import json
import pandas as pd
from pathlib import Path
from mlflow import MlflowClient

MONITORING_EXPERIMENT = "cmapss_monitoring"
REGISTERED_MODEL_NAME = "cmapss_rul_model"
OUTPUT_DIR = Path("demo/static")

client = MlflowClient()


def export_monitoring_runs():
    experiment = client.get_experiment_by_name(MONITORING_EXPERIMENT)
    if experiment is None:
        print("No monitoring experiment found.")
        return

    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        order_by=["start_time ASC"],
    )

    records = []
    for run in runs:
        m = run.data.metrics
        records.append({
            "run_id": run.info.run_id,
            "timestamp": pd.Timestamp(run.info.start_time, unit="ms").isoformat(),
            "current_asym_score": m.get("current_asym_score"),
            "baseline_asym_score": m.get("baseline_asym_score"),
            "score_ratio": m.get("score_ratio"),
            "drift_detected": bool(m.get("drift_detected", 0)),
            "perf_degraded": bool(m.get("perf_degraded", 0)),
            "retrain_recommended": bool(m.get("retrain_recommended", 0)),
            **{k: v for k, v in m.items() if k.startswith("ks_p_")},
        })

    path = OUTPUT_DIR / "monitoring_runs.json"
    with open(path, "w") as f:
        json.dump(records, f, indent=2)
    print(f"Exported {len(records)} monitoring runs to {path}")


def export_model_versions():
    try:
        versions = client.search_model_versions(f"name='{REGISTERED_MODEL_NAME}'")
        records = [
            {"version": mv.version, "stage": mv.current_stage, "run_id": mv.run_id}
            for mv in versions
        ]
    except Exception as e:
        print(f"Could not fetch model versions: {e}")
        records = []

    path = OUTPUT_DIR / "model_versions.json"
    with open(path, "w") as f:
        json.dump(records, f, indent=2)
    print(f"Exported {len(records)} model versions to {path}")


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(exist_ok=True)
    export_monitoring_runs()
    export_model_versions()