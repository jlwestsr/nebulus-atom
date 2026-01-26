import unittest
from mini_nebulus.services.task_service import TaskService


class TestTaskGraph(unittest.TestCase):
    def test_dependency_structure(self):
        service = TaskService()
        service.create_plan("Build a house")

        # Create tasks
        task_a = service.add_task("Lay foundation")
        task_b = service.add_task("Build walls", dependencies=[task_a.id])
        task_c = service.add_task("Build roof", dependencies=[task_b.id])

        data = service.get_plan_data()
        tasks = {t["id"]: t for t in data["tasks"]}

        # Verify dependencies are stored
        self.assertEqual(tasks[task_a.id]["dependencies"], [])
        self.assertEqual(tasks[task_b.id]["dependencies"], [task_a.id])
        self.assertEqual(tasks[task_c.id]["dependencies"], [task_b.id])

        # Verify tree logic (simulated)
        # Roots should be tasks with no dependencies
        roots = [t for t in data["tasks"] if not t.get("dependencies")]
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0]["id"], task_a.id)

        # Dependents of A
        deps_a = [t for t in data["tasks"] if task_a.id in t.get("dependencies", [])]
        self.assertEqual(len(deps_a), 1)
        self.assertEqual(deps_a[0]["id"], task_b.id)


if __name__ == "__main__":
    unittest.main()
