from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class WebGateway:
    endpoint: str
    method: str = "GET"
    payload: Optional[Dict[str, Any]] = None
    headers: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        self.method = self.method.upper()
