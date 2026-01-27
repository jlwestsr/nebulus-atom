from mini_nebulus.models.web_gateway import WebGateway


class WebGatewayService:
    def __init__(self, gateway: WebGateway):
        self.gateway = gateway
