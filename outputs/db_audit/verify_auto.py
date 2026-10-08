import subprocess
def run(*a):
    r = subprocess.run(["schtasks"] + list(a), capture_output=True)
    b = r.stdout
    if b[:2] == b"\xff\xfe": return b.decode("utf-16-le", errors="replace")
    try: return b.decode("utf-8")
    except Exception: return b.decode("utf-16", errors="replace")

xml = run("/query", "/tn", "HedeDatabaseMissingDataReview", "/xml")
print("=== 注册后的任务 XML（关键字段）===")
for line in xml.splitlines():
    s = line.strip()
    if s.startswith(("<Enabled>", "<StartWhenAvailable>", "<LogonType>", "<DisallowStartIfOnBatteries>",
                     "<StopIfGoingOnBatteries>", "<MultipleInstancesPolicy>", "<ExecutionTimeLimit>",
                     "<StartBoundary>", "<Monday", "<WeeksInterval>", "<Command>", "<ScheduledTaskState>")):
        print("   ", s)
