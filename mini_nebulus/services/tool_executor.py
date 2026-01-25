import subprocess
import asyncio


class ToolExecutor:
    @staticmethod
    async def execute(command: str) -> str:
        try:
            process = await asyncio.create_subprocess_shell(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            output = stdout.decode().strip()
            if stderr:
                output += "\n" + stderr.decode().strip()

            return output if output.strip() else "(no output)"
        except Exception as e:
            return f"Error: {str(e)}"
