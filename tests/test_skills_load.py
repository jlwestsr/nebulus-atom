import pytest
from nebulus_atom.services.skill_service import SkillService
from nebulus_atom.models.web_gateway import WebGateway


def test_web_gateway_import():
    """Verify WebGateway and Service can be imported and instantiated."""
    try:
        from nebulus_atom.services.web_gateway_service import WebGatewayService

        gateway = WebGateway(url="http://test", port=8080)
        service = WebGatewayService(gateway)
        assert service.gateway.url == "http://test"
    except ImportError as e:
        pytest.fail(f"Failed to import WebGatewayService: {e}")


def test_skill_loading():
    """Verify that SkillService can load all defined skills without error."""
    skill_service = SkillService()
    # This triggers dynamic loading of files in nebulus_atom/skills/
    skill_service.load_skills()

    # We expect at least the built-in skills (Forge, WebGateway, etc.)
    assert len(skill_service.skills) > 0
    # Check for the function name we just exposed
    assert "execute_web_request" in skill_service.skills
