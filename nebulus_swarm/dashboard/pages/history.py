"""Work History page - filterable log of completed work."""

import pandas as pd
import streamlit as st

from nebulus_swarm.dashboard.data import SwarmDataClient


def render(client: SwarmDataClient) -> None:
    """Render the Work History page."""
    st.header("Work History")

    # Filter bar
    col1, col2, col3 = st.columns(3)

    with col1:
        repos = ["All"] + client.get_distinct_repos()
        selected_repo = st.selectbox("Repository", repos)

    with col2:
        statuses = ["All", "completed", "failed", "timeout"]
        selected_status = st.selectbox("Status", statuses)

    with col3:
        limit = st.slider("Results", min_value=10, max_value=100, value=50)

    # Fetch data
    repo_filter = None if selected_repo == "All" else selected_repo
    status_filter = None if selected_status == "All" else selected_status

    history = client.get_work_history(
        repo=repo_filter, status=status_filter, limit=limit
    )

    if not history:
        st.info("No work history yet.")
        return

    # Build DataFrame
    df = pd.DataFrame(history)

    # Format columns for display
    display_df = _format_history_df(df)

    # Summary row
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Records", len(df))
    with col2:
        completed_count = len(df[df["status"] == "completed"])
        rate = completed_count / len(df) if len(df) > 0 else 0
        st.metric("Completion Rate", f"{rate:.0%}")
    with col3:
        if "duration_seconds" in df.columns:
            avg_dur = df["duration_seconds"].mean()
            st.metric("Avg Duration", _format_duration(avg_dur))
        else:
            st.metric("Avg Duration", "N/A")

    st.divider()

    # History table
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "status": st.column_config.TextColumn("Status"),
            "repo": st.column_config.TextColumn("Repository"),
            "issue_number": st.column_config.NumberColumn("Issue #", format="%d"),
            "pr_number": st.column_config.NumberColumn("PR #", format="%d"),
            "duration": st.column_config.TextColumn("Duration"),
            "completed_at": st.column_config.TextColumn("Completed"),
            "error_message": st.column_config.TextColumn("Error"),
        },
    )


def _format_history_df(df: pd.DataFrame) -> pd.DataFrame:
    """Format history DataFrame for display."""
    display = df.copy()

    # Format duration
    if "duration_seconds" in display.columns:
        display["duration"] = display["duration_seconds"].apply(
            lambda x: _format_duration(x) if pd.notna(x) else "N/A"
        )
    else:
        display["duration"] = "N/A"

    # Add status emoji
    status_emoji = {
        "completed": "✅ completed",
        "failed": "❌ failed",
        "timeout": "⏰ timeout",
    }
    display["status"] = display["status"].map(lambda s: status_emoji.get(s, s))

    # Truncate error messages
    if "error_message" in display.columns:
        display["error_message"] = display["error_message"].apply(
            lambda x: x[:80] + "..." if isinstance(x, str) and len(x) > 80 else x
        )

    # Select columns for display
    columns = [
        "status",
        "repo",
        "issue_number",
        "pr_number",
        "duration",
        "completed_at",
        "error_message",
    ]
    return display[[c for c in columns if c in display.columns]]


def _format_duration(seconds: float) -> str:
    """Format seconds as 'Xm Ys'."""
    if pd.isna(seconds) or seconds is None:
        return "N/A"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}m {secs}s"
