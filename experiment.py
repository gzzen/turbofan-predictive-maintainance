import numpy as np
import pandas as pd
import mlflow
from mlflow.sklearn import log_model
from mlflow import MlflowClient
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import root_mean_squared_error
from sklearn.base import clone


from data_load import unit_level_split, load_cmapss
from transformer import CMAPSSTransformer


# scoring function (Saxena et al. 2008)
def asymmetric_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    diff = y_pred - y_true
    scores = np.where(
        diff < 0,
        np.exp(-diff / 13) - 1,  # early prediction
        np.exp(diff / 10) - 1,  # late prediction
    )
    return float(scores.sum())


# single fold evaluation
# return (asymmetric_score, RMSE, transformer) tuple
def evaluate_fold(
    model,
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    window_size: int,
    rul_cap: int,
) -> tuple[float, float, CMAPSSTransformer]:
    transformer = CMAPSSTransformer(window_size=window_size, rul_cap=rul_cap)

    train_feat = transformer.fit_transform(train_df)
    val_feat = transformer.transform(val_df, include_rul=True)

    feature_cols = [c for c in train_feat.columns if c not in ("rul", "unit")]

    # training features + labels
    X_train = train_feat[feature_cols].to_numpy()
    y_train = train_feat["rul"].to_numpy()

    # validation features + labels
    X_val = val_feat[feature_cols].to_numpy()
    y_val = val_feat["rul"].to_numpy()

    # fit prediction model
    model.fit(X_train, y_train)
    y_pred = model.predict(X_val)

    # get evaluation stats
    rmse = root_mean_squared_error(y_val, y_pred)
    asym = asymmetric_score(y_val, y_pred)

    return rmse, asym, transformer


# full CV loop with MLflow logging
# return run id for reference
def run_experiment(
    train_raw: pd.DataFrame,
    model,
    model_name: str,
    params: dict,
    window_size: int = 30,
    rul_cap: int = 125,
    n_splits: int = 5,
    experiment_name: str = "cmapss_rul",
) -> str:
    print(f"\n=== {model_name} ===")

    # setup experiment
    mlflow.set_experiment(experiment_name)

    # produce n-fold pairs with training dataset
    splits = unit_level_split(train_raw, n_splits=n_splits)

    fold_rmse = []
    fold_asym = []
    last_transformer = None

    # logs model training process to MLflow
    # one run per model configuration
    # cv fold is logged with `step` param
    with mlflow.start_run(run_name=model_name) as run:
        print(f"  run_id: {run.info.run_id}")

        # log hyperparameters
        mlflow.log_params(params)
        mlflow.log_param("window_size", window_size)
        mlflow.log_param("rul_cap", rul_cap)
        mlflow.log_param("n_splits", n_splits)

        # log per-fold stats
        for i, (tr, val) in enumerate(splits):
            print(f"  fold {i + 1}/{n_splits} ...", end=" ", flush=True)
            fold_model = clone(model)  # clone model

            rmse, asym, transformer = evaluate_fold(
                fold_model, tr, val, window_size, rul_cap
            )
            fold_rmse.append(rmse)
            fold_asym.append(asym)
            last_transformer = transformer

            mlflow.log_metric("fold_rmse", rmse, step=i)
            mlflow.log_metric("fold_asym_score", asym, step=i)
            print(f"rmse={rmse:.3f}  asym={asym:.3f}")

        # log summary stats
        mean_rmse = float(np.mean(fold_rmse))
        mean_asym = float(np.mean(fold_asym))

        mlflow.log_metric("mean_rmse", mean_rmse)
        mlflow.log_metric("mean_asym_score", mean_asym)
        print(f"  mean  rmse={mean_rmse:.3f}  asym={mean_asym:.3f}")

        # fit & log with full training dataset
        print("  fitting on full training set ...", end=" ", flush=True)
        full_transformer = CMAPSSTransformer(window_size=window_size, rul_cap=rul_cap)
        full_features = full_transformer.fit_transform(train_raw)
        feature_cols = [c for c in full_features.columns if c not in ("rul", "unit")]

        final_model = clone(model)
        final_model.fit(full_features[feature_cols].values, full_features["rul"].values)
        print("done")

        # Log model and transformer together
        print("  logging artifacts to MLflow ...", end=" ", flush=True)
        log_model(final_model, artifact_path="model")

        transformer_path = "/tmp/transformer.pkl"
        full_transformer.save(transformer_path)
        mlflow.log_artifact(transformer_path, artifact_path="transformer")
        print("done")

        return run.info.run_id

# find the best run by lowest asym score
# then register into MLflow
def register_best_run(
    experiment_name: str = "cmapss_rul",
    registered_model_name: str = "cmapss_rul_model",
) -> str:
    # retrieve experiment
    client = MlflowClient()
    experiment = client.get_experiment_by_name(experiment_name)
    if experiment is None:
        raise ValueError(f"Experiment '{experiment_name}' not found.")
    
    # find best run, register by run id
    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string="metrics.mean_asym_score > 0",
        order_by=["metrics.mean_asym_score ASC"],
        max_results=1,
    )

    if not runs:
        raise ValueError("No runs found in experiment.")

    best_run = runs[0]
    run_id = best_run.info.run_id
    model_source = f"{best_run.info.artifact_uri}/model"

    try:
        client.create_registered_model(registered_model_name)
    except Exception:
        pass  # already exists

    mv = client.create_model_version(
        name=registered_model_name,
        source=model_source,
        run_id=run_id,
    )

    # mark "Staging" version
    client.transition_model_version_stage(
        name=registered_model_name,
        version=mv.version,
        stage="Staging",
    )

    print(f"Registered run {run_id} as {registered_model_name} v{mv.version} (Staging)")
    return mv.version

# promotes a staging model to production
def promote_to_production(
    version: str,
    registered_model_name: str = "cmapss_rul_model",
) -> None:
    client = MlflowClient()
    client.transition_model_version_stage(
        name=registered_model_name,
        version=version,
        stage="Production",
        archive_existing_versions=True,
    )
    print(f"Promoted {registered_model_name} v{version} to Production")


if __name__ == "__main__":

    train_raw, _ = load_cmapss("./data", subset="FD001")

    # baseline
    run_experiment(
        train_raw,
        model=LinearRegression(),
        model_name="linear_baseline",
        params={},
    )

    # gradient boosting
    gb_params = {"n_estimators": 200, "max_depth": 5, "learning_rate": 0.05}
    run_experiment(
        train_raw,
        model=GradientBoostingRegressor(**gb_params),
        model_name="gradient_boosting",
        params=gb_params,
    )

    # register best run & promote
    version = register_best_run()
    promote_to_production(version)
