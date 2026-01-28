import pytest
import os
from mini_nebulus.services.preference_service import PreferenceService


@pytest.fixture
def clean_prefs():
    path = ".mini_nebulus/test_preferences.json"
    if os.path.exists(path):
        os.remove(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_preference_persistence(clean_prefs):
    service = PreferenceService(clean_prefs)
    service.set_preference("language", "python")

    assert os.path.exists(clean_prefs)

    # Reload
    service2 = PreferenceService(clean_prefs)
    assert service2.get_preference("language") == "python"


def test_context_string(clean_prefs):
    service = PreferenceService(clean_prefs)
    service.set_preference("style", "concise")

    context = service.get_context_string()
    assert "### USER PREFERENCES ###" in context
    assert "- style: concise" in context
