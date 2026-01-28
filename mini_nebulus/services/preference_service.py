import os
import json
from typing import Dict, Any, Optional
from mini_nebulus.utils.logger import setup_logger

logger = setup_logger(__name__)


class PreferenceService:
    def __init__(self, storage_path: str = ".mini_nebulus/preferences.json"):
        self.storage_path = os.path.join(os.getcwd(), storage_path)
        self.preferences: Dict[str, Any] = {}
        self._load_preferences()

    def _load_preferences(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    self.preferences = json.load(f)
                logger.info(f"Loaded preferences from {self.storage_path}")
            except Exception as e:
                logger.error(f"Failed to load preferences: {e}")
                self.preferences = {}
        else:
            self.preferences = {}

    def _save_preferences(self):
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, "w") as f:
                json.dump(self.preferences, f, indent=2)
            logger.info(f"Saved preferences to {self.storage_path}")
        except Exception as e:
            logger.error(f"Failed to save preferences: {e}")

    def set_preference(self, key: str, value: Any) -> str:
        self.preferences[key] = value
        self._save_preferences()
        return f"Preference '{key}' set to '{value}'"

    def get_preference(self, key: str) -> Optional[Any]:
        return self.preferences.get(key)

    def get_all_preferences(self) -> Dict[str, Any]:
        return self.preferences

    def get_context_string(self) -> str:
        # Returns a string formatted for the system prompt.
        if not self.preferences:
            return ""

        lines = ["### USER PREFERENCES ###"]
        for k, v in self.preferences.items():
            lines.append(f"- {k}: {v}")
        return "\n".join(lines) + "\n"


class PreferenceServiceManager:
    def __init__(self):
        self.service = None

    def get_service(self, session_id: str = "default") -> PreferenceService:
        # Preferences are global/user-specific, not session-specific for now.
        if not self.service:
            self.service = PreferenceService()
        return self.service
