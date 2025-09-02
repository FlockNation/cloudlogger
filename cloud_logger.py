# cloud_logger.py
import os
import time
import warnings
import traceback
from datetime import datetime
from threading import Thread

import scratchattach as sa
from flask import Flask, jsonify, Response

# Suppress noisy scratchattach warnings (don't suppress everything globally in larger apps)
warnings.filterwarnings("ignore", category=UserWarning, module="scratchattach")

# Config (use environment vars on Render; fallback to these defaults for local testing)
SCRATCH_USERNAME = os.environ.get("SCRATCH_USERNAME", "PSULions23")
SCRATCH_PASSWORD = os.environ.get("SCRATCH_PASSWORD", "kevin123")
SCRATCH_PROJECT_ID = os.environ.get("SCRATCH_PROJECT_ID", "1211167512")

# In-memory log (bounded)
MAX_LOG_ENTRIES = 2000
log_data = []

def append_log(entry):
    log_data.append(entry)
    if len(log_data) > MAX_LOG_ENTRIES:
        del log_data[0 : len(log_data) - MAX_LOG_ENTRIES]

def start_cloud_listener():
    """
    Connect to Scratch and start listening for cloud events.
    Runs forever (retries on errors). Must be started inside a thread.
    """
    while True:
        try:
            print("Attempting Scratch login...")
            session = sa.login(SCRATCH_USERNAME, SCRATCH_PASSWORD)
            print("Scratch login successful.")

            print(f"Connecting to cloud project {SCRATCH_PROJECT_ID} ...")
            cloud = session.connect_cloud(str(SCRATCH_PROJECT_ID))
            print("Connected to project cloud.")

            # get events object (correct API)
            events = cloud.events()

            # keep track of activity shapes we've already printed (for debug)
            seen_activity_shapes = set()

            @events.event
            def on_set(activity):
                try:
                    # Debug: inspect attributes once per shape so we know what's available
                    shape = tuple(sorted([k for k in dir(activity) if not k.startswith('_')]))
                    if shape not in seen_activity_shapes:
                        seen_activity_shapes.add(shape)
                        # Build a sample dict of non-callable attributes (safe)
                        sample = {}
                        for k in shape:
                            try:
                                v = getattr(activity, k)
                                # avoid printing large callables/objects
                                if callable(v):
                                    sample[k] = f"<callable {type(v).__name__}>"
                                else:
                                    # Some attributes might not be JSON-serializable; stringify safely
                                    try:
                                        sample[k] = v
                                    except Exception:
                                        sample[k] = repr(v)
                            except Exception:
                                sample[k] = "<error reading>"
                        debug_text = f"DEBUG ACTIVITY SHAPE ({datetime.utcnow().isoformat()}):\n{sample}\n"
                        print(debug_text)
                        # also append to debug file for later inspection
                        try:
                            with open("activity_debug_samples.txt", "a", encoding="utf-8") as f:
                                f.write(debug_text + "\n")
                        except Exception:
                            pass

                    # Try common attribute names for username
                    username = None
                    for attr in ("user", "username", "author", "player", "owner"):
                        username = getattr(activity, attr, None)
                        if username:
                            break

                    # Try numeric id fallback and attempt to resolve (best-effort)
                    if not username:
                        uid = getattr(activity, "user_id", None) or getattr(activity, "uid", None) or getattr(activity, "id", None)
                        if uid:
                            try:
                                # best-effort: some scratchattach versions provide session.get_user or sa.get_user
                                try:
                                    user_obj = session.get_user(str(uid))
                                except Exception:
                                    try:
                                        user_obj = sa.get_user(str(uid))
                                    except Exception:
                                        user_obj = None
                                if user_obj:
                                    username = getattr(user_obj, "username", None) or getattr(user_obj, "name", None)
                            except Exception:
                                username = None

                    # Last-resort: attempt to read a helper 'last_user' variable from the project if your Scratch project writes one
                    if not username:
                        try:
                            helper = None
                            try:
                                helper = cloud.get_var("last_user")
                            except Exception:
                                helper = None
                            if helper:
                                username = helper
                        except Exception:
                            username = None

                    if not username:
                        username = "Unknown"

                    ts = getattr(activity, "timestamp", None) or datetime.utcnow().isoformat()
                    variable_name = getattr(activity, "var", getattr(activity, "name", None))
                    value = getattr(activity, "value", None)

                    entry = {
                        "time": ts,
                        "variable": variable_name,
                        "value": value,
                        "user": username
                    }
                    append_log(entry)
                    print(f"[{entry['time']}] {entry['user']} set {entry['variable']} -> {entry['value']}")
                except Exception as e:
                    print("Error in on_set handler:", e)
                    traceback.print_exc()

            @events.event
            def on_create(activity):
                try:
                    ts = getattr(activity, "timestamp", None) or datetime.utcnow().isoformat()
                    variable_name = getattr(activity, "var", getattr(activity, "name", None))
                    entry = {
                        "time": ts,
                        "variable": variable_name,
                        "value": None,
                        "user": getattr(activity, "user", None) or "Unknown",
                        "action": "create",
                    }
                    append_log(entry)
                    print(f"[{entry['time']}] (create) {entry['user']} created {entry['variable']}")
                except Exception as e:
                    print("Error in on_create handler:", e)
                    traceback.print_exc()

            @events.event
            def on_del(activity):
                try:
                    ts = getattr(activity, "timestamp", None) or datetime.utcnow().isoformat()
                    variable_name = getattr(activity, "var", getattr(activity, "name", None))
                    entry = {
                        "time": ts,
                        "variable": variable_name,
                        "value": None,
                        "user": getattr(activity, "user", None) or "Unknown",
                        "action": "delete",
                    }
                    append_log(entry)
                    print(f"[{entry['time']}] (delete) {entry['user']} deleted {entry['variable']}")
                except Exception as e:
                    print("Error in on_del handler:", e)
                    traceback.print_exc()

            @events.event
            def on_ready():
                print("Cloud events listener ready.")

            print("Starting cloud events listener (this will block inside the thread)...")
            events.start()  # usually blocks; that's why this whole function runs in a separate thread
            # if events.start() ever returns normally, we'll loop and reconnect
            print("events.start() returned (unexpected). Will reconnect in 5 seconds.")
            time.sleep(5)

        except Exception as e:
            print("Cloud listener connection error:", e)
            traceback.print_exc()
            print("Retrying connection in 10 seconds...")
            time.sleep(10)
            # loop will retry

# Start the listener thread (daemon so process will exit when main thread exits)
listener_thread = Thread(target=start_cloud_listener, daemon=True)
listener_thread.start()

# --- Flask app to serve frontend + logs ---
app = Flask(__name__)

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
          if(!Array.isArray(data) || data.length === 0){
            tbody.innerHTML = '<tr><td colspan="4">No logs yet.</td></tr>';
            return;
          }
          data.slice().reverse().forEach(e => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td class="time">${e.time || ''}</td>
                            <td class="small">${e.user || ''}</td>
                            <td>${e.variable || ''}</td>
                            <td>${e.value === null ? '' : e.value || ''}</td>`;
            tbody.appendChild(tr);
          });
        }catch(err){
          console.error('fetchLogs error', err);
          document.querySelector('#logTable tbody').innerHTML = '<tr><td colspan="4">Error loading logs.</td></tr>';
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
    return jsonify(log_data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print("Starting Flask on port", port)
    app.run(host="0.0.0.0", port=port)
