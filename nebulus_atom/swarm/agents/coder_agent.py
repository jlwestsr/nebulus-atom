from nebulus_atom.controllers.agent_controller import AgentController


class CoderAgent(AgentController):
    """
    Wrapper around the existing AgentController to make it compatible with Swarm.
    Inherits directly from AgentController to reuse all tools and logic.
    """

    def __init__(self, view=None):
        super().__init__(view)
        # Eventually we customize the system prompt here
