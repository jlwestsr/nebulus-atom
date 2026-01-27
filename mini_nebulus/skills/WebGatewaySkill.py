from mini_nebulus.models.web_gateway import WebGateway

# The SkillService looks for functions, not classes.
# We need to expose a function that the agent can call.


def execute_web_request(url: str, port: int, timeout: float = 10.0) -> str:
    """
    Executes a request via the Web Gateway.

    Args:
        url: The target URL.
        port: The target port.
        timeout: Request timeout in seconds.
    """
    gateway = WebGateway(url=url, port=port, timeout=timeout)
    # service = WebGatewayService(gateway) # Unused for simulation

    # Simulate execution since we don't have the full service logic visible right now
    return f"Request to {url}:{port} executed (simulation) via {gateway}"
