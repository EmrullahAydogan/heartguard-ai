# HeartGuard AI

**Personalized Heart Failure Home Monitoring System**

Real-time early warning system for CHF patients using personalized thresholds, streaming analytics, and MedGemma clinical reasoning.

## Architecture

```
eICU CSV Data → Kafka Producer → Apache Kafka → Stream Processor → InfluxDB → Dash UI
                                                      ↓
                                                MedGemma Engine
                                              (Clinical Reasoning)
```

## Quick Start

```bash
# 1. Start all services
docker compose up -d

# 2. Access dashboards
# InfluxDB: http://localhost:8087 (admin/heartguard2026)
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| Kafka | 9092/29092 | Message broker |
| InfluxDB | 8087 | Time series database |
| Dash UI | 8050 | Dashboard visualization |
| Producer | - | CSV replay to Kafka |
| Processor | - | Vital analysis + MedGemma |

## Dash UI Dashboards

1. **Clinician Single Patient View** - Detailed vital signs, risk scores, MedGemma assessments
2. **Multi-Patient Monitor** - Overview of all patients, risk comparison
3. **Patient Portal** - Patient-friendly interface with simple messages

## Demo Patients

- **Patient A** (ID: 1129386) - 77F, Stable CHF, NYHA II
- **Patient B** (ID: 1060026) - 79F, Deteriorating CHF, demonstrates alert escalation
- **Patient C** (ID: 2743241) - 66F, Low baseline SpO2, demonstrates personalization

## MedGemma Integration

Model: `google/medgemma-1.5-4b-it`

Three usage modes:
1. **Clinical Reasoning** - Risk assessment with JSON output
2. **Patient Communication** - Patient-friendly messages
3. **Clinician Reports** - SOAP format clinical summaries

To enable MedGemma API:
```bash
# Set HuggingFace token in .env
HF_TOKEN=your_huggingface_token_here
```

Without API access, the system uses rule-based clinical reasoning as fallback.

## Personalization Mechanism

Each patient has personalized baselines computed from their stable period:
- Z-scores relative to personal mean ± std
- Same SpO2 value can mean different risk levels for different patients
- MedGemma receives full patient context (demographics, medications, labs, baselines)

## Configuration

Set replay speed via `REPLAY_SPEED` in `.env`:
- `realtime` - 5 min intervals (production simulation)
- `demo` - 1 sec per message (video demo)
- `fast` - 0.2 sec (development/testing)

## Data Source

eICU Collaborative Research Database Demo v2.0.1
- PhysioNet open access
- 2500+ ICU admissions, 20 US hospitals
