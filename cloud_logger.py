import scratchattach as sa
from flask import Flask, jsonify
from threading import Thread
from datetime import datetime

SCRATCH_USERNAME = "PSULions23"
SCRATCH_PASSWORD = "kevin123"
SCRATCH_PROJECT_ID = 1211167512

log_data = []

# Log in and connect
session = sa.login(SCRATCH_USERNAME, SCRATCH_PASSWORD)
# Optionally keep conn if you need to set vars later
conn = session.connect_cloud(SCRATCH_PROJECT_ID)

# Set up event listener correctly
events = sa.CloudEvents(str(SCRATCH_PROJECT_ID))

@events.event
def on_set(event):
    timestamp = event.timestamp or datetime.utcnow().isoformat()
    log_data.append({
        "time": timestamp,
        "variable": event.var,
        "value": event.value,
        "user": event.user
    })
    print(f"[{timestamp}] {event.user} set {event.var} to {event.value}")

@events.event
def on_ready():
    print("Cloud event listener is ready!")

# Start listening in a separate thread
def run_events():
    events.start()

thread = Thread(target=run_events, daemon=True)
thread.start()

# Flask app
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Cloud Logger is running!"

@app.route("/logs")
def get_logs():
    return jsonify(log_data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
