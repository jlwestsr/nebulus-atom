# mini_nebulus/views/web_view.py
from typing import Dict, Any
from mini_nebulus.models.web_gateway import WebGateway
from mini_nebulus.services.web_gateway_service import WebGatewayService


class WebView:
    def __init__(self):
        self.service = WebGatewayService()

    def handle_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        endpoint = payload.get("endpoint")
        if not endpoint:
            return {"error": "Missing endpoint", "status": 400}

        gateway = WebGateway(
            endpoint=endpoint,
            method=payload.get("method", "GET"),
            payload=payload.get("data"),
            headers=payload.get("headers", {}),
        )

        result = self.service.execute_request(gateway)
        return {"data": result, "status": 200}
