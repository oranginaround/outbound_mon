import psutil
import threading
import time
import json
import os
import secrets
from datetime import datetime, timezone
import calendar
from typing import Dict
from pydantic import BaseModel
from fastapi import FastAPI, Request, HTTPException, Depends, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class AdjustRequest(BaseModel):
    offset: float

class AdjustResponse(BaseModel):
    success: bool
    message: str

class TrafficData(BaseModel):
    used_gb: float
    offset_gb: str
    cap_gb: int
    month: str
    status_class: str
    status_msg: str
    last_update: str
    raw_bytes_sent: int
    timestamp: int

class DailyChartData(BaseModel):
    labels: list[str]
    data: list[float]
    month: str
    today: int

class TrafficStateUpdate(BaseModel):
    month: str
    baseline: int
    last_bytes_sent: int
    offset_bytes: int
    daily_traffic: Dict[str, int]
    daily_baseline: int
    current_day: str

class SuccessResponse(BaseModel):
    success: bool
    message: str

app = FastAPI(title="Outbound Traffic Monitor")

# Set up templates
templates = Jinja2Templates(directory="templates")

# Set up HTTP Basic Authentication
security = HTTPBasic()

# ========================
# BASIC AUTH CONFIG
# ========================
MONITOR_USER = os.getenv("MONITOR_USER")
MONITOR_PASS = os.getenv("MONITOR_PASS")
if not MONITOR_USER or not MONITOR_PASS:
    raise ValueError("Environment variables MONITOR_USER and MONITOR_PASS must be set")

def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    """Basic authentication dependency"""
    if not MONITOR_USER or not MONITOR_PASS:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication not configured"
        )
    
    correct_username = secrets.compare_digest(credentials.username, MONITOR_USER)
    correct_password = secrets.compare_digest(credentials.password, MONITOR_PASS)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

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
    now = datetime.now()
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


@app.get("/", response_class=HTMLResponse)
def index(request: Request, _username: str = Depends(authenticate)):
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

    return templates.TemplateResponse(
        'index.html',
        {
            "request": request,
            "used_gb": used_gb,
            "offset_gb": f"{offset_gb:.2f}",
            "cap_gb": TRAFFIC_CAP_GB,
            "month": month,
            "status_class": status_class,
            "status_msg": status_msg,
            "last_update": last_update,
        }
    )


@app.get("/data", response_model=TrafficData, summary="Get current traffic data", description="Returns current traffic usage statistics including used data, status, and timestamps.")
def data(_username: str = Depends(authenticate)):
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

    return {
        "used_gb": used_gb,
        "offset_gb": f"{offset_gb:.2f}",
        "cap_gb": TRAFFIC_CAP_GB,
        "month": month,
        "status_class": status_class,
        "status_msg": status_msg,
        "last_update": last_update,
        "raw_bytes_sent": state["last_bytes_sent"],  # Add raw bytes data
        "timestamp": int(time.time())  # Add timestamp for pulse calculation
    }


@app.get("/daily", response_class=HTMLResponse)
def daily(request: Request, _username: str = Depends(authenticate)):
    return templates.TemplateResponse('daily.html', {"request": request})


@app.get("/daily-chart", response_model=DailyChartData, summary="Get daily chart data", description="Returns daily traffic data for the current month in chart format.")
def daily_chart(_username: str = Depends(authenticate)):
    with lock:
        init_baseline()
        now = datetime.now()
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
        
        return {
            "labels": labels,
            "data": chart_data,
            "month": now.strftime("%B %Y"),
            "today": now.day
        }


@app.post("/adjust", response_model=AdjustResponse, summary="Adjust traffic offset", description="Manually adjust the traffic offset value in GB.")
def adjust(request_data: AdjustRequest, _username: str = Depends(authenticate)):
    try:
        new_offset_gb = request_data.offset
        new_offset_bytes = int(new_offset_gb * 1024 * 1024 * 1024)  # Convert GB to bytes
        
        with lock:
            state["offset_bytes"] = new_offset_bytes  # Rewrite, don't add
            save_state()
        
        return AdjustResponse(
            success=True, 
            message=f"Successfully set manual offset to {new_offset_gb} GB"
        )
    
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid offset value: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@app.get("/config", response_class=HTMLResponse)
def config(request: Request, _username: str = Depends(authenticate)):
    return templates.TemplateResponse('config.html', {"request": request})


@app.get("/api/traffic-state")
def get_traffic_state(_username: str = Depends(authenticate)):
    with lock:
        return state


@app.post("/api/traffic-state", response_model=SuccessResponse, summary="Update traffic state", description="Update the complete traffic state with new values.")
def update_traffic_state(request_data: TrafficStateUpdate, _username: str = Depends(authenticate)):
    try:
        with lock:
            # Update state
            state.update(request_data.dict())
            save_state()
        
        return SuccessResponse(success=True, message="Traffic state updated successfully")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


if __name__ == "__main__":
    load_state()
    init_baseline()
    thread = threading.Thread(target=monitor_traffic, daemon=True)
    thread.start()
    uvicorn.run(app, host="0.0.0.0", port=8080)
