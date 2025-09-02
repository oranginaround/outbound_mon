import psutil
import threading
import time
import json
import os
from datetime import datetime
import calendar
from flask import Flask, render_template, request, jsonify
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
TRAFFIC_CAP_GB = int(os.getenv("TRAFFIC_CAP_GB", "500"))  # Default 500 GB
LIMIT_BYTES = TRAFFIC_CAP_GB * 1024 * 1024 * 1024  # Convert GB to bytes

state = {
    "month": None,
    "baseline": 0,
    "last_bytes_sent": 0,
    "offset_bytes": 0,
    "daily_traffic": {},  # {"2025-09-01": bytes_used, "2025-09-02": bytes_used, ...}
    "daily_baseline": 0,  # Daily baseline for current day
    "current_day": None,  # Track current day
}

lock = threading.Lock()


def load_state():
    global state
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state.update(json.load(f))


def save_state():
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def init_baseline():
    global state
    now = datetime.utcnow()
    month_key = now.strftime("%Y-%m")
    day_key = now.strftime("%Y-%m-%d")
    current_sent = psutil.net_io_counters().bytes_sent

    # Handle monthly reset
    if state["month"] != month_key:
        state["month"] = month_key
        state["baseline"] = current_sent
        state["last_bytes_sent"] = current_sent
        state["daily_traffic"] = {}  # Reset daily tracking for new month
        state["daily_baseline"] = current_sent
        state["current_day"] = day_key
        save_state()
    
    # Handle daily reset
    elif state["current_day"] != day_key:
        # Save yesterday's traffic
        if state["current_day"]:
            yesterday_traffic = current_sent - state["daily_baseline"]
            state["daily_traffic"][state["current_day"]] = yesterday_traffic
        
        # Start new day
        state["daily_baseline"] = current_sent
        state["current_day"] = day_key
        save_state()


def monitor_traffic(interval=10):
    global state
    while True:
        time.sleep(interval)
        with lock:
            init_baseline()
            state["last_bytes_sent"] = psutil.net_io_counters().bytes_sent
            save_state()


@app.route("/")
@basic_auth.required
def index():
    with lock:
        init_baseline()
        raw_used_bytes = state["last_bytes_sent"] - state["baseline"]
        used_bytes = raw_used_bytes + state["offset_bytes"]  # Add manual offset
        used_gb = round(used_bytes / (1024 ** 3), 2)
        offset_gb = round(state["offset_bytes"] / (1024 ** 3), 2)
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

    return render_template(
        'index.html',
        used_gb=used_gb,
        offset_gb=f"{offset_gb:.2f}",
        cap_gb=TRAFFIC_CAP_GB,
        month=month,
        status_class=status_class,
        status_msg=status_msg,
        last_update=last_update,
    )


@app.route("/data")
@basic_auth.required
def data():
    with lock:
        init_baseline()
        raw_used_bytes = state["last_bytes_sent"] - state["baseline"]
        used_bytes = raw_used_bytes + state["offset_bytes"]  # Add manual offset
        used_gb = round(used_bytes / (1024 ** 3), 2)
        offset_gb = round(state["offset_bytes"] / (1024 ** 3), 2)
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

    return jsonify({
        "used_gb": used_gb,
        "offset_gb": f"{offset_gb:.2f}",
        "cap_gb": TRAFFIC_CAP_GB,
        "month": month,
        "status_class": status_class,
        "status_msg": status_msg,
        "last_update": last_update,
    })


@app.route("/daily")
@basic_auth.required
def daily():
    return render_template('daily.html')


@app.route("/daily-chart")
@basic_auth.required
def daily_chart():
    with lock:
        init_baseline()
        now = datetime.utcnow()
        year = now.year
        month = now.month
        
        # Get number of days in current month
        days_in_month = calendar.monthrange(year, month)[1]
        
        # Calculate today's traffic
        current_sent = psutil.net_io_counters().bytes_sent
        today_traffic = current_sent - state["daily_baseline"]
        today_key = now.strftime("%Y-%m-%d")
        
        # Build chart data for the entire month
        chart_data = []
        labels = []
        
        for day in range(1, days_in_month + 1):
            day_key = f"{year:04d}-{month:02d}-{day:02d}"
            labels.append(f"{day}")
            
            if day_key == today_key:
                # Today's traffic (current)
                traffic_gb = round(today_traffic / (1024 ** 3), 3)
            elif day_key in state["daily_traffic"]:
                # Past days with recorded traffic
                traffic_gb = round(state["daily_traffic"][day_key] / (1024 ** 3), 3)
            else:
                # Future days or days without data
                traffic_gb = 0
            
            chart_data.append(traffic_gb)
        
        return jsonify({
            "labels": labels,
            "data": chart_data,
            "month": now.strftime("%B %Y"),
            "today": now.day
        })


@app.route("/adjust", methods=['POST'])
@basic_auth.required
def adjust():
    try:
        data = request.get_json()
        if not data or 'offset' not in data:
            return jsonify({"success": False, "error": "Missing 'offset' in JSON body"}), 400
        
        new_offset_gb = float(data['offset'])
        new_offset_bytes = int(new_offset_gb * 1024 * 1024 * 1024)  # Convert GB to bytes
        
        with lock:
            state["offset_bytes"] = new_offset_bytes  # Rewrite, don't add
            save_state()
        
        return jsonify({
            "success": True, 
            "message": f"Successfully set manual offset to {new_offset_gb} GB"
        })
    
    except (ValueError, TypeError) as e:
        return jsonify({"success": False, "error": f"Invalid offset value: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": f"Server error: {str(e)}"}), 500


if __name__ == "__main__":
    load_state()
    init_baseline()
    thread = threading.Thread(target=monitor_traffic, daemon=True)
    thread.start()
    app.run(host="0.0.0.0", port=8080)
