import subprocess
r = subprocess.run(["schtasks","/query","/tn","HedeDatabaseMissingDataReview","/xml"], capture_output=True)
b = r.stdout
t = b.decode("utf-16-le", errors="replace") if b[:2]==b"\xff\xfe" else b.decode("utf-8", errors="replace")
if not t.strip().startswith("<"): t = b.decode("utf-16", errors="replace")
print(t)
