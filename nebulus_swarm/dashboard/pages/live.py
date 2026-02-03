"""Live Status page - active minions, health, pending questions."""

from datetime import datetime

import streamlit as st

from nebulus_swarm.dashboard.data import SwarmDataClient


def render(client: SwarmDataClient) -> None:
    """Render the Live Status page."""
    st.header("Live Status")

    status = client.get_status()

    if status is None:
        st.error(
            f"Cannot reach Overlord at {client.overlord_url}. "
            "Real-time data unavailable."
        )
        return

    # Health metric cards
    col1, col2, col3, col4 = st.columns(4)

    config = status.get("config", {})
    active_count = len(status.get("active_minions", []))
    max_concurrent = config.get("max_concurrent", 0)

    with col1:
        st.metric("Health", status.get("status", "unknown").title())

    with col2:
        st.metric(
            "Active Minions",
            f"{active_count} / {max_concurrent}",
        )

    with col3:
        queue_status = "Paused" if status.get("paused") else "Active"
        st.metric("Queue", queue_status)

    with col4:
        docker_ok = status.get("docker_available", False)
        st.metric("Docker", "Available" if docker_ok else "Unavailable")

    st.divider()

    # Active Minions table
    st.subheader("Active Minions")
    minions = status.get("active_minions", [])

    if not minions:
        st.info("No active minions.")
    else:
        for m in minions:
            _render_minion_card(m)

    # Pending Questions
    questions = [
        pq for pq in status.get("pending_questions", []) if not pq.get("answered")
    ]

    if questions:
        st.divider()
        st.subheader(f"Pending Questions ({len(questions)})")

        for pq in questions:
            _render_question_card(pq)


def _render_minion_card(minion: dict) -> None:
    """Render a single minion status card."""
    status = minion.get("status", "unknown")
    emoji = "🚀" if status == "starting" else "⚙️"

    col1, col2, col3, col4 = st.columns([2, 2, 1, 2])

    with col1:
        st.markdown(f"{emoji} **`{minion.get('id', 'unknown')}`**")

    with col2:
        repo = minion.get("repo", "")
        issue = minion.get("issue_number", "")
        st.markdown(f"{repo} **#{issue}**")

    with col3:
        st.markdown(f"`{status}`")

    with col4:
        started = minion.get("started_at")
        heartbeat = minion.get("last_heartbeat")

        elapsed = _time_ago(started) if started else "unknown"
        hb_ago = _time_ago(heartbeat) if heartbeat else "never"

        # Warn if heartbeat is stale (>2 min)
        hb_warning = ""
        if heartbeat:
            try:
                hb_dt = datetime.fromisoformat(heartbeat)
                seconds_ago = (datetime.now() - hb_dt).total_seconds()
                if seconds_ago > 120:
                    hb_warning = " ⚠️"
            except (ValueError, TypeError):
                pass

        st.markdown(f"Elapsed: {elapsed} | HB: {hb_ago}{hb_warning}")


def _render_question_card(question: dict) -> None:
    """Render a pending question card."""
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])

        with col1:
            st.markdown(
                f"🤔 **Minion `{question.get('minion_id')}`** "
                f"on #{question.get('issue_number')}"
            )
            st.markdown(f"> {question.get('question_text', '')}")

        with col2:
            asked_at = question.get("asked_at")
            if asked_at:
                st.markdown(f"Asked {_time_ago(asked_at)}")
            st.caption("Reply in Slack thread")


def _time_ago(iso_str: str) -> str:
    """Format an ISO datetime as a relative time string."""
    try:
        dt = datetime.fromisoformat(iso_str)
        delta = datetime.now() - dt
        seconds = int(delta.total_seconds())

        if seconds < 60:
            return f"{seconds}s ago"
        elif seconds < 3600:
            return f"{seconds // 60}m ago"
        elif seconds < 86400:
            return f"{seconds // 3600}h ago"
        else:
            return f"{seconds // 86400}d ago"
    except (ValueError, TypeError):
        return "unknown"
