from mini_nebulus.models.web_gateway import WebGateway
from mini_nebulus.services.web_gateway_service import WebGatewayService


class WebGatewaySkill:
    def execute(self, gateway: WebGateway):
        service = WebGatewayService()
        return service.execute_request(gateway)
