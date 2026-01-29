"""Run server_pg.py with Python verbose (-v) import tracing and save output to import_verbose.log.

Usage:
    py -3 run_server_verbose.py

This script launches `py -3 -v server_pg.py` and redirects stdout/stderr to import_verbose.log.
It does not block; check import_verbose.log for progress.
"""
import subprocess
import os

LOG = os.path.join(os.path.dirname(__file__), 'import_verbose.log')
CMD = ['py', '-3', '-v', 'server_pg.py']
with open(LOG, 'wb') as f:
    p = subprocess.Popen(CMD, stdout=f, stderr=subprocess.STDOUT)
print('Launched verbose server tracer; PID=', p.pid)
print('Logging to', LOG)
