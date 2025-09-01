# Outbound Traffic Monitor

A Flask-based web application that monitors outbound network traffic and provides a web interface to track monthly data usage against a 100GB limit.

## Features

- Real-time monitoring of outbound network traffic
- Monthly traffic tracking with automatic baseline reset
- Web dashboard with basic authentication
- Visual warnings when approaching or exceeding limits
- Auto-refresh dashboard every 5 seconds
- Persistent state storage

## Quick Start with Docker

1. **Build and run with docker-compose:**
   ```bash
   docker-compose up --build
   ```

2. **Access the dashboard:**
   - Open your browser to `http://localhost:8080`
   - Default credentials: `admin` / `secret123`

## Configuration

Environment variables:
- `MONITOR_USER`: Basic auth username (default: admin)
- `MONITOR_PASS`: Basic auth password (default: secret123)
- `DATA_DIR`: Directory for persistent data (default: /app/data)

## Docker Commands

```bash
# Build and start
docker-compose up --build -d

# View logs
docker-compose logs -f

# Stop
docker-compose down

# Rebuild
docker-compose build --no-cache
```

## Manual Docker Build

```bash
# Build image
docker build -t outbound-monitor .

# Run container
docker run -d \
  --name outbound-monitor \
  --network host \
  --privileged \
  -e MONITOR_USER=admin \
  -e MONITOR_PASS=secret123 \
  -v $(pwd)/data:/app/data \
  outbound-monitor
```

## Notes

- The container runs in `--privileged` mode with `--network host` to access real network statistics
- Data is persisted in the `./data` directory
- The application automatically resets the baseline at the beginning of each month
