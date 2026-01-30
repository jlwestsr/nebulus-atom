from typing import Optional
from nebulus_atom.swarm.agents.base_agent import BaseAgent, logger


class RouterAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Router",
            system_prompt=(
                "You are the Router for an autonomous coding swarm.\n"
                "Your job is to classify the user's request and delegate it to the best specialist.\n\n"
                "### SPECIALISTS ###\n"
                "1. **coder**: Implementation, writing code, running commands, debugging errors.\n"
                "2. **architect**: Planning, designing, updating documentation (ROADMAP.md, implementation_plan.md).\n"
                "3. **tester**: QA, writing tests, verifying functionality.\n\n"
                "### OUTPUT FORMAT ###\n"
                'Return ONLY a JSON object: {"agent": "<name>", "reasoning": "<why>"}\n'
                'Example: {"agent": "coder", "reasoning": "User asked to write a python script."}'
            ),
        )

    async def process_turn(
        self, session_id: str, user_input: Optional[str] = None
    ) -> str:
        if not user_input:
            return '{"agent": "coder", "reasoning": "No input provided, defaulting to Coder."}'

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_input},
        ]

        logger.info(f"Router analyzing: {user_input[:50]}...")

        response = await self.openai.create_chat_completion_simple(messages)

        # Strip potential markdown code blocks
        clean_response = response.replace("```json", "").replace("```", "").strip()
        logger.info(f"Router decision: {clean_response}")
        return clean_response
