import streamlit as st
import sqlite3
import pandas as pd
import json
import os

DB_PATH = "nebulus_atom/data/telemetry.db"

st.set_page_config(
    page_title="Nebulus Atom Flight Recorder",
    page_icon="🤖",
    layout="wide",
)


def load_data(query, params=()):
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(query, conn, params=params)


def render_overview():
    st.header("Mission Control: Overview")

    # Check if DB exists
    if not os.path.exists(DB_PATH):
        st.error(f"Telemetry database not found at {DB_PATH}")
        return

    # Basic Metrics
    try:
        session_count = load_data(
            "SELECT COUNT(DISTINCT session_id) as count FROM events"
        ).iloc[0]["count"]
        event_count = load_data("SELECT COUNT(*) as count FROM events").iloc[0]["count"]

        col1, col2 = st.columns(2)
        col1.metric("Total Sessions", session_count)
        col2.metric("Total Events Logged", event_count)
    except Exception as e:
        st.error(f"Error loading metrics: {e}")

    st.subheader("Recent Activity")
    recent_events = load_data(
        "SELECT timestamp, session_id, event_type, content FROM events ORDER BY timestamp DESC LIMIT 20"
    )
    st.dataframe(recent_events)


def render_session_inspector():
    st.header("Session Inspector")

    if not os.path.exists(DB_PATH):
        st.warning("No data found.")
        return

    sessions = load_data(
        "SELECT DISTINCT session_id FROM events ORDER BY timestamp DESC"
    )
    if sessions.empty:
        st.info("No recorded sessions.")
        return

    session_id = st.selectbox("Select Session", sessions["session_id"])

    events = load_data(
        "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp ASC",
        params=(session_id,),
    )

    for _, event in events.iterrows():
        try:
            content = json.loads(event["content"])
        except Exception:
            content = event["content"]

        with st.chat_message(
            "assistant" if event["event_type"] == "THOUGHT" else "system"
        ):
            st.write(f"**{event['event_type']}** ({event['timestamp']})")
            st.json(content)


def render_skills():
    st.header("Dynamic Skill Library")
    skill_dir = "nebulus_atom/skills"

    if not os.path.exists(skill_dir):
        st.warning("No skills directory found.")
        return

    skills = [
        f for f in os.listdir(skill_dir) if f.endswith(".py") and f != "__init__.py"
    ]

    if not skills:
        st.info("No custom skills created yet.")
        return

    selected_skill = st.selectbox("Select Skill", skills)
    if selected_skill:
        with open(os.path.join(skill_dir, selected_skill), "r") as f:
            code = f.read()
        st.code(code, language="python")


# Sidebar Navigation
page = st.sidebar.radio(
    "Navigation", ["Overview", "Session Inspector", "Skill Library"]
)

if page == "Overview":
    render_overview()
elif page == "Session Inspector":
    render_session_inspector()
elif page == "Skill Library":
    render_skills()
