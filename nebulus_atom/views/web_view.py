from .web_gateway_service import WebGatewayService


class WebView:
    def display_status(self, service: WebGatewayService):
        return f"Gateway status: {service.gateway.url}:{service.gateway.port}"
