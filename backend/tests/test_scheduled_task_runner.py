from collections import deque

import pytest

from scripts.run_scheduled_task import ERROR_SUMMARY_MAX_CHARS, _error_summary, _normalized_command


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


def test_error_summary_keeps_failure_reason_instead_of_sql_parameter_tail() -> None:
    lines = deque([
        "[OK] previous source imported\n",
        '[FAILED] 2026-10-19 IntegrityError: duplicate key violates unique constraint "date_code"\n',
        "DETAIL: Key (source_date, goods_code)=(2026-10-19, SKU001) already exists.\n",
        "[SQL: INSERT INTO products ...]\n",
        "[parameters: " + "private product data" * 1000 + "]\n",
        "(Background on this error at: https://sqlalche.me/e/20/gkpj)\n",
        "[SUMMARY] imported=0 failed=1\n",
    ])
    summary = _error_summary(lines)
    assert summary.startswith("[FAILED] 2026-10-19 IntegrityError")
    assert "SKU001" in summary
    assert "previous source" not in summary
    assert "private product data" not in summary
    assert "[SQL:" not in summary


def test_error_summary_preserves_last_exception_and_details() -> None:
    lines = deque([
        "Traceback (most recent call last):\n",
        "ValueError: first failure\n",
        "During handling of the above exception, another exception occurred:\n",
        "sqlalchemy.exc.IntegrityError: (psycopg.errors.UniqueViolation) duplicate key\n",
        "DETAIL: existing key\n",
        "[SQL: INSERT INTO products ...]\n",
        "[parameters: omitted]\n",
    ])
    assert _error_summary(lines) == "sqlalchemy.exc.IntegrityError: (psycopg.errors.UniqueViolation) duplicate key\nDETAIL: existing key"


def test_error_summary_keeps_start_when_message_exceeds_limit() -> None:
    summary = _error_summary(deque(["RuntimeError: root cause " + "x" * 10000]))
    assert len(summary) <= ERROR_SUMMARY_MAX_CHARS
    assert summary.startswith("RuntimeError: root cause")
    assert summary.endswith("完整内容请查看任务日志")
