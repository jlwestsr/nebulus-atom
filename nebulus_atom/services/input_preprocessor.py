import re
from pathlib import Path


class InputPreprocessor:
    @staticmethod
    def process(user_input: str) -> str:
        regex = r"@([a-zA-Z0-9_./-]+)"
        matches = re.finditer(regex, user_input)

        file_contents = []

        for m in matches:
            file_path = m.group(1)
            try:
                resolved_path = Path.cwd() / file_path
                if resolved_path.is_file():
                    content = resolved_path.read_text(encoding="utf-8")
                    file_contents.append(
                        f"\n--- Content from {file_path} ---\n{content}\n--- End of {file_path} ---\n"
                    )
                    print(f"✔ Read file: {file_path}")
                else:
                    print(f"⚠ Warning: {file_path} is not a file.")
            except Exception as e:
                print(f"⚠ Warning: Could not read {file_path}: {e}")

        if file_contents:
            return user_input + "\n" + "".join(file_contents)

        return user_input
