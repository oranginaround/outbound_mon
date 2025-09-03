#!/usr/bin/env python3
"""
Production startup script for the FastAPI application
"""
import uvicorn
from main import app, load_state, init_baseline, monitor_traffic
import threading

if __name__ == "__main__":
    # Initialize the application state
    load_state()
    init_baseline()
    
    # Start the traffic monitoring thread
    thread = threading.Thread(target=monitor_traffic, daemon=True)
    thread.start()
    
    # Start the FastAPI server with production settings
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8080,
        log_level="info",
        access_log=True
    )
