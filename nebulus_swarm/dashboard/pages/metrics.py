"""Metrics page - aggregate analytics over time."""

import pandas as pd
import streamlit as st

from nebulus_swarm.dashboard.data import SwarmDataClient


def render(client: SwarmDataClient) -> None:
    """Render the Metrics page."""
    st.header("Metrics")

    # Time range selector
    time_ranges = {
        "Last 24 hours": 1,
        "Last 7 days": 7,
        "Last 30 days": 30,
        "All time": None,
    }
    selected_range = st.radio(
        "Time range",
        list(time_ranges.keys()),
        horizontal=True,
    )
    days = time_ranges[selected_range]

    # Fetch metrics
    m = client.get_metrics(days=days)

    if m["total"] == 0:
        st.info("No work history data available for the selected time range.")
        return

    # Success Rate
    st.subheader("Success Rate")
    _render_success_rate(m)

    st.divider()

    # Duration Trends
    if m["daily_stats"]:
        st.subheader("Duration Trends")
        _render_duration_trends(m)

        st.divider()

        # Throughput
        st.subheader("Throughput")
        _render_throughput(m)

        st.divider()

    # Failure Analysis
    if m["error_types"]:
        st.subheader("Failure Analysis")
        _render_failure_analysis(m)


def _render_success_rate(m: dict) -> None:
    """Render the success rate section."""
    col1, col2, col3, col4 = st.columns(4)

    rate = m["completion_rate"]
    if rate >= 0.8:
        color = "normal"
    elif rate >= 0.5:
        color = "off"
    else:
        color = "inverse"

    with col1:
        st.metric(
            "Completion Rate",
            f"{rate:.0%}",
            delta=None,
            delta_color=color,
        )

    with col2:
        st.metric("Completed", m["completed"])

    with col3:
        st.metric("Failed", m["failed"])

    with col4:
        st.metric("Timeout", m["timeout"])

    # Breakdown bar
    if m["total"] > 0:
        data = pd.DataFrame(
            {
                "Status": ["Completed", "Failed", "Timeout"],
                "Count": [m["completed"], m["failed"], m["timeout"]],
            }
        )
        st.bar_chart(data, x="Status", y="Count", horizontal=True, height=150)


def _render_duration_trends(m: dict) -> None:
    """Render the duration trends section."""
    daily_df = pd.DataFrame(m["daily_stats"])

    if daily_df.empty:
        st.info("Not enough data for duration trends.")
        return

    # Duration chart
    if "avg_duration" in daily_df.columns:
        chart_data = daily_df[["date", "avg_duration"]].copy()
        chart_data["avg_duration"] = chart_data["avg_duration"] / 60  # To minutes
        chart_data = chart_data.rename(
            columns={"date": "Date", "avg_duration": "Avg Duration (min)"}
        )
        st.bar_chart(chart_data, x="Date", y="Avg Duration (min)")

    # Duration stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Average", _format_duration(m["avg_duration"]))
    with col2:
        st.metric("Median", _format_duration(m["median_duration"]))
    with col3:
        st.metric("Fastest", _format_duration(m["min_duration"]))
    with col4:
        st.metric("Slowest", _format_duration(m["max_duration"]))


def _render_throughput(m: dict) -> None:
    """Render the throughput section."""
    daily_df = pd.DataFrame(m["daily_stats"])

    if daily_df.empty:
        return

    # Tasks per day
    chart_data = daily_df[["date", "completed", "failed"]].copy()
    chart_data = chart_data.rename(
        columns={
            "date": "Date",
            "completed": "Completed",
            "failed": "Failed",
        }
    )
    st.line_chart(chart_data, x="Date", y=["Completed", "Failed"])


def _render_failure_analysis(m: dict) -> None:
    """Render the failure analysis section."""
    error_types = m["error_types"]

    if not error_types:
        st.info("No failures in the selected time range.")
        return

    rows = []
    for err_type, info in sorted(
        error_types.items(), key=lambda x: x[1]["count"], reverse=True
    ):
        rows.append(
            {
                "Error Type": err_type,
                "Count": info["count"],
                "Last Message": info["last_message"][:100],
            }
        )

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if not seconds:
        return "0s"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"
