"""Run a command while recording its execution in PostgreSQL and a log file."""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback

from config import load_settings
from storage.task_status_repository import ScheduledTaskRunRepository, ScheduledTaskStatusRepository


ERROR_SUMMARY_MAX_CHARS = 8_000
ERROR_SUMMARY_MAX_LINES = 80


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run and record a scheduled task")
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--log-file", type=Path, required=True)
    parser.add_argument("--working-directory", type=Path, default=None)
    parser.add_argument(
        "--skip-if-business-success",
        metavar="TASK_NAME",
        help="Skip this invocation when the named business task already succeeded today",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def _normalized_command(command: list[str]) -> list[str]:
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("A command is required after --")
    return command


def _error_summary(lines: deque[str]) -> str | None:
    summary = "".join(lines).strip()
    if not summary:
        return None
    return summary[-ERROR_SUMMARY_MAX_CHARS:]


def _write_line(log_handle, message: str) -> None:
    log_handle.write(message)
    if not message.endswith("\n"):
        log_handle.write("\n")
    log_handle.flush()


def main() -> int:
    args = _parser().parse_args()
    try:
        command = _normalized_command(args.command)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    log_path = args.log_file.resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command_text = subprocess.list2cmdline(command)
    started_at = datetime.now().astimezone()
    started_monotonic = time.monotonic()
    repository: ScheduledTaskRunRepository | None = None
    run_id: int | None = None

    if args.skip_if_business_success:
        try:
            settings = load_settings(require_database=True)
            assert settings.database_url is not None
            status_repository = ScheduledTaskStatusRepository(settings.database_url)
            if status_repository.is_success(
                args.skip_if_business_success,
                started_at.date(),
            ):
                message = (
                    f"[{started_at.isoformat(timespec='seconds')}] skip {args.task_name} "
                    f"because business task {args.skip_if_business_success} "
                    "already succeeded today"
                )
                with log_path.open("a", encoding="utf-8", errors="replace") as log_handle:
                    _write_line(log_handle, message)
                print(message)
                return 0
        except Exception as exc:
            with log_path.open("a", encoding="utf-8", errors="replace") as log_handle:
                _write_line(
                    log_handle,
                    f"[TASK-RUN-LOG WARNING] failed to check today's business status: "
                    f"{type(exc).__name__}: {exc}",
                )

    with log_path.open("a", encoding="utf-8", errors="replace") as log_handle:
        _write_line(
            log_handle,
            f"[{started_at.isoformat(timespec='seconds')}] start {args.task_name}",
        )
        try:
            settings = load_settings(require_database=True)
            assert settings.database_url is not None
            repository = repository or ScheduledTaskRunRepository(settings.database_url)
            run_id = repository.mark_started(
                args.task_name,
                host_name=socket.gethostname(),
                process_id=os.getpid(),
                command=command_text,
                log_path=log_path,
            )
        except Exception as exc:
            _write_line(
                log_handle,
                f"[TASK-RUN-LOG WARNING] failed to record start: {type(exc).__name__}: {exc}",
            )

        output_tail: deque[str] = deque(maxlen=ERROR_SUMMARY_MAX_LINES)
        exit_code = 1
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PYTHONUTF8"] = "1"
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
                cwd=args.working_directory,
            )
            assert process.stdout is not None
            for line in process.stdout:
                log_handle.write(line)
                log_handle.flush()
                output_tail.append(line)
            exit_code = int(process.wait())
        except Exception:
            detail = traceback.format_exc()
            _write_line(log_handle, detail)
            output_tail.append(detail)

        duration_ms = round((time.monotonic() - started_monotonic) * 1000)
        status = "success" if exit_code == 0 else "failed"
        summary = _error_summary(output_tail) if exit_code != 0 else None
        finished_at = datetime.now().astimezone()
        _write_line(
            log_handle,
            f"[{finished_at.isoformat(timespec='seconds')}] end {args.task_name} "
            f"status={status} exit_code={exit_code} duration_ms={duration_ms}",
        )

        if repository is not None and run_id is not None:
            try:
                repository.mark_finished(
                    run_id,
                    status=status,
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    error_summary=summary,
                )
            except Exception as exc:
                _write_line(
                    log_handle,
                    f"[TASK-RUN-LOG WARNING] failed to record finish: {type(exc).__name__}: {exc}",
                )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
