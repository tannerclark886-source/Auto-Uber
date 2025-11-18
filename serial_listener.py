"""
serial_listener.py

Listens to a serial port (Arduino Uno) and starts/stops the FastAPI server
located in the same project when it receives simple commands from the Arduino
(e.g. "START" / "STOP").

Usage (PowerShell):
  python serial_listener.py --port COM3

If --port is omitted the script will try to auto-detect a port that looks like
an Arduino (by name/description). If none found it will list available ports.

It will try to use the project's virtualenv at ./.venv/Scripts/python.exe if
present, otherwise it will fall back to the Python interpreter used to launch
this script.

This script requires pyserial:
  python -m pip install pyserial

"""

from __future__ import annotations
import sys
import os
import time
import re
import json
import argparse
import subprocess
import signal
import logging
from pathlib import Path
from typing import Optional

try:
    import serial
    import serial.tools.list_ports
except Exception as e:
    print("Missing dependency 'pyserial'. Install it with: python -m pip install pyserial")
    raise

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(PROJECT_DIR, "uvicorn.pid")

# Windows creation flag to detach process: DETACHED_PROCESS
DETACHED_PROCESS = 0x00000008


def find_arduino_port() -> Optional[str]:
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None
    # Prefer ports that mention Arduino
    for p in ports:
        if "arduino" in (p.description or "").lower() or "arduino" in (p.device or "").lower():
            return p.device
    # otherwise return the first
    return ports[0].device


def get_python_executable() -> str:
    # Prefer project's venv if present
    venv_python = os.path.join(PROJECT_DIR, ".venv", "Scripts", "python.exe")
    if os.path.exists(venv_python):
        return venv_python
    return sys.executable


def is_server_running() -> bool:
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            # check if process exists
            os.kill(pid, 0)
            return True
        except Exception:
            try:
                os.remove(PID_FILE)
            except OSError:
                pass
    return False


def start_server() -> Optional[int]:
    if is_server_running():
        print("Server already running (pid file exists).")
        return None
    python = get_python_executable()
    cmd = [python, "-m", "uvicorn", "main:app", "--reload"]
    print("Starting server with:", cmd)
    try:
        # Start detached so it keeps running after this script continues
        proc = subprocess.Popen(cmd, cwd=PROJECT_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=DETACHED_PROCESS, close_fds=True)
        pid = proc.pid
        with open(PID_FILE, "w") as f:
            f.write(str(pid))
        print(f"Server started (pid={pid}).")
        return pid
    except Exception as e:
        print("Failed to start server:", e)
        return None


def stop_server() -> bool:
    if not os.path.exists(PID_FILE):
        print("No pid file, server may not be running.")
        return False
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        print(f"Stopping server pid={pid} ...")
        # Try graceful termination
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            # last resort
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception as e:
                print("Failed to kill process:", e)
                return False
        # remove pid file
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        print("Server stopped.")
        return True
    except Exception as e:
        print("Error stopping server:", e)
        return False


def list_ports():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("No serial ports found.")
        return
    print("Available serial ports:")
    for p in ports:
        print(f"  {p.device} - {p.description}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", "-p", help="Serial port (e.g. COM3). If omitted the script will try to auto-detect.")
    parser.add_argument("--baud", "-b", type=int, default=9600, help="Baud rate (default 9600)")
    parser.add_argument("--no-auto-start", action="store_true", help="Do not auto-start server on START command; just print messages")
    parser.add_argument("--bac-threshold", type=float, default=0.08, help="BAC numeric threshold to auto-start the server (default 0.08)")
    parser.add_argument("--auto-stop", action="store_true", help="Automatically stop the server when BAC falls below threshold")
    parser.add_argument("--consecutive", type=int, default=3, help="Number of consecutive BAC readings >= threshold required to start (default 3)")
    parser.add_argument("--consecutive-stop", type=int, default=3, help="Number of consecutive BAC readings < threshold required to stop when --auto-stop is enabled (default 3)")
    parser.add_argument("--calibration-file", default="bac_calibration.json", help="Path to JSON calibration file (optional)")
    parser.add_argument("--log-file", default="logs/serial_listener.log", help="Path to log file")
    args = parser.parse_args()

    com_port = args.port or find_arduino_port()
    if com_port is None:
        print("Could not detect Arduino port automatically.")
        list_ports()
        print("Specify a port with --port COM3")
        return

    print(f"Using serial port: {com_port} @ {args.baud}")

    try:
        ser = serial.Serial(com_port, args.baud, timeout=1)
    except Exception as e:
        print("Failed to open serial port:", e)
        list_ports()
        return

    server_pid = None
    started_by_bac = False
    above_count = 0
    below_count = 0

    # Prepare logging
    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s', handlers=[
        logging.FileHandler(log_path, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ])

    # Load calibration if present
    calibration = None
    cal_path = Path(args.calibration_file)
    if cal_path.exists():
        try:
            with open(cal_path, 'r', encoding='utf-8') as f:
                calibration = json.load(f)
            logging.info(f"Loaded calibration from {cal_path}")
        except Exception as e:
            logging.warning(f"Failed to load calibration file {cal_path}: {e}")
            calibration = None
    else:
        logging.info("No calibration file found; using default mapping")

    def calibrated_bac_from_analog(analog_val: int) -> float:
        # If calibration is a dict with 'scale' and optional 'offset' use it
        if calibration and isinstance(calibration, dict):
            try:
                scale = float(calibration.get('scale', 0.5/1023.0))
                offset = float(calibration.get('offset', 0.0))
                return analog_val * scale + offset
            except Exception:
                pass
        # Default mapping (legacy): map 0..1023 to 0..0.5
        return float(analog_val) * (0.5 / 1023.0)
    print("Listening for serial commands (START / STOP). Ctrl-C to quit.")

    try:
        while True:
            try:
                raw = ser.readline()
            except Exception as e:
                print("Serial read error:", e)
                time.sleep(0.5)
                continue
            if not raw:
                time.sleep(0.05)
                continue
            try:
                line = raw.decode("utf-8", errors="ignore").strip()
            except Exception:
                line = str(raw)
            if not line:
                continue
            print("Serial->", line)
            cmd = line.strip()

            # If the Arduino sends a simple START or STOP command, handle it first
            if cmd.upper() == "START":
                if args.no_auto_start:
                    print("(no-auto-start) Received START")
                else:
                    start_server()
                    started_by_bac = False
                continue
            if cmd.upper() == "STOP":
                stop_server()
                started_by_bac = False
                continue

            # Try to parse a BAC value from the line.
            # Accept formats like: "BAC:0.082", "Estimated BAC: 0.082", "BAC: 0.082%", or just a number.
            m = re.search(r"\bBAC\b[:\s]*([0-9]*\.?[0-9]+)", line, flags=re.IGNORECASE)
            val = None
            if m:
                try:
                    val = float(m.group(1))
                except Exception:
                    val = None
            else:
                # try any standalone float in the line as fallback
                m2 = re.search(r"([0-9]*\.?[0-9]+)", line)
                if m2:
                    try:
                        val = float(m2.group(1))
                    except Exception:
                        val = None

            if val is not None:
                # If the value looks like a percentage > 1 (e.g., 8.2), normalize if needed
                if val > 1.0:
                    # Likely a percent like 8.2 -> convert to 0.082
                    if val > 100.0:
                        # improbable large value, keep as-is
                        pass
                    else:
                        val = val / 100.0
                logging.info(f"Parsed BAC={val:.3f} (threshold={args.bac_threshold})")
                # trigger start when threshold met, using consecutive reading debounce
                if val >= args.bac_threshold:
                    above_count += 1
                    below_count = 0
                else:
                    below_count += 1
                    above_count = 0

                logging.debug(f"consecutive above={above_count} below={below_count}")

                if above_count >= args.consecutive:
                    if not is_server_running():
                        if args.no_auto_start:
                            logging.info("(no-auto-start) Detected BAC>=threshold, not starting server")
                        else:
                            p = start_server()
                            if p:
                                started_by_bac = True
                                logging.info(f"Started server due to BAC threshold (pid={p})")
                    else:
                        logging.info("Server already running; BAC threshold detected")

                if args.auto_stop and started_by_bac and below_count >= args.consecutive_stop:
                    if is_server_running():
                        logging.info("BAC dropped below threshold and --auto-stop enabled: stopping server")
                        stop_server()
                        started_by_bac = False
                continue

            # If we get here, line didn't match START/STOP/BAC
            print("Unrecognized serial command. Use START, STOP or send 'BAC:<value>' lines.")
    except KeyboardInterrupt:
        print("Exiting: closing serial port")
    finally:
        if ser and ser.is_open:
            ser.close()


if __name__ == "__main__":
    main()
