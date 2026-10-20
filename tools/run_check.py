"""Bounded local checks, e.g. python tools/run_check.py 120 npm.cmd run lint.

Runs an argument vector without a shell; kills only this check's process tree
on timeout. Does not print environment variables or command arguments.
"""
import os
import subprocess
import sys

seconds = int(sys.argv[1])
process = subprocess.Popen(sys.argv[2:])
try:
    raise SystemExit(process.wait(timeout=seconds))
except subprocess.TimeoutExpired:
    print(f"Check exceeded {seconds} seconds; stopping its process tree.", flush=True)
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], timeout=10, capture_output=True)
    else:
        process.kill()
    raise SystemExit(124)
