import os
import tempfile
import pandas as pd
import mlflow
import mlflow.artifacts
from mlflow import MlflowClient
from mlflow.sklearn import load_model as sklearn_load_model

from transformer import CMAPSSTransformer


REGISTERED_MODEL_NAME = os.getenv("REGISTERED_MODEL_NAME", "cmapss_rul_model")
MAINTENANCE_THRESHOLD = int(os.getenv("MAINTENANCE_THRESHOLD", 30))  # cycles

# singleton class that (a) loads pruduction model and transformer from registery
# and (b) run inference with them
class RULPredictor:
    def __init__(self):
        self.model = None
        self.transformer: CMAPSSTransformer | None = None
        self.run_id: str | None = None

    # load production model and its associated data transformer from MLflow
    def load_production(self) -> None:
        client = MlflowClient()

        versions = client.get_latest_versions(REGISTERED_MODEL_NAME, stages=["Production"])
        if not versions:
            raise RuntimeError("No production model found in registry.")

        mv = versions[0]
        self.run_id = mv.run_id

        # MLflow 3.x stores models in models/m-xxx outside the run artifact dir;
        # look up the actual location via search_logged_models
        experiment = client.get_experiment_by_name("cmapss_rul")
        logged_models = client.search_logged_models(
            experiment_ids=[experiment.experiment_id] if experiment else [],
        )
        run_models = [m for m in logged_models if m.source_run_id == self.run_id]
        model_path = run_models[0].artifact_location if run_models else mv.source
        self.model = sklearn_load_model(model_path)

        # load transformer from the same run
        with tempfile.TemporaryDirectory() as tmpdir:
            transformer_path = mlflow.artifacts.download_artifacts(
                run_id=self.run_id,
                artifact_path="transformer/transformer.pkl",
                dst_path=tmpdir,
            )
            self.transformer = CMAPSSTransformer.load(transformer_path)

        print(f"Loaded production model v{mv.version} from run {self.run_id}")

    # predict RUL given recent cycle stats
    # return (predicted RUL, advisory (whether a maintainance is suggested))
    def predict(self, cycles: pd.DataFrame) -> tuple[float, bool]:
        assert self.model is not None, "Call load_production() first."

        # standardize labels
        cycles = cycles.copy()
        cycles["unit"] = 1
        cycles["cycle"] = range(1, len(cycles) + 1)

        assert self.transformer is not None, "Call load_production() first."
        # transform
        features = self.transformer.transform(cycles, include_rul=False)
        feature_cols = [c for c in features.columns if c != "unit"]

        # predict with last row - most recent cycle
        X = features[feature_cols].iloc[[-1]].values
        rul = float(self.model.predict(X)[0])
        rul = max(0.0, rul)  # clip negative predictions

        advisory = rul <= MAINTENANCE_THRESHOLD
        return rul, advisory
