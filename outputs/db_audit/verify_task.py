import subprocess
def run(*a):
    r = subprocess.run(["schtasks"] + list(a), capture_output=True)
    b = r.stdout
    if b[:2] == b"\xff\xfe": return b.decode("utf-16-le", errors="replace")
    try: return b.decode("utf-8")
    except Exception: return b.decode("utf-16", errors="replace")

txt = run("/query", "/tn", "HedeDatabaseMissingDataReview", "/v", "/fo", "LIST")
keys = ["TaskName","Next Run Time","Status","Logon Mode","Run As User","Schedule Type",
        "Start Time","Days","Weeks","Task To Run","Start In","Repeat: Every",
        "Repeat: Until: Time","Stop Task If Runs X Hours and X Mins",
        "Start In (USD)","Power Management","Scheduled Task State","Last Run Time","Last Result"]
for line in txt.splitlines():
    if any(line.strip().startswith(k) for k in keys):
        print(line.rstrip())
print("\n=== 全部 Hede* 任务（确认并存）===")
t2 = run("/query","/fo","TABLE")
for line in t2.splitlines():
    if "Hede" in line: print(line.rstrip())
