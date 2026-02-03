import unittest
from unittest.mock import patch
from nebulus_atom.services.context_service import ContextService, ContextServiceManager


class TestContextService(unittest.TestCase):
    def test_pin_file(self):
        service = ContextService()
        # Mock os.path.exists
        with patch("os.path.exists", return_value=True):
            result = service.pin_file("test.txt")
            self.assertIn("Pinned test.txt", result)
            self.assertIn("test.txt", service.list_context())

    def test_unpin_file(self):
        service = ContextService()
        with patch("os.path.exists", return_value=True):
            service.pin_file("test.txt")
            result = service.unpin_file("test.txt")
            self.assertIn("Unpinned test.txt", result)
            self.assertNotIn("test.txt", service.list_context())

    def test_manager_sessions(self):
        manager = ContextServiceManager()
        s1 = manager.get_service("session1")
        s2 = manager.get_service("session2")

        self.assertNotEqual(s1, s2)

        with patch("os.path.exists", return_value=True):
            s1.pin_file("file1.txt")
            self.assertIn("file1.txt", s1.list_context())
            self.assertNotIn("file1.txt", s2.list_context())

    def test_context_truncation(self):
        service = ContextService()
        # Reduce MAX_CONTEXT_CHARS for testing, but enough for headers
        # Headers are approx 30-40 chars each, plus initial context header ~40
        # Total overhead ~110-120 chars. Set limit to 200 to allow ~80 chars of content
        service.MAX_CONTEXT_CHARS = 200

        with (
            patch("os.path.exists", return_value=True),
            patch(
                "nebulus_atom.services.file_service.FileService.read_file"
            ) as mock_read,
        ):
            # File content is 300 chars, limit allows only ~80
            mock_read.return_value = "A" * 300

            service.pin_file("large_file.txt")
            context = service.get_context_string()

            self.assertIn("large_file.txt", context)
            self.assertIn("TRUNCATED DUE TO LENGTH LIMIT", context)
            self.assertLess(
                len(context), 350
            )  # Should be roughly 200 + overhead of truncate msg


if __name__ == "__main__":
    unittest.main()
