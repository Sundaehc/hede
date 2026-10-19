from datetime import datetime, timedelta, timezone
import logging
import os
import socket

from sqlalchemy import select, update

from domain.task_status_schema import SCHEDULED_TASK_RUN_TABLE


logger = logging.getLogger(__name__)
INTERRUPTED_RUN_MESSAGE = (
    "任务执行器已退出，未记录完整执行结果；请查看业务日期状态和日志确认各步骤。"
    "本条结束时间为发现时间，非实际退出时间，不代表已回滚或全部成功。"
)


def process_matches_run(process_id: int, started_at: datetime) -> bool | None:
    if process_id <= 0:
        return None
    if os.name != "nt":
        try:
            os.kill(process_id, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return None
        return True

    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    kernel.GetProcessTimes.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, process_id)
    if not handle:
        return False if ctypes.get_last_error() == 87 else None
    try:
        exit_code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return None
        if exit_code.value != 259:
            return False
        created, exited, kernel_time, user_time = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                      ctypes.byref(kernel_time), ctypes.byref(user_time)):
            return None
        timestamp = ((created.dwHighDateTime << 32) + created.dwLowDateTime) / 10_000_000 - 11_644_473_600
        process_started_at = datetime.fromtimestamp(timestamp, timezone.utc)
        return process_started_at <= started_at + timedelta(seconds=5)
    finally:
        kernel.CloseHandle(handle)


def reconcile_local_task_runs(engine, *, now: datetime | None = None, task_name: str | None = None) -> int:
    observed_at = now or datetime.now(timezone.utc)
    table = SCHEDULED_TASK_RUN_TABLE
    conditions = [
        table.c.status == "running",
        table.c.host_name == socket.gethostname(),
        table.c.process_id.is_not(None),
        table.c.started_at < observed_at - timedelta(minutes=2),
    ]
    if task_name:
        conditions.append(table.c.task_name == task_name)
    with engine.connect() as connection:
        candidates = connection.execute(select(table).where(*conditions)).mappings().all()
    recovered = 0
    for row in candidates:
        started_at = row["started_at"]
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        if process_matches_run(row["process_id"], started_at) is not False:
            continue
        with engine.begin() as connection:
            changed = connection.execute(update(table).where(
                table.c.id == row["id"], table.c.status == "running",
                table.c.process_id == row["process_id"], table.c.started_at == row["started_at"],
            ).values(status="failed", finished_at=observed_at, duration_ms=None, exit_code=-1,
                     error_summary=INTERRUPTED_RUN_MESSAGE)).rowcount
        recovered += changed
        if changed:
            logger.warning("Recovered interrupted scheduled task run %s: task=%s process=%s", row["id"], row["task_name"], row["process_id"])
    return recovered
