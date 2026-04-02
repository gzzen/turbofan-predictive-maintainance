import pickle
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

# maximum RUL allowance (for early cycles)
RUL_CAP = 125

# dropping threshold for sensory data with near-zero variance across samples
VAR_THRESHOLD = 1e-4

# window size: number of cycles included in rolling computation
WINDOW_SIZE = 30


class CMAPSSTransformer:
    def __init__(
        self,
        window_size: int = WINDOW_SIZE,
        rul_cap: int = RUL_CAP,
        var_threshold: float = VAR_THRESHOLD,
    ):
        self.window_size = window_size
        self.rul_cap = rul_cap
        self.var_threshold = var_threshold

        self.active_sensors: list[str] = []
        self.scalers: dict[str, MinMaxScaler] = {}
        self._is_fit = False

    def fit(self, df: pd.DataFrame) -> "CMAPSSTransformer":
        # 1. select sensory columns whose variance > VAR_THRESHOLD
        sensor_cols = [c for c in df.columns if c.startswith("s_")]
        variances = df[sensor_cols].var()
        self.active_sensors = variances[variances > self.var_threshold].index.tolist()

        # 2. get rolling statistics
        raw_features = self._raw_window_features(df)

        # 3. re-scale value to [0, 1] based on min / max across rows
        # x = (x - min) / (max - min)
        for col in raw_features.columns:
            scaler = MinMaxScaler()
            scaler.fit(raw_features[[col]])
            self.scalers[col] = scaler

        self._is_fit = True
        return self

    def transform(self, df: pd.DataFrame, include_rul: bool = True) -> pd.DataFrame:
        assert self._is_fit, "call fit() before transform()."

        # compute rolling window stats
        features = self._raw_window_features(df)

        # scale feature values by min / max
        scaled = features.copy()
        for col in features.columns:
            if col in self.scalers:
                scaled[col] = self.scalers[col].transform(features[[col]])

        # generate RUL label, if set
        if include_rul:
            rul = self._compute_rul(df)
            scaled["rul"] = rul.values

        scaled["unit"] = df.groupby("unit").ngroup().values

        return scaled.reset_index(drop=True)

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        return self.fit(df).transform(df, include_rul=True)

    # compute rolling window features
    def _raw_window_features(self, df: pd.DataFrame) -> pd.DataFrame:
        sensor_cols = (
            self.active_sensors
            if self.active_sensors
            else [c for c in df.columns if c.startswith("s_")]
        )

        records = []
        for _, group in df.groupby("unit"):
            # iterates over a single engine unit
            # `sensors` has shape (n_cycles, n_sensors)
            sensors = group[sensor_cols].values.astype(float)
            n = len(sensors)

            for i in range(n):
                # iterate over a single cycle
                # handles two scenarios
                # - cycle >= window size: roll over [cycle - window_size, cycle]
                # - cycle < window size: pad with repeated previous cycles
                start = max(0, i - self.window_size + 1)
                window = sensors[start : i + 1]  # self + historic cycles

                # padding
                if len(window) < self.window_size:
                    pad = np.tile(window[0], (self.window_size - len(window), 1))
                    window = np.vstack([pad, window])

                row = {}
                # append with rolling window statistics
                for j, col in enumerate(sensor_cols):
                    vals = window[:, j]
                    row[f"{col}_mean"] = vals.mean()
                    row[f"{col}_std"] = vals.std()
                    row[f"{col}_delta"] = vals[-1] - vals[0]

                records.append(row)

        return pd.DataFrame(records)

    # compute piecewise RUL labels
    def _compute_rul(self, df: pd.DataFrame) -> pd.Series:
        rul_series = []
        for _, group in df.groupby("unit"):
            max_cycle = group["cycle"].max()
            rul_raw = max_cycle - group["cycle"]  # true remaining cycles

            # caps remaining cycles at rul_cap
            # assume that model can't distinguish very healthy engine
            rul_capped = rul_raw.clip(upper=self.rul_cap)
            rul_series.append(rul_capped)
        return pd.concat(rul_series)

    # persistency functions
    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, path: str) -> "CMAPSSTransformer":
        with open(path, "rb") as f:
            return pickle.load(f)
