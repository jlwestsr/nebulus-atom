import subprocess
import asyncio
from mini_nebulus.services.file_service import FileService
from mini_nebulus.services.task_service import TaskServiceManager
from mini_nebulus.services.skill_service import SkillService
from mini_nebulus.services.context_service import ContextServiceManager
from mini_nebulus.services.checkpoint_service import CheckpointServiceManager
from mini_nebulus.services.rag_service import RagServiceManager
from mini_nebulus.services.mcp_service import MCPService
from mini_nebulus.services.preference_service import PreferenceServiceManager
from mini_nebulus.services.doc_service import DocServiceManager
from mini_nebulus.services.image_service import ImageServiceManager
from mini_nebulus.services.journal_service import JournalServiceManager
from mini_nebulus.services.ast_service import ASTServiceManager
from mini_nebulus.services.macro_service import MacroServiceManager
from mini_nebulus.services.docker_service import DockerServiceManager
from mini_nebulus.services.error_recovery_service import ErrorRecoveryServiceManager
from mini_nebulus.models.task import TaskStatus
from mini_nebulus.utils.logger import setup_logger

logger = setup_logger(__name__)


class ToolExecutor:
    task_manager = TaskServiceManager()
    context_manager = ContextServiceManager()
    skill_service = SkillService()
    checkpoint_manager = CheckpointServiceManager()
    rag_manager = RagServiceManager()
    mcp_service = MCPService()
    preference_manager = PreferenceServiceManager()
    doc_manager = DocServiceManager()
    image_manager = ImageServiceManager()
    journal_manager = JournalServiceManager()
    ast_manager = ASTServiceManager()
    macro_manager = MacroServiceManager()
    history_manager = None  # Set by AgentController
    docker_manager = DockerServiceManager()
    recovery_manager = ErrorRecoveryServiceManager()

    @staticmethod
    def initialize():
        """Initial load of skills."""
        ToolExecutor.skill_service.load_skills()

    @staticmethod
    async def dispatch(tool_name: str, args: dict, session_id: str = "default"):
        logger.info(
            f"Dispatching tool '{tool_name}' with args: {str(args)[:200]}..."
        )  # Truncate args for log safety
        try:
            task_service = ToolExecutor.task_manager.get_service(session_id)
            context_service = ToolExecutor.context_manager.get_service(session_id)
            checkpoint_service = ToolExecutor.checkpoint_manager.get_service(session_id)
            rag_service = ToolExecutor.rag_manager.get_service(session_id)

            # Auto-Checkpoint for destructive operations
            if tool_name == "write_file":
                checkpoint_service.create_checkpoint(label=f"auto_before_{tool_name}")

            # Shell Tools
            if tool_name == "run_shell_command":
                docker_service = ToolExecutor.docker_manager.get_service(session_id)
                if docker_service.enabled:
                    return docker_service.execute_command(args.get("command"))
                return await ToolExecutor.run_shell_command(args.get("command"))

            # File Tools
            elif tool_name == "read_file":
                return FileService.read_file(args.get("path"))
            elif tool_name == "write_file":
                return FileService.write_file(args.get("path"), args.get("content"))
            elif tool_name == "list_dir":
                return str(FileService.list_dir(args.get("path", ".")))

            # Context Tools
            elif tool_name == "pin_file":
                return context_service.pin_file(args.get("path"))
            elif tool_name == "unpin_file":
                return context_service.unpin_file(args.get("path"))
            elif tool_name == "list_context":
                return str(context_service.list_context())

            # Checkpoint Tools
            elif tool_name == "create_checkpoint":
                return checkpoint_service.create_checkpoint(args.get("label", "manual"))
            elif tool_name == "rollback_checkpoint":
                return checkpoint_service.rollback_checkpoint(args.get("id"))
            elif tool_name == "list_checkpoints":
                return checkpoint_service.list_checkpoints()

            # RAG Tools
            elif tool_name == "index_codebase":
                return await rag_service.index_codebase()
            elif tool_name == "search_code" or tool_name == "search_knowledge":
                return str(await rag_service.search_code(args.get("query")))
            elif tool_name == "search_history" or tool_name == "search_memory":
                return str(await rag_service.search_history(args.get("query")))

            # Task Tools
            elif tool_name == "create_plan":
                plan = task_service.create_plan(args.get("goal"))
                return f"Plan created for goal: {plan.goal}. ID: {plan.id}"
            elif tool_name == "add_task" or tool_name == "create_task":
                task = task_service.add_task(
                    args.get("description"), args.get("dependencies")
                )
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

            # Doc Tools
            elif tool_name == "list_docs":
                doc_service = ToolExecutor.doc_manager.get_service(session_id)
                return str(doc_service.list_docs())
            elif tool_name == "read_doc":
                doc_service = ToolExecutor.doc_manager.get_service(session_id)
                content = doc_service.read_doc(args.get("path"))
                return content if content else "Error: Doc not found"

            # Preference Tools
            elif tool_name == "set_preference":
                preference_service = ToolExecutor.preference_manager.get_service(
                    session_id
                )
                return preference_service.set_preference(
                    args.get("key"), args.get("value")
                )
            elif tool_name == "get_preference":
                preference_service = ToolExecutor.preference_manager.get_service(
                    session_id
                )
                return str(preference_service.get_preference(args.get("key")))

            # Image Tools
            elif tool_name == "scan_image":
                image_service = ToolExecutor.image_manager.get_service(session_id)
                return image_service.encode_image(args.get("path"))

            # Journal Tools
            elif tool_name == "save_session_log":
                if not ToolExecutor.history_manager:
                    return "Error: History manager not initialized."
                journal_service = ToolExecutor.journal_manager.get_service(session_id)
                task_service = ToolExecutor.task_manager.get_service(session_id)
                history = ToolExecutor.history_manager.get_session(session_id)
                return journal_service.generate_journal(
                    session_id, task_service, history
                )

            # Codebase Tools
            elif tool_name == "map_codebase":
                ast_service = ToolExecutor.ast_manager.get_service(session_id)
                return str(ast_service.generate_map(args.get("target_dir")))
            elif tool_name == "find_symbol":
                ast_service = ToolExecutor.ast_manager.get_service(session_id)
                return str(ast_service.find_symbol(args.get("symbol")))

            # Macro Tools
            elif tool_name == "create_macro":
                macro_service = ToolExecutor.macro_manager.get_service(session_id)
                return macro_service.create_macro(
                    args.get("name"), args.get("commands"), args.get("description", "")
                )

            # Skill Tools
            elif tool_name == "create_skill":
                name = args.get("name")
                code = args.get("code")
                filename = f"mini_nebulus/skills/{name}.py"
                FileService.write_file(filename, code)
                ToolExecutor.skill_service.load_skills()  # Hot reload
                return f"Skill {name} created and loaded from {filename}"
            elif tool_name == "publish_skill":
                return ToolExecutor.skill_service.publish_skill(args.get("name"))
            elif tool_name == "refresh_skills":
                ToolExecutor.skill_service.load_skills()
                return "Skills reloaded."

            # MCP Tools
            elif tool_name == "connect_mcp_server":
                return await ToolExecutor.mcp_service.connect_server(
                    args.get("name"),
                    args.get("command"),
                    args.get("args", []),
                    args.get("env"),
                )
            elif tool_name.startswith("mcp__"):
                return await ToolExecutor.mcp_service.call_tool(tool_name, args)

            # Dynamic Skills
            elif tool_name in ToolExecutor.skill_service.skills:
                return ToolExecutor.skill_service.execute_skill(tool_name, args)

            else:
                logger.warning(f"Attempted to execute unknown tool: {tool_name}")
                return f"Unknown tool: {tool_name}"
        except Exception as e:
            logger.error(f"Error executing {tool_name}: {str(e)}", exc_info=True)
            try:
                recovery_service = ToolExecutor.recovery_manager.get_service(session_id)
                return recovery_service.analyze_error(tool_name, str(e), args)
            except Exception as e2:
                logger.error(f"CRITICAL: Recovery Service Failed: {e2}", exc_info=True)
                # Fallback to standard error message
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
