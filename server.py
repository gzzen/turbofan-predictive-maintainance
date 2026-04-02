import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from predictor import RULPredictor, MAINTENANCE_THRESHOLD


# singleton predictor loaded at startup
predictor = RULPredictor()


# data schema for HTTP request / response (pydantic)
# one cycle of sensor data
class CycleReading(BaseModel):
    os_1: float
    os_2: float
    os_3: float
    sensors: list[float]  # 21 values, s_1 through s_21

# all cycle stats for one engine
class EngineRequest(BaseModel):
    engine_id: str
    cycles: list[CycleReading]  # ordered oldest to newest

# prediction output
class RULResponse(BaseModel):
    engine_id: str
    predicted_rul: float
    maintenance_advisory: bool
    threshold_cycles: int

# wrapper for processing a list of engines
class BatchRequest(BaseModel):
    engines: list[EngineRequest]

# batch prediction output
class BatchResponse(BaseModel):
    predictions: list[RULResponse]


SENSOR_COLS = [f"s_{i}" for i in range(1, 22)]
OS_COLS = ["os_1", "os_2", "os_3"]

# convert a single EngineRequest into a transformer-ready dataframe
def request_to_dataframe(engine: EngineRequest) -> pd.DataFrame:
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


# server
app = FastAPI(title="CMAPSS RUL Prediction Service")


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