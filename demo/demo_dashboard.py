import json
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

DRIFT_P_THRESHOLD = 0.05
STATIC_DIR = Path("demo/static")

st.set_page_config(page_title="CMAPSS RUL Monitor", layout="wide")


@st.cache_data
def fetch_monitoring_runs() -> pd.DataFrame:
    path = STATIC_DIR / "monitoring_runs.json"
    if not path.exists():
        return pd.DataFrame()
    with open(path) as f:
        records = json.load(f)
    df = pd.DataFrame(records)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


@st.cache_data
def fetch_model_versions() -> list[dict]:
    path = STATIC_DIR / "model_versions.json"
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


# layout
st.title("CMAPSS RUL Monitoring Dashboard")

runs_df = fetch_monitoring_runs()
model_versions = fetch_model_versions()

if runs_df.empty:
    st.warning("No monitoring data found. Run export_static.py to generate static data.")
    st.stop()

latest = runs_df.iloc[-1]

# view 1: model status
st.subheader("Model Status")

col1, col2, col3, col4 = st.columns(4)
production = next((v for v in model_versions if v["stage"] == "Production"), None)

with col1:
    st.metric("Production Version", f"v{production['version']}" if production else "None")
with col2:
    st.metric("Baseline Score", f"{latest['baseline_asym_score']:.1f}" if latest["baseline_asym_score"] else "N/A")
with col3:
    st.metric("Retrain Recommended", "Yes" if latest["retrain_recommended"] else "No")
with col4:
    st.metric("Monitoring Runs", len(runs_df))

if model_versions:
    st.dataframe(pd.DataFrame(model_versions), use_container_width=True, hide_index=True)

# view 2: performance over time
st.subheader("Performance History")

if len(runs_df) == 1:
    st.info("Only one monitoring run recorded.")

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=runs_df["timestamp"],
    y=runs_df["current_asym_score"],
    mode="lines+markers",
    name="Current Score",
))

if runs_df["baseline_asym_score"].notna().any():
    baseline = runs_df["baseline_asym_score"].iloc[-1]
    fig.add_hline(y=baseline, line_dash="dash", annotation_text="Baseline")
    fig.add_hline(y=baseline * 1.5, line_dash="dot", annotation_text="Retrain threshold")

fig.update_layout(
    xaxis_title="Time",
    yaxis_title="Asymmetric Score (lower is better)",
    height=350,
)
st.plotly_chart(fig, use_container_width=True)

# view 3: drift detection
st.subheader("Sensor Drift (Latest Run)")

sensor_p_cols = [c for c in latest.index if c.startswith("ks_p_")]

if sensor_p_cols:
    sensor_names = [c.replace("ks_p_", "") for c in sensor_p_cols]
    p_values = [latest[c] for c in sensor_p_cols]
    flagged = [p < DRIFT_P_THRESHOLD for p in p_values]

    drift_df = pd.DataFrame({
        "sensor": sensor_names,
        "p_value": p_values,
        "flagged": flagged,
    }).sort_values("p_value")

    fig2 = go.Figure(go.Bar(x=drift_df["sensor"], y=drift_df["p_value"]))
    fig2.add_hline(y=DRIFT_P_THRESHOLD, line_dash="dash", annotation_text=f"p={DRIFT_P_THRESHOLD}")
    fig2.update_layout(xaxis_title="Sensor", yaxis_title="KS p-value", height=350)
    st.plotly_chart(fig2, use_container_width=True)

    flagged_sensors = [s for s, f in zip(sensor_names, flagged) if f]
    if flagged_sensors:
        st.warning(f"{len(flagged_sensors)} sensor(s) flagged: {', '.join(flagged_sensors)}")
    else:
        st.success("No drift detected.")
else:
    st.info("No sensor p-values found in latest monitoring run.")

with st.expander("Raw monitoring data"):
    st.dataframe(runs_df, use_container_width=True, hide_index=True)