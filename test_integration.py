"""
Integration test helper for the Auto Uber API project.

What it does:
- Detects if something is already listening on port 8000. If not, it starts the server
  using the project's venv Python (./.venv/Scripts/python.exe) and `-m uvicorn main:app`.
- Polls the root endpoint (http://127.0.0.1:8000/) until it gets a valid JSON response or a timeout.
- Verifies the response contains the expected message.
- If this script started the server, it will terminate it at the end.

Usage (PowerShell):
  python test_integration.py

Notes:
- Requires `requests` (already in requirements.txt). If missing, install with:
    python -m pip install requests

"""
from __future__ import annotations
import os
import sys
import time
import socket
import subprocess
import signal
import requests

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
UVICORN_PORT = 8000
PID_FILE = os.path.join(PROJECT_DIR, "uvicorn.pid")

# Windows detached flag
DETACHED_PROCESS = 0x00000008


def is_port_open(port: int = UVICORN_PORT, host: str = '127.0.0.1') -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect((host, port))
            return True
        except Exception:
            return False


def get_python_executable() -> str:
    venv_python = os.path.join(PROJECT_DIR, '.venv', 'Scripts', 'python.exe')
    if os.path.exists(venv_python):
        return venv_python
    return sys.executable


def start_uvicorn_detached() -> int | None:
    python = get_python_executable()
    cmd = [python, '-m', 'uvicorn', 'main:app']
    print('Starting uvicorn:', cmd)
    try:
        proc = subprocess.Popen(cmd, cwd=PROJECT_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=DETACHED_PROCESS, close_fds=True)
        pid = proc.pid
        print('uvicorn started as pid', pid)
        # write PID so other tools may use it (serial_listener uses uvicorn.pid too)
        try:
            with open(PID_FILE, 'w') as f:
                f.write(str(pid))
        except Exception:
            pass
        return pid
    except Exception as e:
        print('Failed to start uvicorn:', e)
        return None


def stop_pid(pid: int) -> None:
    try:
        print('Stopping pid', pid)
        # On Windows, os.kill is available but signal.SIGTERM may be ignored; use TerminateProcess via taskkill for reliability
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(pid), '/F'], check=False)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception as e:
        print('Error stopping pid:', e)


def wait_for_server(timeout: float = 10.0) -> bool:
    url = f'http://127.0.0.1:{UVICORN_PORT}/'
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=1.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def main() -> int:
    already_running = is_port_open()
    started_pid = None

    if already_running:
        print(f"Server appears to be already running on port {UVICORN_PORT}.")
    else:
        print("No server found on port 8000 — starting uvicorn...")
        started_pid = start_uvicorn_detached()
        if started_pid is None:
            print('Could not start server; aborting test.')
            return 2

    print('Waiting for server to become available...')
    ok = wait_for_server(timeout=15.0)
    if not ok:
        print('Server did not respond within timeout.')
        if started_pid:
            stop_pid(started_pid)
        return 3

    print('Server is up — calling root endpoint...')
    try:
        r = requests.get(f'http://127.0.0.1:{UVICORN_PORT}/', timeout=2.0)
        print('Status code:', r.status_code)
        print('Body:', r.text)
        j = r.json()
        expected = '✅ Uber FastAPI Bridge is running'
        if isinstance(j, dict) and j.get('message') == expected:
            print('Integration test passed ✅')
            result = 0
        else:
            print('Unexpected response body; test failed')
            result = 4
    except Exception as e:
        print('Error calling endpoint:', e)
        result = 5

    # If we started the server, stop it to leave system as we found it
    if started_pid:
        print('Stopping the server we started...')
        stop_pid(started_pid)
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
        except Exception:
            pass

    return result


if __name__ == '__main__':
    code = main()
    sys.exit(code)
