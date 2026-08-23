from collections import deque

import pytest

from scripts.run_scheduled_task import _error_summary, _normalized_command


def test_normalized_command_removes_separator() -> None:
    assert _normalized_command(["--", "python", "-m", "scripts.example"]) == [
        "python",
        "-m",
        "scripts.example",
    ]


def test_normalized_command_requires_target() -> None:
    with pytest.raises(ValueError, match="command is required"):
        _normalized_command(["--"])


def test_error_summary_uses_recent_output() -> None:
    lines = deque(["old\n", "Traceback\n", "failure detail\n"])
    assert _error_summary(lines) == "old\nTraceback\nfailure detail"
    assert _error_summary(deque()) is None
