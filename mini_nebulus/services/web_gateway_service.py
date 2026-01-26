import requests
from mini_nebulus.models.web_gateway import WebGateway


class WebGatewayService:
    def execute_request(self, gateway: WebGateway):
        try:
            response = requests.request(
                method=gateway.method,
                url=gateway.endpoint,
                json=gateway.payload,
                headers=gateway.headers,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return f"Error: {str(e)}"
