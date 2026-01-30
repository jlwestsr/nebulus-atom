import streamlit as st
import requests
import os
import time

# Configuration
API_URL = "http://nebulus-atom-core:8000"
WS_URL = "ws://nebulus-atom-core:8000/ws"

st.set_page_config(page_title="Nebulus Atom", page_icon="🌌", layout="wide")

# --- Security: Basic Auth ---


def check_password():
    """Returns `True` if the user had a correct password."""

    # Load secrets from Environment (Docker/OS)
    # Default to secure values if not set to prevent open access in prod
    EXPECTED_USER = os.environ.get("WEB_UI_USERNAME", "admin")
    EXPECTED_PASS = os.environ.get("WEB_UI_PASSWORD", "nebulus")

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        user_input = st.session_state["username"].strip()
        pass_input = st.session_state["password"]

        print(
            f"DEBUG: Comparing Input User '{user_input}' vs Expected '{EXPECTED_USER}'"
        )

        if user_input == EXPECTED_USER and pass_input == EXPECTED_PASS:
            print("DEBUG: Password Correct!")
            st.session_state["password_correct"] = True
            # Clear any previous error
            if "auth_error" in st.session_state:
                del st.session_state["auth_error"]
        else:
            print("DEBUG: Password Incorrect!")
            st.session_state["password_correct"] = False
            st.session_state["auth_error"] = "😕 User not known or password incorrect"

    # Create a placeholder for the login UI to allow complete cleanup
    login_placeholder = st.empty()

    with login_placeholder.container():
        # Layout: Use Columns for Width Constraint (CSS max-width is unreliable in Streamlit)
        # Ratio [1, 1, 1] -> Center column is 33% of screen width.
        col1, col2, col3 = st.columns([1, 1, 1])

        with col2:
            if "password_correct" not in st.session_state:
                # First run, show inputs
                with st.form("login_form"):
                    st.subheader("Login")
                    st.text_input("Username", key="username")
                    st.text_input("Password", type="password", key="password")
                    if st.form_submit_button("Login"):
                        password_entered()
                return False

            elif not st.session_state["password_correct"]:
                # Password not correct, show input + error
                with st.form("login_form"):
                    st.subheader("Login")
                    st.text_input("Username", key="username")
                    st.text_input("Password", type="password", key="password")
                    if st.form_submit_button("Login"):
                        password_entered()

                # Show error if set
                if "auth_error" in st.session_state:
                    st.error(st.session_state["auth_error"])
                return False

            else:
                # Password correct
                login_placeholder.empty()
                return True


if not check_password():
    st.stop()
else:
    # Explicitly clear the login placeholder on success to remove ANY ghost elements
    # Since we can't access 'login_placeholder' here easily (it's inside check_password),
    # we should have cleared it inside check_password's success block.
    # Refactoring check_password below to clean itself up.
    pass
# -----------------------------

# Custom CSS for "Gemini Dark Mode" feel
st.markdown(
    """
<style>
    /* Glassmorphism Login Card */
    [data-testid="stForm"] {
        background-color: #1e293b !important;
        border: 1px solid #334155 !important;
        padding: 3rem !important;
        border-radius: 1rem !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06) !important;

        /* STRICT WIDTH CONTROL */
        max-width: 450px !important;
        margin: 0 auto !important;
    }

    /* Center the button inside the form */
    .stButton button {
        width: 100% !important;
        background-color: #a855f7 !important;
        color: white !important;
        border: none !important;
    }

    .stApp {
        background-color: #0e1117 !important;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        display: flex;
        flex-direction: column;
    }
    .user-msg {
        background-color: #2b313e;
        border-left: 5px solid #a855f7;
    }
    .agent-msg {
        background-color: #1e293b;
        border-left: 5px solid #10b981;
    }
    .tool-output {
        font-family: monospace;
        font-size: 0.85em;
        background-color: #0f172a;
        color: #94a3b8;
        padding: 0.5rem;
        margin-top: 0.5rem;
        border-radius: 4px;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Session State
if "messages" not in st.session_state:
    st.session_state.messages = []
if "plan" not in st.session_state:
    st.session_state.plan = {}
if "logs" not in st.session_state:
    st.session_state.logs = []

# Sidebar - Plan & Status
with st.sidebar:
    st.title("🌌 Nebulus Atom")
    st.markdown("---")

    if st.session_state.plan:
        st.subheader(f"🎯 Goal: {st.session_state.plan.get('goal', 'None')}")
        tasks = st.session_state.plan.get("tasks", [])
        for task in tasks:
            icon = "⏳"
            if task["status"] == "completed":
                icon = "✅"
            elif task["status"] == "in_progress":
                icon = "🔄"
            elif task["status"] == "failed":
                icon = "❌"
            st.markdown(f"{icon} {task['description']}")
    else:
        st.info("No active plan.")

    st.markdown("---")
    st.subheader("📝 Live Logs")
    log_container = st.container(height=300)
    for log in st.session_state.logs[-20:]:  # Last 20 logs
        log_container.text(log)

# Main Chat Interface
st.header("Agent Chat")

# Render History
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(
            f"""<div class="chat-message user-msg"><b>User:</b> {msg['content']}</div>""",
            unsafe_allow_html=True,
        )
    else:
        # Check if it has tool output
        tools = msg.get("tools", [])
        tool_html = ""
        for tool in tools:
            tool_html += f"""<div class="tool-output">🔧 {tool['name']}: {tool['output'][:200]}...</div>"""

        st.markdown(
            f"""
        <div class="chat-message agent-msg">
            <b>Agent:</b> {msg['content']}
            {tool_html}
        </div>
        """,
            unsafe_allow_html=True,
        )

# Input
prompt = st.chat_input("Say something...")
if prompt:
    # Optimistic Update
    st.session_state.messages.append({"role": "user", "content": prompt})
    try:
        requests.post(f"{API_URL}/chat", json={"message": prompt})
    except Exception as e:
        st.error(f"Failed to send message: {e}")
    st.rerun()

# --- Event Logic ---


def handle_event(event):
    if event["type"] == "agent_response":
        st.session_state.messages.append(
            {"role": "assistant", "content": event["data"]["text"]}
        )

    elif event["type"] == "plan_update":
        st.session_state.plan = event["data"]

    elif event["type"] == "tool_output":
        st.session_state.logs.append(
            f"🔧 {event['data']['tool']} -> {event['data']['output'][:100]}..."
        )

    elif event["type"] == "spinner":
        status = event["data"].get("status")
        text = event["data"].get("text", "")
        if status == "start":
            st.session_state.logs.append(f"⏳ {text}")
        elif status == "stop":
            st.session_state.logs.append("✔ Done")


def poll_events():
    """Fetch pending events from API and update state."""
    try:
        response = requests.get(f"{API_URL}/events", timeout=30)
        if response.status_code == 200:
            events = response.json()
            if events:
                for event in events:
                    handle_event(event)
                return True
        else:
            st.sidebar.error(f"Poll Error: {response.status_code}")
    except Exception as e:
        st.sidebar.error(f"Poll Failed: {e}")
    return False


# --- Auto-Refresh / Polling Loop ---
if st.sidebar.toggle("Live Updates", value=True):
    st.sidebar.caption("Polling active...")
    poll_events()
    time.sleep(1)
    st.rerun()
else:
    st.sidebar.caption("Polling paused.")
    if st.sidebar.button("Manual Refresh"):
        poll_events()
        st.rerun()
