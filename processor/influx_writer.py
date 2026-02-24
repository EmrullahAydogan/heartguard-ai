"""
HeartGuard AI - InfluxDB Writer
Writes vital signs, risk scores, MedGemma assessments, and alerts to InfluxDB.
"""

import logging
from datetime import datetime, timezone

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from config import INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET

logger = logging.getLogger(__name__)


class InfluxWriter:
    def __init__(self):
        self.client = None
        self.write_api = None
        self._connect()

    def _connect(self):
        """Connect to InfluxDB."""
        try:
            self.client = InfluxDBClient(
                url=INFLUXDB_URL,
                token=INFLUXDB_TOKEN,
                org=INFLUXDB_ORG,
            )
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            # Test connection
            health = self.client.health()
            logger.info(f"Connected to InfluxDB: {health.status}")
        except Exception as e:
            logger.error(f"Failed to connect to InfluxDB: {e}")
            raise

    def write_vitals(self, analysis: dict):
        """Write raw vital signs to InfluxDB."""
        timestamp = analysis.get('timestamp')
        if timestamp and isinstance(timestamp, str):
            try:
                ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                ts = datetime.now(timezone.utc)
        else:
            ts = datetime.now(timezone.utc)

        point = (
            Point("vital_signs")
            .tag("patient_id", analysis['patient_id'])
            .tag("source", "monitor")
            .time(ts, WritePrecision.S)
        )

        for field_name, key in [
            ('heart_rate', 'heart_rate'),
            ('spo2', 'spo2'),
            ('respiration', 'respiration'),
            ('temperature', 'temperature'),
            ('systolic_bp', 'systolic_bp'),
            ('diastolic_bp', 'diastolic_bp'),
            ('mean_bp', 'mean_bp'),
        ]:
            val = analysis.get(key)
            if val is not None:
                point = point.field(field_name, float(val))

        try:
            self.write_api.write(bucket=INFLUXDB_BUCKET, record=point)
        except Exception as e:
            logger.error(f"Failed to write vitals: {e}")

    def write_risk_scores(self, analysis: dict, calculator='python'):
        """Write computed risk scores to InfluxDB."""
        timestamp = analysis.get('timestamp')
        if timestamp and isinstance(timestamp, str):
            try:
                ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                ts = datetime.now(timezone.utc)
        else:
            ts = datetime.now(timezone.utc)

        point = (
            Point("risk_scores")
            .tag("patient_id", analysis['patient_id'])
            .tag("calculator", calculator)
            .time(ts, WritePrecision.S)
            .field("risk_score", float(analysis.get('risk_score', 0)))
            .field("risk_category", analysis.get('risk_category', 'stable'))
            .field("z_hr", float(analysis.get('z_hr', 0)))
            .field("z_spo2", float(analysis.get('z_spo2', 0)))
            .field("z_rr", float(analysis.get('z_rr', 0)))
            .field("hr_trend", float(analysis.get('hr_trend', 0)))
            .field("spo2_trend", float(analysis.get('spo2_trend', 0)))
            .field("rr_trend", float(analysis.get('rr_trend', 0)))
            .field("n_active_flags", int(analysis.get('n_active_flags', 0)))
        )

        # Add individual flags
        for flag_name, flag_val in analysis.get('flags', {}).items():
            point = point.field(f"flag_{flag_name}", bool(flag_val))

        try:
            self.write_api.write(bucket=INFLUXDB_BUCKET, record=point)
        except Exception as e:
            logger.error(f"Failed to write risk scores: {e}")

    def write_medgemma_assessment(self, patient_id: str, assessment: dict,
                                  trigger_reason: str = 'periodic'):
        """Write MedGemma assessment to InfluxDB."""
        ts = datetime.now(timezone.utc)

        point = (
            Point("medgemma_assessments")
            .tag("patient_id", patient_id)
            .tag("trigger_reason", trigger_reason)
            .tag("source", assessment.get('source', 'medgemma'))
            .time(ts, WritePrecision.S)
            .field("risk_score", float(assessment.get('risk_score', 0)))
            .field("risk_category", str(assessment.get('risk_category', 'stable')))
            .field("clinical_reasoning", str(assessment.get('clinical_reasoning', '')))
            .field("recommendation", str(assessment.get('recommendation', '')))
        )

        key_concerns = assessment.get('key_concerns', [])
        if isinstance(key_concerns, list):
            point = point.field("key_concerns", '; '.join(key_concerns))
        else:
            point = point.field("key_concerns", str(key_concerns))

        # Include NYHA class if provided
        if 'nyha_class' in assessment:
            def parse_nyha(val):
                if isinstance(val, int): return val
                if isinstance(val, str):
                    v = val.strip().upper()
                    roman_map = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5}
                    if v in roman_map: return roman_map[v]
                    if v.startswith('CLASS '):
                        v = v.replace('CLASS ', '')
                        if v in roman_map: return roman_map[v]
                    try: return int(v)
                    except ValueError: pass
                return 0
            point = point.field("nyha_class", parse_nyha(assessment['nyha_class']))

        try:
            self.write_api.write(bucket=INFLUXDB_BUCKET, record=point)
        except Exception as e:
            logger.error(f"Failed to write MedGemma assessment: {e}")

    def write_alert(self, patient_id: str, severity: str, alert_type: str,
                    message: str, medgemma_analysis: str = ''):
        """Write alert to InfluxDB."""
        ts = datetime.now(timezone.utc)

        point = (
            Point("alerts")
            .tag("patient_id", patient_id)
            .tag("severity", severity)
            .tag("alert_type", alert_type)
            .time(ts, WritePrecision.S)
            .field("message", message)
            .field("medgemma_analysis", medgemma_analysis)
            .field("acknowledged", False)
        )

        try:
            self.write_api.write(bucket=INFLUXDB_BUCKET, record=point)
        except Exception as e:
            logger.error(f"Failed to write alert: {e}")

    def write_patient_baseline(self, patient_id: str, baselines: dict, nyha_class: int = 0):
        """Write patient baselines to InfluxDB."""
        ts = datetime.now(timezone.utc)

        def parse_nyha(val):
            if isinstance(val, int): return val
            if isinstance(val, str):
                v = val.strip().upper()
                roman_map = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5}
                if v in roman_map: return roman_map[v]
                if v.startswith('CLASS '):
                    v = v.replace('CLASS ', '')
                    if v in roman_map: return roman_map[v]
                try: return int(v)
                except ValueError: pass
            return 0

        parsed_nyha = parse_nyha(nyha_class)

        point = (
            Point("patient_baselines")
            .tag("patient_id", patient_id)
            .time(ts, WritePrecision.S)
            .field("nyha_class", parsed_nyha)
        )

        for key, val in baselines.items():
            if val is not None:
                point = point.field(key, float(val))

        try:
            self.write_api.write(bucket=INFLUXDB_BUCKET, record=point)
        except Exception as e:
            logger.error(f"Failed to write baselines: {e}")

    def write_patient_message(self, patient_id: str, message: str, risk_category: str):
        """Write patient-friendly message to InfluxDB."""
        ts = datetime.now(timezone.utc)

        point = (
            Point("patient_messages")
            .tag("patient_id", patient_id)
            .tag("risk_category", risk_category)
            .time(ts, WritePrecision.S)
            .field("message", message)
        )

        try:
            self.write_api.write(bucket=INFLUXDB_BUCKET, record=point)
        except Exception as e:
            logger.error(f"Failed to write patient message: {e}")

    def write_clinician_report(self, patient_id: str, report: str):
        """Write SOAP report to InfluxDB."""
        ts = datetime.now(timezone.utc)

        point = (
            Point("clinician_reports")
            .tag("patient_id", patient_id)
            .time(ts, WritePrecision.S)
            .field("report", report)
        )

        try:
            self.write_api.write(bucket=INFLUXDB_BUCKET, record=point)
        except Exception as e:
            logger.error(f"Failed to write clinician report: {e}")

    def close(self):
        """Close InfluxDB connection."""
        if self.client:
            self.client.close()
