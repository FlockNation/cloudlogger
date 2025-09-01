import scratchattach as sa
import json
import time
from datetime import datetime
from threading import Thread
from flask import Flask, jsonify

SCRATCH_USERNAME = "PSULions23"
SCRATCH_PASSWORD = "kevin123"
SCRATCH_PROJECT_ID = 1211167512

log_data = []

print("Logging in...")
session = sa.login(SCRATCH_USERNAME, SCRATCH_PASSWORD)

print("Connecting to cloud project...")
cloud = session.connect_cloud(SCRATCH_PROJECT_ID)

@cloud.event
def on_set(event):
    timestamp = datetime.utcnow().isoformat()

    entry = {
        "time": timestamp,
        "variable": event.name,
        "value": event.value,
        "user": event.user
    }

    log_data.append(entry)
    print(f"[{timestamp}] {event.user} set {event.name} to {event.value}")

# Keep listener alive in a background thread
def run_listener():
    print("Logger started. Waiting for cloud changes...")
    while True:
        time.sleep(1)

listener_thread = Thread(target=run_listener)
listener_thread.daemon = True
listener_thread.start()

# Flask app to serve logs
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Cloud Logger is running!"

@app.route("/logs")
def get_logs():
    return jsonify(log_data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
