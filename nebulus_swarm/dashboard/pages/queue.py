"""Queue page - pending GitHub issues waiting for minion assignment."""

import pandas as pd
import streamlit as st

from nebulus_swarm.dashboard.data import SwarmDataClient


def render(client: SwarmDataClient) -> None:
    """Render the Queue page."""
    st.header("Work Queue")

    queue_data = client.get_queue()
    status_data = client.get_status()

    if queue_data is None:
        st.warning(
            "Queue data unavailable - Overlord is unreachable "
            "or hasn't completed a queue scan yet."
        )
        return

    issues = queue_data.get("issues", [])
    paused = queue_data.get("paused", False)

    # Queue summary
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Pending Issues", len(issues))

    with col2:
        if status_data:
            active = len(status_data.get("active_minions", []))
            max_c = status_data.get("config", {}).get("max_concurrent", 0)
            available = max(0, max_c - active)
            st.metric("Available Slots", f"{available} / {max_c}")
        else:
            st.metric("Available Slots", "N/A")

    with col3:
        queue_status = "Paused" if paused else "Active"
        st.metric("Queue Processing", queue_status)

    st.divider()

    # Pending issues table
    if not issues:
        st.info("No pending issues in queue.")
        return

    df = pd.DataFrame(issues)

    # Add priority indicator
    if "priority" in df.columns:
        df["priority_label"] = df["priority"].apply(
            lambda p: "🔥 High" if p and p > 0 else "📌 Normal"
        )
    else:
        df["priority_label"] = "📌 Normal"

    # Select and rename columns for display
    display_columns = {
        "priority_label": "Priority",
        "repo": "Repository",
        "number": "Issue #",
        "title": "Title",
    }

    display_df = df[[c for c in display_columns if c in df.columns]].rename(
        columns=display_columns
    )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )
