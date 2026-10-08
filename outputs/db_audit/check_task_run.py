import sys
sys.path.insert(0, r"E:\hede\backend")
from config import load_settings
from sqlalchemy import create_engine
s = load_settings(require_database=True)
with create_engine(s.database_url).connect() as c:
    c = c.execution_options(isolation_level="AUTOCOMMIT")
    for r in c.exec_driver_sql("""
        SELECT task_name, status, exit_code, started_at, finished_at, duration_ms
        FROM scheduled_task_runs WHERE task_name='HedeDatabaseMissingDataReview'
        ORDER BY id DESC LIMIT 3""").fetchall():
        print("运行记录:", r)
    for r in c.exec_driver_sql("""
        SELECT task_name, status, last_run_at, last_exit_code
        FROM scheduled_task_statuses WHERE task_name='HedeDatabaseMissingDataReview'""").fetchall():
        print("任务状态:", r)
