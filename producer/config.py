"""HeartGuard AI - Producer Configuration"""
import os

KAFKA_BROKER = os.environ.get('KAFKA_BROKER', 'localhost:29092')
KAFKA_TOPIC_VITALS = os.environ.get('KAFKA_TOPIC_VITALS', 'chf.vitals')
KAFKA_TOPIC_CONTROL = os.environ.get('KAFKA_TOPIC_CONTROL', 'chf.control')

# Replay speed: seconds between messages per patient
REPLAY_SPEEDS = {
    'realtime': 300.0,   # 5 min intervals (real-time simulation)
    'demo': 1.0,         # 1 sec per message (24hrs ~= 5 min demo)
    'fast': 0.2,         # Fast mode for development/testing
}

REPLAY_SPEED = os.environ.get('REPLAY_SPEED', 'demo')

DATA_DIR = os.environ.get('DATA_DIR', '/app/data')
