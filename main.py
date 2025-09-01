import psutil
import threading
import time
import json
import os
from datetime import datetime
from flask import Flask, render_template_string
from flask_basicauth import BasicAuth

app = Flask(__name__)

# ========================
# BASIC AUTH CONFIG
# ========================
MONITOR_USER = os.getenv("MONITOR_USER")
MONITOR_PASS = os.getenv("MONITOR_PASS")
if not MONITOR_USER or not MONITOR_PASS:
    raise ValueError("Environment variables MONITOR_USER and MONITOR_PASS must be set")
app.config['BASIC_AUTH_USERNAME'] = MONITOR_USER
app.config['BASIC_AUTH_PASSWORD'] = MONITOR_PASS
app.config['BASIC_AUTH_FORCE'] = True   # protect all routes

basic_auth = BasicAuth(app)

# ========================
# TRAFFIC MONITOR CONFIG
# ========================
STATE_FILE = os.path.join(os.getenv("DATA_DIR", "/app/data"), "traffic_state.json")
LIMIT_BYTES = 100 * 1024 * 1024 * 1024  # 100 GB

state = {
    "month": None,
    "baseline": 0,
    "last_bytes_sent": 0,
}

lock = threading.Lock()


def load_state():
    global state
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            state.update(json.load(f))


def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def init_baseline():
    global state
    now = datetime.utcnow()
    month_key = now.strftime("%Y-%m")
    current_sent = psutil.net_io_counters().bytes_sent

    if state["month"] != month_key:
        state["month"] = month_key
        state["baseline"] = current_sent
        state["last_bytes_sent"] = current_sent
        save_state()


def monitor_traffic(interval=10):
    global state
    while True:
        time.sleep(interval)
        with lock:
            init_baseline()
            state["last_bytes_sent"] = psutil.net_io_counters().bytes_sent
            save_state()


TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Outbound Traffic Monitor</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; margin-top: 50px; }
        .card { display: inline-block; padding: 20px; border: 1px solid #ccc; border-radius: 10px; box-shadow: 2px 2px 10px rgba(0,0,0,0.1); }
        h1 { font-size: 24px; }
        p { font-size: 20px; }
        .warn { color: orange; }
        .over { color: red; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Outbound Traffic Monitor</h1>
        <p><strong>Month:</strong> {{ month }}</p>
        <p><strong>Used:</strong> {{ used_gb }} GB / 100 GB</p>
        <p class="{{ status_class }}">{{ status_msg }}</p>
        <p><small>Last Update: {{ last_update }}</small></p>
    </div>
    <script>
        setTimeout(() => window.location.reload(), 5000);
    </script>
</body>
</html>
"""


@app.route("/")
@basic_auth.required
def index():
    with lock:
        init_baseline()
        used_bytes = state["last_bytes_sent"] - state["baseline"]
        used_gb = round(used_bytes / (1024 ** 3), 2)
        month = state["month"]

        if used_bytes > LIMIT_BYTES:
            status_class = "over"
            status_msg = "⚠️ Over limit! Extra charges apply."
        elif used_bytes > LIMIT_BYTES * 0.8:
            status_class = "warn"
            status_msg = f"Warning: {used_gb} GB used (~80% of limit)."
        else:
            status_class = ""
            status_msg = "Within safe limit."

        last_update = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    return render_template_string(
        TEMPLATE,
        used_gb=used_gb,
        month=month,
        status_class=status_class,
        status_msg=status_msg,
        last_update=last_update,
    )


if __name__ == "__main__":
    load_state()
    init_baseline()
    thread = threading.Thread(target=monitor_traffic, daemon=True)
    thread.start()
    app.run(host="0.0.0.0", port=8080)
