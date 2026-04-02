import pandas as pd
from pathlib import Path
from sklearn.model_selection import GroupKFold


COLUMNS = [
    "unit",
    "cycle",
    "os_1",
    "os_2",
    "os_3",
    *[f"s_{i}" for i in range(1, 22)], # sensory columns
]

# returns tuple[train_set, test_set]
def load_cmapss(
    data_dir: str, subset: str = "FD001"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = Path(data_dir)

    train = pd.read_csv(
        base / f"train_{subset}.txt", sep=r"\s+", header=None, names=COLUMNS
    )
    test = pd.read_csv(
        base / f"test_{subset}.txt", sep=r"\s+", header=None, names=COLUMNS
    )

    return train, test

# generate a list of (train_fold, validation_fold) tuple
def unit_level_split(df: pd.DataFrame, n_splits: int = 5
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    gkf = GroupKFold(n_splits=n_splits)
    units = df["unit"].to_numpy()
    splits = []
    for train_idx, val_idx in gkf.split(df, groups=units):
        splits.append((df.iloc[train_idx], df.iloc[val_idx]))
    return splits
