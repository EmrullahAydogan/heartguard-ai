# HeartGuard AI - Operations Guide

## System Architecture

```
                        HOST MACHINE (GPU)
                    ┌─────────────────────────┐
                    │  MedGemma Server (:8888) │
                    │  google/medgemma-1.5-4b-it   │
                    │  RTX 4070 - bfloat16     │
                    └────────────┬─────────────┘
                                 │ HTTP (localhost:8888)
┌────────────────────────────────┼──── DOCKER ─────────────────────────────┐
│                                │                                         │
│  ┌──────────┐   ┌───────┐   ┌─┴──────────┐   ┌──────────┐   ┌────────┐ │
│  │ Producer  │──>│ Kafka │──>│ Processor  │──>│ InfluxDB │<──│Dash UI │ │
│  │ (replay)  │   │:29092 │   │(host mode) │   │  :8087   │   │ :9005  │ │
│  └──────────┘   └───────┘   └────────────┘   └──────────┘   └────────┘ │
│       │              │                                                   │
│  CSV Replay     Zookeeper                                               │
│  1 msg/sn        :2181                                                  │
└──────────────────────────────────────────────────────────────────────────┘
```

**Data Flow:**
1. **Producer** reads CSV files and streams vital signs to Kafka (1 message/second per patient)
2. **Processor** consumes from Kafka, runs Layer 1 (rule-based analysis) on every message
3. When anomaly/trigger detected, request is queued for **MedGemma** (Layer 2)
4. MedGemma worker processes queue sequentially (one at a time, waits for completion)
5. All results written to **InfluxDB** (vital signs, risk scores, AI assessments, alerts)
6. **Dash UI** dashboards visualize everything in real-time

---

## Quick Start (Full System)

### Step 1: Start MedGemma Server (Host)

MedGemma runs on the host machine (not in Docker) to access the GPU directly.

```bash
cd "/home/developer/Desktop/The MedGemma Impact Challenge/heartguard-ai"

# Start MedGemma server in background
nohup python3 processor/medgemma_server.py > /tmp/medgemma_server.log 2>&1 &

# Wait ~20 seconds for model to load, then verify
tail -f /tmp/medgemma_server.log
# Should see: "Model loaded successfully!" and "MedGemma server running on port 8888"

# Quick health check
curl http://localhost:8888/health
# Should return: {"status": "ok", "model": "google/medgemma-1.5-4b-it"}
```

### Step 2: Start Docker Services

```bash
cd "/home/developer/Desktop/The MedGemma Impact Challenge/heartguard-ai"

# Start all services
docker compose up -d

# Verify all containers are running
docker compose ps
```

All 6 containers should show as running:
| Container | Status |
|-----------|--------|
| heartguard-zookeeper | Running (healthy) |
| heartguard-kafka | Running (healthy) |
| heartguard-influxdb | Running (healthy) |
| heartguard-dashboard | Running |
| heartguard-producer | Running |
| heartguard-processor | Running |

### Step 3: Open Dashboards

- **Dash UI:** http://localhost:9005
  - Username: `admin`
  - Password: `heartguard`
- **InfluxDB:** http://localhost:8087 (optional)
  - Username: `admin`
  - Password: `heartguard2026`

---

## Stopping the System

### Stop Everything

```bash
cd "/home/developer/Desktop/The MedGemma Impact Challenge/heartguard-ai"

# Stop Docker services (preserves data)
docker compose down

# Stop MedGemma server
kill $(lsof -ti:8888)
```

### Stop Only Data Streaming (Keep Infrastructure)

```bash
# Stop producer and processor only
docker compose stop heartguard-producer heartguard-processor

# Infrastructure (Kafka, InfluxDB, Dash UI) stays running
# Dashboard data remains visible
```

### Full Cleanup (Delete All Data)

```bash
# Stop and remove containers + volumes
docker compose down -v

# Stop MedGemma
kill $(lsof -ti:8888)

# This deletes all InfluxDB data and Dash UI settings
```

---

## Restarting After a Stop

### Restart with Existing Data

```bash
# 1. Start MedGemma first
cd "/home/developer/Desktop/The MedGemma Impact Challenge/heartguard-ai"
nohup python3 processor/medgemma_server.py > /tmp/medgemma_server.log 2>&1 &

# 2. Wait for model to load (~20 seconds)
sleep 20 && curl http://localhost:8888/health

# 3. Start Docker services
docker compose up -d
```

### Fresh Restart (Clean Data)

```bash
cd "/home/developer/Desktop/The MedGemma Impact Challenge/heartguard-ai"

# 1. Stop everything
docker compose down
kill $(lsof -ti:8888) 2>/dev/null

# 2. Clear InfluxDB data (if containers still exist)
# Or use: docker compose down -v (removes volumes)

# 3. Start MedGemma
nohup python3 processor/medgemma_server.py > /tmp/medgemma_server.log 2>&1 &
sleep 20

# 4. Start services
docker compose up -d
```

### Restart Only Producer/Processor (Code Change)

After editing processor or producer code:

```bash
# Rebuild and restart
docker compose up -d --build heartguard-processor heartguard-producer
```

---

## Monitoring & Logs

### View Live Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f heartguard-processor
docker compose logs -f heartguard-producer

# MedGemma server
tail -f /tmp/medgemma_server.log
```

### Key Log Messages to Watch

**Processor - Healthy Operation:**
```
Loaded state for Patient A (ID: 341781)
Patient 341781: NYHA Class 4 - ...              # MedGemma NYHA estimation
MedGemma worker thread started                   # Queue worker ready
Processed 100 messages, 2 MedGemma assessments   # Normal throughput
[Patient X] Queued for MedGemma: ...             # Trigger detected
[Patient X] Clinical reasoning complete           # AI assessment done
[Patient X] Patient message generated             # Patient comms done
[Patient X] Clinician SOAP report generated       # SOAP note done
[Patient X] MedGemma assessment #N complete       # Full cycle done
```

**Processor - Problems:**
```
HF API call failed: 410                          # HF API down (uses local server instead)
Could not connect to Kafka!                       # Kafka not ready
Failed to connect to InfluxDB                     # InfluxDB not ready
MedGemma worker error                             # MedGemma server issue
```

### Check System Status

```bash
# Container status
docker compose ps

# GPU usage (MedGemma)
nvidia-smi

# MedGemma server health
curl http://localhost:8888/health

# InfluxDB data count
curl -s -X POST "http://localhost:8087/api/v2/query?org=heartguard" \
  -H "Authorization: Token heartguard-super-secret-token" \
  -H "Content-Type: application/vnd.flux" \
  --data-raw 'from(bucket: "heartguard")
    |> range(start: -1y, stop: 2027-01-01T00:00:00Z)
    |> group(columns: ["_measurement"])
    |> count()
    |> keep(columns: ["_measurement", "_value"])'
```

---

## Configuration

### Replay Speed

Edit `.env` file before starting:

```bash
REPLAY_SPEED=demo      # 1 msg/sec (default, good for demo)
REPLAY_SPEED=fast      # 5 msg/sec (testing)
REPLAY_SPEED=realtime  # 1 msg/5min (real-time simulation)
```

Then restart producer: `docker compose restart heartguard-producer`

### Changing Patients

1. Edit `scripts/prepare_data.py` - update patient IDs in `select_demo_patients()`
2. Run: `python3 scripts/prepare_data.py`
3. Clear InfluxDB data
4. Restart: `docker compose restart heartguard-producer heartguard-processor`

### MedGemma Trigger Thresholds

Edit `processor/config.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| ANOMALY_Z_THRESHOLD | 2.0 | Z-score deviation to trigger AI |
| CRITICAL_HR | 120 | Heart rate critical threshold |
| CRITICAL_SPO2 | 90 | SpO2 critical threshold |
| CRITICAL_SBP | 85 | Systolic BP critical threshold |
| MIN_FLAGS_FOR_TRIGGER | 2 | Minimum flags to trigger AI |
| PERIODIC_ASSESSMENT_INTERVAL | 72 | Messages between periodic assessments |

After changes: `docker compose up -d --build heartguard-processor`

---

## Dash UI Dashboards

### 3 Dashboard Types

| Dashboard | URL | Purpose |
|-----------|-----|---------|
| Clinician Dashboard | `/d/heartguard-clinician` | Single patient detailed view |
| Command Center | `/d/heartguard-multipatient` | All patients overview |
| My Health | `/d/heartguard-patient` | Patient-friendly portal |

### Patient Selection

- **Clinician** and **My Health** dashboards have a `patient_id` dropdown at the top
- Select between: 341781, 447543, 3141080
- **Command Center** shows all 3 patients simultaneously

### Time Range

- Default: Last 6 hours to +2 days ahead
- Data timestamps extend into the future (due to CSV offset replay)
- Use Dash UI's time picker to zoom in/out

### Dashboard Refresh

- Dashboards auto-refresh every 5 seconds
- Dashboard JSON files are reloaded by Dash UI every 10 seconds
- After editing JSON files: `docker compose restart dashboard`

---

## Troubleshooting

### Problem: MedGemma sections empty in dashboard

**Cause:** MedGemma server not running or not reachable.

```bash
# Check if server is running
curl http://localhost:8888/health

# If not running, start it
nohup python3 processor/medgemma_server.py > /tmp/medgemma_server.log 2>&1 &

# Restart processor to reconnect
docker compose restart heartguard-processor
```

### Problem: No data in dashboards

**Cause:** Time range mismatch or services not running.

```bash
# Check if data exists in InfluxDB
curl -s -X POST "http://localhost:8087/api/v2/query?org=heartguard" \
  -H "Authorization: Token heartguard-super-secret-token" \
  -H "Content-Type: application/vnd.flux" \
  --data-raw 'from(bucket: "heartguard")
    |> range(start: -1y, stop: 2027-01-01T00:00:00Z)
    |> filter(fn: (r) => r._measurement == "vital_signs" and r._field == "heart_rate")
    |> group(columns: ["patient_id"])
    |> count()'

# If empty, check producer and processor logs
docker compose logs --tail=20 heartguard-producer
docker compose logs --tail=20 heartguard-processor
```

### Problem: Port already in use

```bash
# MedGemma port 8888
kill $(lsof -ti:8888)

docker compose down
docker compose up -d

# InfluxDB port 8087
docker compose down
docker compose up -d
```

### Problem: GPU out of memory

```bash
# Check GPU usage
nvidia-smi

# Kill MedGemma server and restart
kill $(lsof -ti:8888)
sleep 5
nohup python3 processor/medgemma_server.py > /tmp/medgemma_server.log 2>&1 &
```

### Problem: Kafka consumer timeout

This happens if the processor can't poll Kafka frequently enough.
The system is configured with `max_poll_interval_ms=600000` (10 min) to handle this.

```bash
# If still occurring, restart processor
docker compose restart heartguard-processor
```

---

## Service Ports Summary

| Service | Port | Protocol | Access |
|---------|------|----------|--------|
| Dash UI | 9005 | HTTP | http://localhost:9005 |
| InfluxDB | 8087 | HTTP | http://localhost:8087 |
| Kafka (external) | 29092 | TCP | localhost:29092 |
| Kafka (internal) | 9092 | TCP | kafka:9092 (Docker only) |
| Zookeeper | 2181 | TCP | localhost:2181 |
| MedGemma Server | 8888 | HTTP | http://localhost:8888 |

## Credentials

| Service | Username | Password |
|---------|----------|----------|
| InfluxDB | admin | heartguard2026 |
| InfluxDB Token | - | heartguard-super-secret-token |

---

## Demo Patients

| Label | Patient ID | Age | Role | Key Features |
|-------|-----------|-----|------|--------------|
| A | 341781 | 49M | Stable Control | HR std=3.1, SpO2=98.3%, BNP=1630 |
| B | 447543 | 80M | Deteriorating | APACHE=112, Troponin=4.95, Expired |
| C | 3141080 | 87M | Personalization | SpO2=88.9%, BNP=3529, CHF Class III |

## InfluxDB Measurements

| Measurement | Description | Written By |
|-------------|-------------|------------|
| vital_signs | Raw HR, SpO2, RR, Temp, BP | Every message |
| risk_scores | Risk score, z-scores, trends, flags | Every message |
| medgemma_assessments | AI clinical reasoning + risk | MedGemma queue |
| patient_messages | Patient-friendly AI messages | MedGemma queue |
| clinician_reports | SOAP format clinical notes | MedGemma queue (warning/critical) |
| alerts | Severity alerts with AI analysis | MedGemma queue (warning/critical) |
| patient_baselines | Personal baseline values | Startup only |
