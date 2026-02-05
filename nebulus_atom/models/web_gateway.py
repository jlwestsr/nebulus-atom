from dataclasses import dataclass


@dataclass
class WebGateway:
    url: str
    port: int
    timeout: float = 10.0
