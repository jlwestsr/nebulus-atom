import unittest
from mini_nebulus.services.context_service import ContextService, ContextServiceManager


class TestContextService(unittest.TestCase):
    def test_pin_file(self):
        service = ContextService()
        # Mock os.path.exists
        with unittest.mock.patch("os.path.exists", return_value=True):
            result = service.pin_file("test.txt")
            self.assertIn("Pinned test.txt", result)
            self.assertIn("test.txt", service.list_context())

    def test_unpin_file(self):
        service = ContextService()
        with unittest.mock.patch("os.path.exists", return_value=True):
            service.pin_file("test.txt")
            result = service.unpin_file("test.txt")
            self.assertIn("Unpinned test.txt", result)
            self.assertNotIn("test.txt", service.list_context())

    def test_manager_sessions(self):
        manager = ContextServiceManager()
        s1 = manager.get_service("session1")
        s2 = manager.get_service("session2")

        self.assertNotEqual(s1, s2)

        with unittest.mock.patch("os.path.exists", return_value=True):
            s1.pin_file("file1.txt")
            self.assertIn("file1.txt", s1.list_context())
            self.assertNotIn("file1.txt", s2.list_context())


if __name__ == "__main__":
    unittest.main()
