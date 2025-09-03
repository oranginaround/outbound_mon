# Outbound Traffic Monitor

A FastAPI-based web application that monitors outbound network traffic and provides a web interface to track monthly data usage against a configurable limit.

## Features

- Real-time monitoring of outbound network traffic
- Monthly traffic tracking with automatic baseline reset
- Web dashboard with basic authentication
- Visual warnings when approaching or exceeding limits
- Auto-refresh dashboard every 5 seconds
- Persistent state storage
- RESTful API endpoints for programmatic access
- Interactive API documentation via Swagger UI

## Quick Start with Docker

1. **Build and run with docker-compose:**
   ```bash
   docker-compose up --build
   ```

2. **Access the application:**
   - Web dashboard: `http://localhost:8080`
   - API documentation: `http://localhost:8080/docs`
   - Default credentials: `admin` / `secret123`

## Configuration

Environment variables:
- `MONITOR_USER`: Basic auth username (default: admin)
- `MONITOR_PASS`: Basic auth password (default: secret123)
- `DATA_DIR`: Directory for persistent data (default: /app/data)
- `TRAFFIC_CAP_GB`: Monthly traffic limit in GB (default: 500)

## API Endpoints

The application provides several REST API endpoints:

- `GET /` - Main dashboard (HTML)
- `GET /data` - Current traffic data (JSON)
- `GET /daily` - Daily traffic chart (HTML)
- `GET /daily-chart` - Daily chart data (JSON)
- `POST /adjust` - Adjust manual offset
- `GET /config` - Configuration page (HTML)
- `GET /api/traffic-state` - Get complete traffic state
- `POST /api/traffic-state` - Update traffic state
- `GET /docs` - Interactive API documentation (Swagger UI)

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
