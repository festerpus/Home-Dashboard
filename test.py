from flask import Flask, jsonify
import serial
import threading
import time
import json

app = Flask(__name__)

ser = serial.Serial("COM4", 9600, timeout=1)

latest = {
    "raw": None,
    "rtherm": None,
    "temp": None
}

# latest = ""

def read_temp():
    global latest

    while True:
        try:
            line = ser.readline().decode("utf-8").strip()

            if not line:
                continue

            latest = json.loads(line)

        except json.JSONDecodeError as e:
            print(f"Bad JSON: {line!r}")
            print(e)


thread = threading.Thread(target=read_temp, daemon=True)
thread.start()


@app.route("/temperature")
def temperature():
    return jsonify(latest)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000
    )