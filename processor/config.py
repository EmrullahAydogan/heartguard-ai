"""HeartGuard AI - Processor Configuration"""
import os

KAFKA_BROKER = os.environ.get('KAFKA_BROKER', 'localhost:29092')
KAFKA_TOPIC_VITALS = os.environ.get('KAFKA_TOPIC_VITALS', 'chf.vitals')
KAFKA_TOPIC_ALERTS = os.environ.get('KAFKA_TOPIC_ALERTS', 'chf.alerts')

INFLUXDB_URL = os.environ.get('INFLUXDB_URL', 'http://localhost:8087')
INFLUXDB_TOKEN = os.environ.get('INFLUXDB_TOKEN', 'heartguard-super-secret-token')
INFLUXDB_ORG = os.environ.get('INFLUXDB_ORG', 'heartguard')
INFLUXDB_BUCKET = os.environ.get('INFLUXDB_BUCKET', 'heartguard')

DATA_DIR = os.environ.get('DATA_DIR', '/app/data')

# Window sizes (number of data points)
WINDOW_5MIN = 5
WINDOW_1HR = 60
WINDOW_6HR = 360
WINDOW_24HR = 1440

# Risk flag thresholds
THRESHOLDS = {
    'tachycardia': 100,      # HR > 100
    'bradycardia': 50,       # HR < 50
    'hypoxia': 93,           # SpO2 < 93
    'tachypnea': 22,         # RR > 22
    'fever': 38.0,           # Temp > 38.0
    'hypotension': 90,       # SBP < 90
}

# MedGemma trigger thresholds
ANOMALY_Z_THRESHOLD = 2.0        # |z| > 2.0
CRITICAL_HR = 120
CRITICAL_SPO2 = 90
CRITICAL_SBP = 85
TREND_HR_THRESHOLD = 10          # HR trend > 10 bpm
TREND_SPO2_THRESHOLD = -3        # SpO2 trend < -3%
MIN_FLAGS_FOR_TRIGGER = 2        # 2+ flags = trigger MedGemma

# Periodic assessment interval (in data points received)
PERIODIC_ASSESSMENT_INTERVAL = 72  # ~72 messages in demo mode

# MedGemma API
MEDGEMMA_API_URL = os.environ.get('MEDGEMMA_API_URL', '')
HF_TOKEN = os.environ.get('HF_TOKEN', '')
