import os
import time
import warnings
from datetime import datetime
from threading import Thread

import scratchattach as sa
from flask import Flask, jsonify, Response

# Suppress login warnings
warnings.filterwarnings('ignore', category=UserWarning, module='scratchattach')

# Configuration
SCRATCH_USERNAME = os.environ.get("SCRATCH_USERNAME", "PSULions23")
SCRATCH_PASSWORD = os.environ.get("SCRATCH_PASSWORD", "kevin123")
SCRATCH_PROJECT_ID = os.environ.get("SCRATCH_PROJECT_ID", "1211167512")

# In-memory log (keeps recent events)
MAX_LOG_ENTRIES = 2000
log_data = []

def append_log(entry):
    log_data.append(entry)
    # Keep memory bounded
    if len(log_data) > MAX_LOG_ENTRIES:
        del log_data[0 : len(log_data) - MAX_LOG_ENTRIES]

def start_cloud_listener():
    """
    Connect to Scratch and start listening to cloud events.
    Uses cloud.events() and @events.event handlers (correct API).
    """
    try:
        print("Logging into Scratch...")
        session = sa.login(SCRATCH_USERNAME, SCRATCH_PASSWORD)
        print("Connected to Scratch session.")

        print(f"Connecting to cloud for project {SCRATCH_PROJECT_ID}...")
        cloud = session.connect_cloud(str(SCRATCH_PROJECT_ID))
        print("Connected to project cloud.")

        # Correct way to get event handlers for this cloud connection:
        events = cloud.events()

        @events.event
        def on_set(activity):
            ts = getattr(activity, "timestamp", None) or datetime.utcnow().isoformat()
            entry = {
                "time": ts,
                "variable": getattr(activity, "var", getattr(activity, "name", None)),
                "value": getattr(activity, "value", None),
                "user": getattr(activity, "user", None),
            }
            append_log(entry)
            print(f"[{entry['time']}] {entry['user']} set {entry['variable']} -> {entry['value']}")

        @events.event
        def on_create(activity):
            ts = getattr(activity, "timestamp", None) or datetime.utcnow().isoformat()
            entry = {
                "time": ts,
                "variable": getattr(activity, "var", getattr(activity, "name", None)),
                "value": None,
                "user": getattr(activity, "user", None),
                "action": "create",
            }
            append_log(entry)
            print(f"[{entry['time']}] {entry['user']} created {entry['variable']}")

        @events.event
        def on_del(activity):
            ts = getattr(activity, "timestamp", None) or datetime.utcnow().isoformat()
            entry = {
                "time": ts,
                "variable": getattr(activity, "var", getattr(activity, "name", None)),
                "value": None,
                "user": getattr(activity, "user", None),
                "action": "delete",
            }
            append_log(entry)
            print(f"[{entry['time']}] {entry['user']} deleted {entry['variable']}")

        @events.event
        def on_ready():
            print("Cloud events listener ready.")

        # Start the cloud event loop (this will run in background)
        print("Starting cloud event loop...")
        events.start()

    except Exception as e:
        # If anything goes wrong, print it and try to reconnect after a short delay
        print("Cloud listener error:", e)
        print("Retrying in 10 seconds...")
        time.sleep(10)
        start_cloud_listener()  # retry (simple retry loop)

# Start the cloud listener in a daemon thread so Flask can run in main thread
listener_thread = Thread(target=start_cloud_listener, daemon=True)
listener_thread.start()

# --- Flask app to serve logs and a simple frontend ---
app = Flask(__name__)

# Simple frontend HTML (you can replace with a static file instead)
INDEX_HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Scratch Cloud Log</title>
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <style>
      body{font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial; padding:20px; max-width:1000px;margin:auto;}
      h1{text-align:center}
      table{width:100%; border-collapse:collapse; margin-top:1rem; box-shadow:0 4px 10px rgba(0,0,0,0.06);}
      th,td{padding:10px;border-bottom:1px solid #e6e6e6;text-align:center;}
      th{background:#111827;color:white}
      tr:hover{background:#f8fafc}
      .time{font-size:0.85rem;color:#6b7280}
      .small{font-size:0.9rem;color:#374151}
    </style>
  </head>
  <body>
    <h1>🌍 Scratch Cloud Log</h1>
    <div style="text-align:center"><small>Auto-refreshes every 5s • Showing newest first</small></div>
    <table id="logTable">
      <thead>
        <tr><th>Time (UTC)</th><th>User</th><th>Variable</th><th>Value</th></tr>
      </thead>
      <tbody><tr><td colspan="4">Loading…</td></tr></tbody>
    </table>

    <script>
      async function fetchLogs(){
        try{
          const res = await fetch('/logs?_=' + Date.now());
          const data = await res.json();
          const tbody = document.querySelector('#logTable tbody');
          tbody.innerHTML = '';
          // newest first
          data.slice().reverse().forEach(e => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td class="time">${e.time || ''}</td>
                            <td class="small">${e.user || ''}</td>
                            <td>${e.variable || ''}</td>
                            <td>${e.value === null ? '' : e.value || ''}</td>`;
            tbody.appendChild(tr);
          });
          if(data.length === 0){
            document.querySelector('#logTable tbody').innerHTML = '<tr><td colspan="4">No logs yet.</td></tr>';
          }
        }catch(err){
          console.error('fetchLogs error', err);
        }
      }
      fetchLogs();
      setInterval(fetchLogs, 5000);
    </script>
  </body>
</html>
"""

@app.route("/")
def home():
    return Response(INDEX_HTML, mimetype="text/html")

@app.route("/logs")
def logs_route():
    # Return the in-memory log (most recent last)
    return jsonify(log_data)

if __name__ == "__main__":
    # Flask runs on port 8080 on Render by default
    port = int(os.environ.get("PORT", 8080))
    print("Starting Flask server on port", port)
    app.run(host="0.0.0.0", port=port)
