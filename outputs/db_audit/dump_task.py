import subprocess, re
out = subprocess.run(["schtasks","/query","/tn","HedeDatabaseIndexReview","/xml"],
                     capture_output=True)
xml = out.stdout.decode("utf-16-le", errors="replace") if out.stdout[:2] == b"\xff\xfe" else out.stdout.decode("utf-8", errors="replace")
if not xml.strip().startswith("<"):
    xml = out.stdout.decode("utf-16", errors="replace")
open(r"E:\hede\outputs\db_audit\task_template.xml","w",encoding="utf-8").write(xml)
print("bytes:", len(xml))
print(xml)
