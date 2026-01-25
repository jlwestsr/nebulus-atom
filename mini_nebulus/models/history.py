from typing import List, Dict, Optional, Any


class History:
    def __init__(self, system_prompt: str):
        self.messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]

    def add(
        self,
        role: str,
        content: Optional[str] = None,
        tool_calls: Optional[List[Dict]] = None,
        tool_call_id: Optional[str] = None,
    ):
        message = {"role": role}

        if role == "assistant" and content is None:
            message["content"] = None
        elif content is not None:
            message["content"] = content

        if tool_calls:
            message["tool_calls"] = tool_calls
        if tool_call_id:
            message["tool_call_id"] = tool_call_id

        self.messages.append(message)

    def get(self) -> List[Dict[str, Any]]:
        return self.messages


class HistoryManager:
    """Manages multiple History instances keyed by session_id."""

    def __init__(self, system_prompt: str):
        self.system_prompt = system_prompt
        self.sessions: Dict[str, History] = {}

    def get_session(self, session_id: str) -> History:
        if session_id not in self.sessions:
            self.sessions[session_id] = History(self.system_prompt)
        return self.sessions[session_id]
