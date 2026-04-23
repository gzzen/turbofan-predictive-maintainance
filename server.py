import asyncio
import json
import os
import time
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from predictor import RULPredictor, MAINTENANCE_THRESHOLD


# singleton predictor loaded at startup
predictor = RULPredictor()


# ── Pydantic request/response models ─────────────────────────────────────────

class CycleReading(BaseModel):
    os_1: float
    os_2: float
    os_3: float
    sensors: list[float]  # 21 values, s_1 through s_21

class EngineRequest(BaseModel):
    engine_id: str
    cycles: list[CycleReading]  # ordered oldest to newest

class RULResponse(BaseModel):
    engine_id: str
    predicted_rul: float
    maintenance_advisory: bool
    threshold_cycles: int

class BatchRequest(BaseModel):
    engines: list[EngineRequest]

class BatchResponse(BaseModel):
    predictions: list[RULResponse]


SENSOR_COLS = [f"s_{i}" for i in range(1, 22)]
OS_COLS = ["os_1", "os_2", "os_3"]
DATA_COLS = ["unit", "cycle"] + OS_COLS + SENSOR_COLS


def request_to_dataframe(engine: EngineRequest) -> pd.DataFrame:
    """Convert a single EngineRequest into a transformer-ready dataframe."""
    records = []
    for reading in engine.cycles:
        if len(reading.sensors) != 21:
            raise HTTPException(
                status_code=422,
                detail=f"Expected 21 sensor values, got {len(reading.sensors)}"
            )
        row = {
            "os_1": reading.os_1,
            "os_2": reading.os_2,
            "os_3": reading.os_3,
            **{f"s_{i+1}": reading.sensors[i] for i in range(21)},
        }
        records.append(row)
    return pd.DataFrame(records)


def load_test_engine(engine_id: str, dataset: str = "FD001") -> Optional[pd.DataFrame]:
    """
    Load all cycles for a specific engine unit from the CMAPSS test set.
    engine_id format: 'engine_<unit_number>', e.g. 'engine_1'.
    """
    try:
        unit_num = int(engine_id.split("_")[-1])
    except (ValueError, IndexError):
        return None

    data_path = os.path.join("data", f"test_{dataset}.txt")
    if not os.path.exists(data_path):
        return None

    df = pd.read_csv(data_path, sep=r"\s+", header=None, usecols=range(26), engine="python")
    df.columns = DATA_COLS

    engine_data = df[df["unit"] == unit_num].copy().reset_index(drop=True)
    return engine_data if len(engine_data) > 0 else None


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="CMAPSS RUL Prediction Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    predictor.load_production()


# loading status and current run-id
@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded": predictor.model is not None,
        "run_id": predictor.run_id,
    }


@app.get("/engines")
def list_engines(dataset: str = "FD001", limit: int = 20):
    """List available engine IDs from the test dataset."""
    data_path = os.path.join("data", f"test_{dataset}.txt")
    if not os.path.exists(data_path):
        raise HTTPException(status_code=404, detail=f"Dataset {dataset} not found")

    df = pd.read_csv(data_path, sep=r"\s+", header=None, usecols=[0], engine="python")
    units = sorted(df[0].unique().tolist())[:limit]
    return {"dataset": dataset, "engines": [f"engine_{u}" for u in units]}


@app.get("/stream/{engine_id}")
async def stream_engine(engine_id: str, interval: float = 1.0, dataset: str = "FD001"):
    """
    Stream real-time RUL predictions for a test engine as Server-Sent Events.

    Each SSE 'data' event carries a JSON payload with:
      - engine_id, cycle, total_cycles
      - predicted_rul, maintenance_advisory, threshold_cycles
      - sensors: {s_1 … s_21}
      - inference_ts: Unix ms at inference completion (client uses Date.now() delta for E2E latency)
      - inference_duration_ms: server-side model inference time

    Terminates with a named 'done' event when all cycles are exhausted.
    """
    engine_data = load_test_engine(engine_id, dataset)
    if engine_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engine '{engine_id}' not found in dataset {dataset}",
        )

    # clamp interval to avoid runaway fast streams
    stream_interval = max(0.1, min(float(interval), 60.0))

    async def event_generator():
        total = len(engine_data)

        for cycle_idx in range(total):
            # Feed all cycles up to this point into the predictor (rolling window)
            cycles_so_far = engine_data.iloc[: cycle_idx + 1][OS_COLS + SENSOR_COLS].copy()

            t0 = time.perf_counter()
            rul, advisory = predictor.predict(cycles_so_far)
            inference_duration_ms = round((time.perf_counter() - t0) * 1000, 3)

            current_row = engine_data.iloc[cycle_idx]
            sensors = {col: round(float(current_row[col]), 4) for col in SENSOR_COLS}

            payload = {
                "engine_id": engine_id,
                "cycle": int(current_row["cycle"]),
                "total_cycles": total,
                "predicted_rul": round(float(rul), 2),
                "maintenance_advisory": bool(advisory),
                "threshold_cycles": MAINTENANCE_THRESHOLD,
                "sensors": sensors,
                # Unix ms timestamp — client subtracts Date.now() for E2E latency
                "inference_ts": int(time.time() * 1000),
                "inference_duration_ms": inference_duration_ms,
            }

            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(stream_interval)

        # Signal clean stream termination to the client
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


@app.post("/predict", response_model=RULResponse)
def predict(request: EngineRequest):
    cycles_df = request_to_dataframe(request)
    rul, advisory = predictor.predict(cycles_df)
    return RULResponse(
        engine_id=request.engine_id,
        predicted_rul=round(rul, 2),
        maintenance_advisory=advisory,
        threshold_cycles=MAINTENANCE_THRESHOLD,
    )


@app.post("/predict/batch", response_model=BatchResponse)
def predict_batch(request: BatchRequest):
    results = []
    for engine in request.engines:
        cycles_df = request_to_dataframe(engine)
        rul, advisory = predictor.predict(cycles_df)
        results.append(RULResponse(
            engine_id=engine.engine_id,
            predicted_rul=round(rul, 2),
            maintenance_advisory=advisory,
            threshold_cycles=MAINTENANCE_THRESHOLD,
        ))
    return BatchResponse(predictions=results)
