from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    logs_dir = backend_dir / "logs"
    logs_dir.mkdir(exist_ok=True)

    out_log = logs_dir / "fine_table_history_import.out.log"
    err_log = logs_dir / "fine_table_history_import.err.log"
    pid_file = logs_dir / "fine_table_history_import.pid"

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    with out_log.open("ab", buffering=0) as stdout, err_log.open("ab", buffering=0) as stderr:
        process = subprocess.Popen(
            [sys.executable, "scripts/import_fine_table_history_snapshots.py"],
            cwd=backend_dir,
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
        )

    pid_file.write_text(str(process.pid), encoding="utf-8")
    print(f"started pid={process.pid}")
    print(f"stdout={out_log}")
    print(f"stderr={err_log}")


if __name__ == "__main__":
    main()
