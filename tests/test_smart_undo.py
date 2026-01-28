import time
import pytest
import os
import shutil
from mini_nebulus.services.checkpoint_service import CheckpointService


@pytest.fixture
def clean_env():
    # Setup test dir
    test_dir = "test_smart_undo_dir"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)

    # Switch to test dir
    original_cwd = os.getcwd()
    os.chdir(test_dir)

    # Create checkpoint dir
    os.makedirs(".mini_nebulus/checkpoints", exist_ok=True)

    yield

    # Cleanup
    os.chdir(original_cwd)
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)


def test_checkpoint_lifecycle(clean_env):
    service = CheckpointService()

    # 1. Create a file
    with open("test_file.txt", "w") as f:
        f.write("Original Content")

    # 2. Create Checkpoint
    result = service.create_checkpoint("v1")
    assert "Checkpoint created" in result

    # 3. Modify File
    with open("test_file.txt", "w") as f:
        f.write("Modified Content")

    assert open("test_file.txt").read() == "Modified Content"

    # 4. Rollback
    result = service.rollback_checkpoint("v1")
    assert "Rollback successful" in result

    # 5. Verify Restore
    assert open("test_file.txt").read() == "Original Content"


def test_list_checkpoints(clean_env):
    service = CheckpointService()
    service.create_checkpoint("alpha")
    time.sleep(1)  # Ensure timestamp diff
    service.create_checkpoint("beta")

    listing = service.list_checkpoints()
    assert "alpha" in listing
    assert "beta" in listing
    assert "ID:" in listing
