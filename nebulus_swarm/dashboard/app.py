"""Nebulus Swarm Dashboard - Streamlit entry point.

Run with: streamlit run nebulus_swarm/dashboard/app.py
"""

import os
import time

import streamlit as st

from nebulus_swarm.dashboard.data import SwarmDataClient
from nebulus_swarm.dashboard.pages import history, live, metrics, queue

# Page configuration
st.set_page_config(
    page_title="Nebulus Swarm Dashboard",
    page_icon="🐝",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Available pages
PAGES = {
    "Live Status": live.render,
    "Work History": history.render,
    "Queue": queue.render,
    "Metrics": metrics.render,
}


def get_client() -> SwarmDataClient:
    """Get or create a cached SwarmDataClient."""
    overlord_url = st.session_state.get(
        "overlord_url",
        os.environ.get("OVERLORD_URL", "http://localhost:8080"),
    )
    state_db_path = st.session_state.get(
        "state_db_path",
        os.environ.get("OVERLORD_STATE_DB", "/var/lib/overlord/state.db"),
    )

    # Cache client in session state
    cache_key = f"{overlord_url}:{state_db_path}"
    if (
        "client" not in st.session_state
        or st.session_state.get("client_key") != cache_key
    ):
        st.session_state["client"] = SwarmDataClient(
            overlord_url=overlord_url,
            state_db_path=state_db_path,
        )
        st.session_state["client_key"] = cache_key

    return st.session_state["client"]


def sidebar() -> str:
    """Render the sidebar and return the selected page name."""
    with st.sidebar:
        st.title("Nebulus Swarm")

        # Page navigation
        page = st.radio(
            "Navigate",
            list(PAGES.keys()),
            label_visibility="collapsed",
        )

        st.divider()

        # Auto-refresh toggle
        auto_refresh = st.toggle("Auto-refresh", value=True)
        st.session_state["auto_refresh"] = auto_refresh

        if auto_refresh:
            interval = st.slider(
                "Refresh interval (s)", min_value=5, max_value=60, value=10
            )
            st.session_state["refresh_interval"] = interval
        else:
            if st.button("Refresh now"):
                st.rerun()

        st.divider()

        # Configuration
        with st.expander("Settings"):
            overlord_url = st.text_input(
                "Overlord URL",
                value=st.session_state.get(
                    "overlord_url",
                    os.environ.get("OVERLORD_URL", "http://localhost:8080"),
                ),
            )
            st.session_state["overlord_url"] = overlord_url

            state_db_path = st.text_input(
                "State DB Path",
                value=st.session_state.get(
                    "state_db_path",
                    os.environ.get("OVERLORD_STATE_DB", "/var/lib/overlord/state.db"),
                ),
            )
            st.session_state["state_db_path"] = state_db_path

        # Connection status
        client = get_client()
        if client.is_overlord_reachable():
            st.success("Overlord: Connected")
        else:
            st.error("Overlord: Unreachable")

    return page


def main() -> None:
    """Main dashboard entry point."""
    page_name = sidebar()
    client = get_client()

    # Render selected page
    render_fn = PAGES[page_name]
    render_fn(client)

    # Auto-refresh
    if st.session_state.get("auto_refresh", True):
        interval = st.session_state.get("refresh_interval", 10)
        time.sleep(interval)
        st.rerun()


if __name__ == "__main__":
    main()
