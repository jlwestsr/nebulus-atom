import os
from datetime import datetime


def file_info(path):
    file_stat = os.stat(path)
    return {
        "file_size": f"{file_stat.st_size} bytes",
        "last_modified": datetime.fromtimestamp(file_stat.st_mtime).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    }
