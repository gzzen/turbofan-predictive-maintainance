import numpy as np
import pandas as pd
import mlflow
import mlflow.artifacts
from mlflow.sklearn import load_model as sklearn_load_model
from mlflow import MlflowClient
from scipy import stats

import tempfile

from data_load import load_cmapss
from transformer import CMAPSSTransformer
from experiment import asymmetric_score




# configs
# ks test p-value
DRIFT_P_THRESHOLD = 0.05       
# fraction of sensors flagged to trigger drift alert
DRIFT_SENSOR_RATIO = 0.3
# current score / baseline score
PERF_DEGRADATION_RATIO = 1.5
MONITORING_EXPERIMENT = "cmapss_monitoring"
REGISTERED_MODEL_NAME = "cmapss_rul_model"


# extract lists of per-sensor values from traning data
# return dictionary { sensor: [values] }
def build_reference_distributions(train_df: pd.DataFrame) -> dict[str, np.ndarray]:
    sensor_cols = [c for c in train_df.columns if c.startswith("s_")]
    return {col: train_df[col].to_numpy() for col in sensor_cols}


# 1. drift detection using ks test 
# tests on each incoming sensory data, versus reference distribution
# return tuple (has_drift, dictionary { sensor: p-val })
def detect_drift(
    incoming: pd.DataFrame,
    reference: dict[str, np.ndarray],
    p_threshold: float = DRIFT_P_THRESHOLD,
    sensor_ratio: float = DRIFT_SENSOR_RATIO,
) -> tuple[bool, dict[str, float]]:
    sensor_cols = [c for c in incoming.columns if c.startswith("s_")]
    p_values = {}

    for col in sensor_cols:
        if col not in reference:
            continue
        _, p = stats.ks_2samp(reference[col], incoming[col].values)
        p_values[col] = p

    flagged_count = sum(1 for p in p_values.values() if p < p_threshold)
    drift_detected = (flagged_count / len(p_values)) >= sensor_ratio

    return drift_detected, p_values


# 2. performance monitoring
# loader function
def load_production_model_and_transformer() -> tuple:

    client = MlflowClient()
    versions = client.get_latest_versions(REGISTERED_MODEL_NAME, stages=["Production"])
    if not versions:
        raise RuntimeError("No production model in registry.")

    mv = versions[0]
    run_id = mv.run_id
    
    experiment = client.get_experiment_by_name("cmapss_rul")
    logged_models = client.search_logged_models(
				experiment_ids=[experiment.experiment_id] if experiment else [],
		)
    run_models = [m for m in logged_models if m.source_run_id == run_id]
    model_path = run_models[0].artifact_location if run_models else mv.source
    model = sklearn_load_model(model_path)    
    
    # model = sklearn_load_model(f"models:/{REGISTERED_MODEL_NAME}/Production")

    with tempfile.TemporaryDirectory() as tmpdir:
        transformer_path = mlflow.artifacts.download_artifacts(
            run_id=mv.run_id,
            artifact_path="transformer/transformer.pkl",
            dst_path=tmpdir,
        )
        transformer = CMAPSSTransformer.load(transformer_path)

    return model, transformer, mv

# predict RUL on holdout set with production model
# return asymmetric score
def compute_current_performance(
    model,
    transformer: CMAPSSTransformer,
    holdout_df: pd.DataFrame,
) -> float:
    features = transformer.transform(holdout_df, include_rul=True)
    feature_cols = [c for c in features.columns if c not in ("rul", "unit")]

    X = features[feature_cols].values
    y_true = features["rul"].to_numpy()
    y_pred = model.predict(X)

    return asymmetric_score(y_true, y_pred)

# retrieve mean_asym_score logged for production model
def get_baseline_score(mv) -> float | None:
    client = MlflowClient()
    run = client.get_run(mv.run_id)
    return run.data.metrics.get("mean_asym_score")

# monitor a single run
# return & log monitoring summary to MLflow
def run_monitoring(
    incoming_batch: pd.DataFrame,
    holdout_df: pd.DataFrame,
    reference: dict[str, np.ndarray],
) -> dict:
    mlflow.set_experiment(MONITORING_EXPERIMENT)

    model, transformer, mv = load_production_model_and_transformer()
    baseline_score = get_baseline_score(mv)

    drift_detected, p_values = detect_drift(incoming_batch, reference)
    current_score = compute_current_performance(model, transformer, holdout_df)

    # performance degraded if curr_score / base_score > RATIO (default 1.5)
    perf_degraded = (
        baseline_score is not None
        and current_score > baseline_score * PERF_DEGRADATION_RATIO
    )
    retrain_recommended = drift_detected or perf_degraded

    # log monitoring stats
    with mlflow.start_run(run_name="monitoring"):
        mlflow.log_param("model_version", mv.version)
        mlflow.log_param("model_run_id", mv.run_id)

        mlflow.log_metric("current_asym_score", current_score)
        if baseline_score is not None:
            mlflow.log_metric("baseline_asym_score", baseline_score)
            mlflow.log_metric("score_ratio", current_score / baseline_score)

        mlflow.log_metric("drift_detected", int(drift_detected))
        mlflow.log_metric("perf_degraded", int(perf_degraded))
        mlflow.log_metric("retrain_recommended", int(retrain_recommended))

        for sensor, p in p_values.items():
            mlflow.log_metric(f"ks_p_{sensor}", p)

    summary = {
        "model_version": mv.version,
        "drift_detected": drift_detected,
        "perf_degraded": perf_degraded,
        "retrain_recommended": retrain_recommended,
        "current_asym_score": round(current_score, 3),
        "baseline_asym_score": round(baseline_score, 3) if baseline_score else None,
        "flagged_sensors": [s for s, p in p_values.items() if p < DRIFT_P_THRESHOLD],
    }

    print(summary)
    return summary


if __name__ == "__main__":
    train_raw, _ = load_cmapss("./data", subset="FD001")

    # split training data: first 80% for reference, last 20% as holdout
    units = train_raw["unit"].unique()
    rng = np.random.default_rng()
    rng.shuffle(units) # randomly shuffle unit ids
    split = int(len(units) * 0.8)
    train_units = units[:split]
    holdout_units = units[split:]

    reference_df = train_raw[train_raw["unit"].isin(train_units)]
    holdout_df = train_raw[train_raw["unit"].isin(holdout_units)]

    reference = build_reference_distributions(reference_df)

    # simulate incoming data
    incoming_batch = holdout_df.sample(frac=0.2)

    run_monitoring(incoming_batch, holdout_df, reference)