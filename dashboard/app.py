"""DataPulse health dashboard (Streamlit).

Three views:
1. Health overview — green/red status tiles for the latest run.
2. Trends over time — volume, freshness, and per-column distribution drift.
3. Recent anomalies — a table of flagged metrics.
"""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

# Make the src package importable when run via `streamlit run dashboard/app.py`.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from datapulse.config import load_config  # noqa: E402
from datapulse.storage import Storage  # noqa: E402

st.set_page_config(page_title="DataPulse — Data Health", page_icon="📈", layout="wide")


@st.cache_data(ttl=60)
def _load() -> tuple[pd.DataFrame, pd.DataFrame]:
    config = load_config()
    storage = Storage(config)
    return storage.read_run_history(), storage.read_metrics()


def _status_color(status: str) -> str:
    return {"success": "🟢", "warning": "🟠", "failed": "🔴"}.get(status, "⚪")


def main() -> None:
    st.title("📈 DataPulse — Self-Monitoring Data Pipeline")
    st.caption("Catches schema drift, freshness gaps, volume anomalies, and distribution shifts.")

    run_history, metrics = _load()

    if run_history.empty:
        st.warning("No runs recorded yet. Run `make run` to populate the dashboard.")
        return

    latest = run_history.sort_values("run_ts").iloc[-1]

    # --- View 1: Health overview --------------------------------------------
    st.subheader("Data health overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Latest status", f"{_status_color(latest['status'])} {latest['status']}")
    c2.metric("Rows last run", int(latest["rows_ingested"]))
    c3.metric("Checks failed", int(latest["checks_failed"]))
    c4.metric("Anomalies (last run)", int(latest["anomalies_found"]))

    latest_metrics = (
        metrics[metrics["run_id"] == latest["run_id"]] if not metrics.empty else pd.DataFrame()
    )
    if not latest_metrics.empty:
        st.markdown("**Latest checks**")
        tiles = st.columns(min(len(latest_metrics), 5))
        for i, (_, row) in enumerate(latest_metrics.iterrows()):
            icon = "🔴" if row["is_anomaly"] else "🟢"
            label = f"{row['metric']} · {row['column_name']}"
            tiles[i % len(tiles)].metric(label, f"{icon} {row['value']:.2f}")

    # --- View 2: Trends ------------------------------------------------------
    st.subheader("Trends over time")
    rh = run_history.copy()
    rh["run_ts"] = pd.to_datetime(rh["run_ts"])
    colA, colB = st.columns(2)
    with colA:
        st.markdown("**Rows ingested per run**")
        st.altair_chart(
            alt.Chart(rh)
            .mark_line(point=True)
            .encode(
                x="run_ts:T",
                y="rows_ingested:Q",
                tooltip=["run_ts:T", "rows_ingested:Q", "status:N"],
            ),
            use_container_width=True,
        )
    with colB:
        st.markdown("**Anomalies per run**")
        st.altair_chart(
            alt.Chart(rh)
            .mark_bar()
            .encode(
                x="run_ts:T",
                y="anomalies_found:Q",
                color=alt.Color("status:N", legend=None),
                tooltip=["run_ts:T", "anomalies_found:Q", "status:N"],
            ),
            use_container_width=True,
        )

    if not metrics.empty:
        drift = metrics[metrics["metric"] == "distribution_drift"].copy()
        if not drift.empty:
            drift["run_ts"] = pd.to_datetime(drift["run_ts"])
            st.markdown("**Distribution drift — per-column mean over time**")
            st.altair_chart(
                alt.Chart(drift)
                .mark_line(point=True)
                .encode(
                    x="run_ts:T",
                    y="value:Q",
                    color="column_name:N",
                    tooltip=["run_ts:T", "column_name:N", "value:Q", "zscore:Q"],
                ),
                use_container_width=True,
            )

    # --- View 3: Recent anomalies -------------------------------------------
    st.subheader("Recent anomalies")
    if metrics.empty:
        st.info("No metrics recorded yet.")
    else:
        anomalies = metrics[metrics["is_anomaly"]].sort_values("run_ts", ascending=False)
        if anomalies.empty:
            st.success("No anomalies flagged across recorded runs. 🎉")
        else:
            st.dataframe(
                anomalies[["run_ts", "metric", "column_name", "value", "baseline", "zscore"]],
                use_container_width=True,
                hide_index=True,
            )


if __name__ == "__main__":
    main()
