# Auto Uber API (FastAPI bridge)

This project exposes a small FastAPI wrapper for Uber API endpoints.

What's included
- `main.py` - FastAPI app
- `.env` - environment (set `UBER_ACCESS_TOKEN` here)
- `.venv/` - virtualenv used in this workspace (if present)
- `serial_listener.py` - listens to an Arduino Uno (serial) and starts/stops the server
- `start_uvicorn.ps1` - PowerShell helper to start uvicorn detached
- `requirements.txt` - Python dependencies

Quick start (Windows / PowerShell)

1. Open PowerShell and change to the project directory:

```powershell
cd "C:\Auto Uber API"
```

2. (Optional) Create a venv and activate it, or use the existing `.venv`:

```powershell
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

4. Ensure `.env` has a valid token (or leave placeholder for testing routes that don't call Uber):

```
UBER_ACCESS_TOKEN=your_real_uber_access_token_here
UBER_BASE_URL=https://sandbox-api.uber.com/v1.2
```

5. Start the server in its own terminal (recommended):

```powershell
& ".\.venv\Scripts\python.exe" -m uvicorn main:app --reload
```

Or use the helper script to detach it:

```powershell
.\start_uvicorn.ps1 -ProjectDir "C:\Auto Uber API"
```

6. Test with your browser: `http://127.0.0.1:8000/docs`

Using an Arduino UNO to trigger the server

- Upload a sketch that sends `START` over serial when the condition is met (button/sensor). See example below.
- Install `pyserial` and run `serial_listener.py` to listen to the Arduino and start/stop the server.

Calibration and automatic start based on BAC

- The listener supports parsing `BAC:<value>` lines from the Arduino and will start the API when the parsed BAC reaches the configured threshold (default `0.08`).
- You can provide a calibration file `bac_calibration.json` in the project root to tune the mapping from analog reading to BAC. The file should contain `scale` and optional `offset` values, for example:

```json
{
  "scale": 0.0004,
  "offset": 0.0
}
```

- To run the listener with consecutive-reading debounce and logging:

```powershell
python .\serial_listener.py --port COM3 --bac-threshold 0.08 --consecutive 3 --consecutive-stop 3 --log-file logs/serial_listener.log
```

- Use `--auto-stop` to stop the server automatically when BAC falls below the threshold for the configured consecutive-stop count.

Example Arduino sketch (button on pin 2):

```arduino
const int buttonPin = 2;

void setup() {
  pinMode(buttonPin, INPUT_PULLUP);
  Serial.begin(9600);
}

void loop() {
  if (digitalRead(buttonPin) == LOW) { // pressed
    Serial.println("START");
    delay(500); // debounce / avoid repeats
  }
}
```

Run the serial listener (replace COM3 with your Arduino port):

```powershell
python .\serial_listener.py --port COM3
```

If you omit `--port` the script will try to auto-detect a port that looks like an Arduino.

Notes & troubleshooting
- Run the uvicorn server in its own terminal; if you run other commands in the same terminal you may accidentally kill the server.
- If the server immediately exits when tested from the same terminal, start it detached (see `start_uvicorn.ps1`) or use two terminals: one for server, one for testing.
- If you get an HTTP 500 complaining about "Missing Uber access token", set `UBER_ACCESS_TOKEN` in `.env` and restart uvicorn.
- To change the serial port or baud rate, pass `--port` and `--baud` to `serial_listener.py`.

If you want, I can:
- Add a small Windows service wrapper to ensure the server always runs at boot.
- Add unit tests and a tiny integration test script that verifies the root endpoint.

