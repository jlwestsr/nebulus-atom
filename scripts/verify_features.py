import asyncio
import os
import shutil
from rich.console import Console
from mini_nebulus.config import Config
from mini_nebulus.services.file_service import FileService
from mini_nebulus.services.rag_service import RagService
from mini_nebulus.services.skill_service import SkillService
from mini_nebulus.services.task_service import TaskService
from mini_nebulus.services.openai_service import OpenAIService

console = Console()


def print_result(name, success, message=""):
    style = "green" if success else "red"
    status = "PASS" if success else "FAIL"
    console.print(f"[{style}][{status}] {name}[/{style}] {message}")


async def main():
    console.rule("[bold blue]Mini-Nebulus Feature Verification")

    # 1. Config & Setup
    print_result(
        "Config Loading",
        Config.NEBULUS_BASE_URL is not None,
        f"Base URL: {Config.NEBULUS_BASE_URL}",
    )

    # 2. File Service
    file_service = FileService()
    files = file_service.list_dir("mini_nebulus")
    print_result(
        "FileService.list_files", len(files) > 0, f"Found {len(files)} files/dirs"
    )

    # 3. RAG Service
    # Use a temp directory for DB testing to avoid messing with real DB if it exists
    test_db_path = "./.mini_nebulus_test_db"
    if os.path.exists(test_db_path):
        shutil.rmtree(test_db_path)

    try:
        # Note: RagService.__init__ takes db_path
        rag_service = RagService(db_path=test_db_path)

        # We need to manually add docs for testing since index_codebase walks the FS
        # But RagService only exposes index_codebase and search_code publicly effectively?
        # Let's use index_codebase on a small subdir like 'tests'
        result_msg = rag_service.index_codebase(root_dir="tests")
        print_result("RagService.index_codebase", "Indexed" in result_msg, result_msg)

        # Querying
        results = rag_service.search_code("test", n_results=1)
        success = len(results) > 0
        print_result("RagService.search_code", success, f"Result count: {len(results)}")
    except Exception as e:
        print_result("RagService", False, str(e))
    finally:
        if os.path.exists(test_db_path):
            shutil.rmtree(test_db_path)

    # 4. Skill Service
    skill_service = SkillService()
    skill_service.load_skills()
    skills = skill_service.skills
    has_file_info = "file_info" in skills
    print_result(
        "SkillService.discovery", has_file_info, f"Skills: {list(skills.keys())}"
    )

    if has_file_info:
        try:
            # Test executing file_info on CONTEXT.md
            # execute_skill expects args as a dict
            result = skill_service.execute_skill(
                "file_info", {"path": os.path.abspath("CONTEXT.md")}
            )
            print_result(
                "SkillService.execute(file_info)",
                "file_size" in str(result),
                f"Output: {result}",
            )
        except Exception as e:
            print_result("SkillService.execute", False, str(e))

    # 5. Task Service
    task_service = TaskService()
    task_service.create_plan("Verification Goal")
    t = task_service.add_task("Test task")
    all_tasks = task_service.current_plan.tasks
    print_result(
        "TaskService.add_task",
        len(all_tasks) == 1 and all_tasks[0].id == t.id,
        f"TaskId: {t.id}",
    )

    # 6. OpenAI Service (Connectivity Check)
    # We won't make a real call to avoid cost/latency, just check client init
    try:
        openai_service = OpenAIService()
        print_result(
            "OpenAIService.init",
            openai_service.client is not None,
            "Client initialized",
        )
    except Exception as e:
        print_result("OpenAIService.init", False, str(e))


if __name__ == "__main__":
    asyncio.run(main())
