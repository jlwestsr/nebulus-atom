import subprocess
import asyncio
from mini_nebulus.services.file_service import FileService
from mini_nebulus.services.task_service import TaskServiceManager
from mini_nebulus.services.skill_service import SkillService
from mini_nebulus.models.task import TaskStatus


class ToolExecutor:
    task_manager = TaskServiceManager()
    skill_service = SkillService()

    @staticmethod
    def initialize():
        """Initial load of skills."""
        ToolExecutor.skill_service.load_skills()

    @staticmethod
    async def dispatch(tool_name: str, args: dict, session_id: str = "default"):
        try:
            task_service = ToolExecutor.task_manager.get_service(session_id)

            # Shell Tools
            if tool_name == "run_shell_command":
                return await ToolExecutor.run_shell_command(args.get("command"))

            # File Tools
            elif tool_name == "read_file":
                return FileService.read_file(args.get("path"))
            elif tool_name == "write_file":
                return FileService.write_file(args.get("path"), args.get("content"))
            elif tool_name == "list_dir":
                return str(FileService.list_dir(args.get("path", ".")))

            # Task Tools
            elif tool_name == "create_plan":
                plan = task_service.create_plan(args.get("goal"))
                return f"Plan created for goal: {plan.goal}. ID: {plan.id}"
            elif tool_name == "add_task":
                task = task_service.add_task(args.get("description"))
                return f"Task added: {task.description}. ID: {task.id}"
            elif tool_name == "update_task":
                status_str = args.get("status", "").upper()
                try:
                    status = TaskStatus[status_str]
                except KeyError:
                    return f"Invalid status: {status_str}. Valid: {list(TaskStatus.__members__.keys())}"

                task_service.update_task_status(
                    args.get("task_id"), status, args.get("result", "")
                )
                return f"Task {args.get('task_id')} updated to {status.value}"
            elif tool_name == "get_plan":
                return task_service.get_plan_data()

            # Skill Tools
            elif tool_name == "create_skill":
                name = args.get("name")
                code = args.get("code")
                filename = f"mini_nebulus/skills/{name}.py"
                FileService.write_file(filename, code)
                ToolExecutor.skill_service.load_skills()  # Hot reload
                return f"Skill {name} created and loaded from {filename}"

            elif tool_name == "refresh_skills":
                ToolExecutor.skill_service.load_skills()
                return "Skills reloaded."

            # Dynamic Skills
            elif tool_name in ToolExecutor.skill_service.skills:
                return ToolExecutor.skill_service.execute_skill(tool_name, args)

            else:
                return f"Unknown tool: {tool_name}"
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    @staticmethod
    async def run_shell_command(command: str) -> str:
        if not command:
            return "Error: No command provided"
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
