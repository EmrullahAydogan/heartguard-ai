"""InfluxDB data client for HeartGuard AI Dash dashboard."""

import os
import json
from influxdb_client import InfluxDBClient

INFLUX_URL    = os.getenv("INFLUXDB_URL",   "http://localhost:8087")
INFLUX_TOKEN  = os.getenv("INFLUXDB_TOKEN", "heartguard-super-secret-token")
INFLUX_ORG    = "heartguard"
INFLUX_BUCKET = "heartguard"
TIME_RANGE_START = "-7d"
TIME_RANGE_STOP = "2027-01-01T00:00:00Z"

_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
_query_api = _client.query_api()

PATIENTS = {
    "341781":  {"label": "Patient A",  "name": "Patient A (Stable)",        "type": "Stable Control"},
    "447543":  {"label": "Patient B",  "name": "Patient B (Deteriorating)", "type": "Deteriorating"},
    "3141080": {"label": "Patient C",  "name": "Patient C (Personalization)","type": "Personalization"},
}

def _query(flux: str):
    try:
        return _query_api.query(flux)
    except Exception:
        return []

def get_vitals_timeseries(patient_id: str, field: str):
    """Returns list of (time, value) tuples for a vital sign."""
    flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {TIME_RANGE_START}, stop: {TIME_RANGE_STOP})
  |> filter(fn: (r) => r._measurement == "vital_signs" and r.patient_id == "{patient_id}")
  |> filter(fn: (r) => r._field == "{field}")
  |> keep(columns: ["_time", "_value"])
  |> sort(columns: ["_time"])
'''
    tables = _query(flux)
    times, values = [], []
    for table in tables:
        for record in table.records:
            times.append(record.get_time())
            values.append(record.get_value())
    return times, values

def get_latest_vitals(patient_id: str):
    """Returns dict of latest vital values."""
    flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {TIME_RANGE_START}, stop: {TIME_RANGE_STOP})
  |> filter(fn: (r) => r._measurement == "vital_signs" and r.patient_id == "{patient_id}")
  |> filter(fn: (r) => r._field == "heart_rate" or r._field == "spo2" or r._field == "temperature" or r._field == "respiration")
  |> last()
  |> keep(columns: ["_field", "_value"])
'''
    tables = _query(flux)
    result = {}
    for table in tables:
        for record in table.records:
            result[record["_field"]] = record.get_value()
    return result

def get_risk_score(patient_id: str):
    """Returns (risk_score 0-1, risk_category string)."""
    flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {TIME_RANGE_START}, stop: {TIME_RANGE_STOP})
  |> filter(fn: (r) => r._measurement == "risk_scores" and r.patient_id == "{patient_id}")
  |> filter(fn: (r) => r._field == "risk_score" or r._field == "risk_category")
  |> last()
  |> keep(columns: ["_field", "_value"])
'''
    tables = _query(flux)
    score, category = None, None
    for table in tables:
        for record in table.records:
            if record["_field"] == "risk_score":
                score = record.get_value()
            elif record["_field"] == "risk_category":
                category = record.get_value()
    return score, category

def get_patient_messages(patient_id: str, limit: int = 5):
    """Returns list of (time, message) tuples, newest first."""
    flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {TIME_RANGE_START}, stop: {TIME_RANGE_STOP})
  |> filter(fn: (r) => r._measurement == "patient_messages" and r.patient_id == "{patient_id}")
  |> filter(fn: (r) => r._field == "message")
  |> keep(columns: ["_time", "_value"])
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {limit})
'''
    tables = _query(flux)
    result = []
    for table in tables:
        for record in table.records:
            result.append((record.get_time(), record.get_value()))
    return result

def get_medgemma_assessment(patient_id: str):
    """Returns latest MedGemma assessment fields."""
    flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {TIME_RANGE_START}, stop: {TIME_RANGE_STOP})
  |> filter(fn: (r) => r._measurement == "medgemma_assessments" and r.patient_id == "{patient_id}")
  |> last()
  |> keep(columns: ["_field", "_value"])
'''
    tables = _query(flux)
    result = {}
    for table in tables:
        for record in table.records:
            result[record["_field"]] = record.get_value()
    return result

def get_alerts(patient_id: str, limit: int = 10):
    """Returns list of (time, message, severity) tuples, newest first."""
    flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {TIME_RANGE_START}, stop: {TIME_RANGE_STOP})
  |> filter(fn: (r) => r._measurement == "alerts" and r.patient_id == "{patient_id}")
  |> filter(fn: (r) => r._field == "message")
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {limit})
'''
    tables = _query(flux)
    result = []
    for table in tables:
        for record in table.records:
            result.append({
                "time": record.get_time(),
                "message": record.get_value(),
                "severity": record.values.get("severity", "info"),
            })
    return result

def get_clinician_report(patient_id: str):
    """Returns latest clinician SOAP report."""
    flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {TIME_RANGE_START}, stop: {TIME_RANGE_STOP})
  |> filter(fn: (r) => r._measurement == "clinician_reports" and r.patient_id == "{patient_id}")
  |> filter(fn: (r) => r._field == "report")
  |> last()
  |> keep(columns: ["_time", "_value"])
'''
    tables = _query(flux)
    for table in tables:
        for record in table.records:
            return record.get_time(), record.get_value()
    return None, None

def get_all_patients_latest():
    """Returns dict of patient_id -> {vitals, risk_score, risk_category} for command center."""
    result = {}
    for pid in PATIENTS:
        vitals = get_latest_vitals(pid)
        score, category = get_risk_score(pid)
        result[pid] = {
            "vitals": vitals,
            "risk_score": score,
            "risk_category": category or "stable",
        }
    return result

def get_patient_profile(patient_id: str):
    """Loads static patient profile from JSON."""
    label = PATIENTS.get(patient_id, {}).get("label", "").split(" ")[-1]
    if not label: return {}
    filepath = os.path.join("/app/data", "patient_profiles", f"patient_{label}_{patient_id}.json")
    try:
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading profile for {patient_id}: {e}")
    return {}

def get_nyha_class(patient_id: str):
    """Returns latest NYHA class."""
    flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {TIME_RANGE_START}, stop: {TIME_RANGE_STOP})
  |> filter(fn: (r) => (r._measurement == "medgemma_assessments" or r._measurement == "patient_baselines") and r.patient_id == "{patient_id}")
  |> filter(fn: (r) => r._field == "nyha_class")
  |> last()
  |> keep(columns: ["_value"])
'''
    tables = _query(flux)
    for table in tables:
        for record in table.records:
            return record.get_value()
    return None

def delete_all_data():
    """Wipes all data from the InfluxDB bucket."""
    delete_api = _client.delete_api()
    try:
        delete_api.delete(
            start="1970-01-01T00:00:00Z",
            stop="2099-01-01T00:00:00Z",
            predicate="",
            bucket=INFLUX_BUCKET,
            org=INFLUX_ORG
        )
        return True
    except Exception as e:
        print(f"InfluxDB Delete Error: {e}")
        return False
