#!/usr/bin/env python3
"""
HeartGuard AI - Kafka Producer (CSV Replay)
Reads processed CHF patient CSVs and streams vitals to Kafka.
Supports 3 simultaneous patients with configurable replay speed.
"""

import json
import os
import sys
import time
import threading
from datetime import datetime, timedelta, timezone

import pandas as pd
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import NoBrokersAvailable

from config import (
    KAFKA_BROKER, KAFKA_TOPIC_VITALS, KAFKA_TOPIC_CONTROL, REPLAY_SPEEDS, REPLAY_SPEED, DATA_DIR
)


def wait_for_kafka(broker, max_retries=30, retry_interval=5):
    """Wait for Kafka broker to become available."""
    for attempt in range(max_retries):
        try:
            producer = KafkaProducer(
                bootstrap_servers=broker,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8'),
            )
            print(f"Connected to Kafka at {broker}")
            return producer
        except NoBrokersAvailable:
            print(f"Kafka not ready (attempt {attempt + 1}/{max_retries}), waiting {retry_interval}s...")
            time.sleep(retry_interval)
    print("ERROR: Could not connect to Kafka!")
    sys.exit(1)


def load_patient_data(data_dir):
    """Load demo patient mapping and CSV data."""
    mapping_path = os.path.join(data_dir, 'demo_patients.json')
    with open(mapping_path) as f:
        mapping = json.load(f)

    patients = {}
    for label, pid in mapping['patients'].items():
        csv_path = os.path.join(data_dir, 'processed', f'patient_{label}_{pid}.csv')
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            # Load profile
            profile_path = os.path.join(data_dir, 'patient_profiles', f'patient_{label}_{pid}.json')
            with open(profile_path) as f:
                profile = json.load(f)
            patients[label] = {
                'patient_id': str(pid),
                'label': mapping['labels'][label],
                'data': df,
                'profile': profile,
            }
            print(f"Loaded Patient {label} ({mapping['labels'][label]}): "
                  f"ID={pid}, {len(df)} records")
        else:
            print(f"WARNING: CSV not found for Patient {label}: {csv_path}")

    return patients


def control_listener(broker, topic, shared_state):
    """Listen for control messages to dynamically change replay speed."""
    print(f"Starting control listener on {topic}", flush=True)
    try:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=broker,
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        for msg in consumer:
            data = msg.value
            action = data.get("action")
            
            if action == "set_speed":
                new_speed = float(data.get("value", 1.0))
                shared_state["speed_seconds"] = new_speed
                print(f"[CONTROL] Speed updated to {new_speed}s", flush=True)
                
            elif action == "set_state":
                state = data.get("value", "playing")
                shared_state["state"] = state
                print(f"[CONTROL] Stream state set to '{state}'", flush=True)
                
            elif action == "restart_stream":
                print("[CONTROL] Restarting streaming threads from row 0...", flush=True)
                shared_state["restart_signal"] = True
                
    except Exception as e:
        print(f"Control listener error: {e}", flush=True)


def stream_patient(producer, topic, patient_info, shared_state, stop_event):
    """Stream a single patient's vitals to Kafka."""
    pid = patient_info['patient_id']
    label = patient_info['label']
    df = patient_info['data']

    print(f"[Patient {pid}] Starting stream ({label}), {len(df)} records, "
          f"initial_interval={shared_state['speed_seconds']}s")

    # Use current time as base timestamp
    base_time = datetime.now(timezone.utc)

    for idx, row in df.iterrows():
        if stop_event.is_set() or shared_state.get("restart_signal"):
            break
            
        while shared_state.get("state") == "paused":
            if stop_event.is_set() or shared_state.get("restart_signal"):
                break
            time.sleep(0.5)
            
        if stop_event.is_set() or shared_state.get("restart_signal"):
            break

        # Build vital message
        timestamp = base_time + timedelta(minutes=row.get('offset_minutes', idx * 5))

        message = {
            'patient_id': pid,
            'timestamp': timestamp.isoformat(),
            'heart_rate': round(float(row['heart_rate']), 1) if pd.notna(row.get('heart_rate')) else None,
            'spo2': round(float(row['spo2']), 1) if pd.notna(row.get('spo2')) else None,
            'respiration': round(float(row['respiration']), 1) if pd.notna(row.get('respiration')) else None,
            'temperature': round(float(row['temperature']), 1) if pd.notna(row.get('temperature')) else None,
            'systolic_bp': round(float(row['systolic_bp']), 1) if pd.notna(row.get('systolic_bp')) else None,
            'diastolic_bp': round(float(row['diastolic_bp']), 1) if pd.notna(row.get('diastolic_bp')) else None,
            'mean_bp': round(float(row['mean_bp']), 1) if pd.notna(row.get('mean_bp')) else None,
        }

        # Send to Kafka
        producer.send(topic, key=pid, value=message)

        if idx % 50 == 0:
            print(f"[Patient {pid}] Sent record {idx}/{len(df)}, "
                  f"HR={message['heart_rate']}, SpO2={message['spo2']}")

        time.sleep(shared_state["speed_seconds"])

    print(f"[Patient {pid}] Stream complete ({len(df)} records sent)")


def main():
    speed = REPLAY_SPEEDS.get(REPLAY_SPEED, 1.0)
    print("=" * 60)
    print("HeartGuard AI - Kafka Producer")
    print(f"Broker: {KAFKA_BROKER}")
    print(f"Topic: {KAFKA_TOPIC_VITALS}")
    print(f"Speed: {REPLAY_SPEED} ({speed}s per message)")
    print("=" * 60)

    # Connect to Kafka
    producer = wait_for_kafka(KAFKA_BROKER)

    # Load patient data
    patients = load_patient_data(DATA_DIR)
    if not patients:
        print("ERROR: No patient data found!")
        sys.exit(1)

    # Shared state for dynamic configuration
    shared_state = {
        "speed_seconds": speed,
        "state": "playing",
        "restart_signal": False
    }

    # Start streaming threads
    stop_event = threading.Event()
    threads = []
    
    # Start control listening thread
    ctrl_t = threading.Thread(
        target=control_listener,
        args=(KAFKA_BROKER, KAFKA_TOPIC_CONTROL, shared_state),
        daemon=True
    )
    ctrl_t.start()

    try:
        for label, patient_info in patients.items():
            t = threading.Thread(
                target=stream_patient,
                args=(producer, KAFKA_TOPIC_VITALS, patient_info, shared_state, stop_event),
                daemon=True,
            )
            threads.append(t)
            t.start()

        while not stop_event.is_set():
            if shared_state.get("restart_signal"):
                print("\n[MAIN] Restart signal received. Killing current streams...")
                for t in threads:
                    t.join(timeout=1.0)
                    
                shared_state["restart_signal"] = False
                threads = []
                print("[MAIN] Spawning fresh streams starting at row 0...")
                
                for label, patient_info in patients.items():
                    t = threading.Thread(
                        target=stream_patient,
                        args=(producer, KAFKA_TOPIC_VITALS, patient_info, shared_state, stop_event),
                        daemon=True,
                    )
                    threads.append(t)
                    t.start()
                    
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping streams...")
        stop_event.set()
        for t in threads:
            t.join(timeout=5)

    producer.flush()
    producer.close()
    print("Producer finished.")


if __name__ == '__main__':
    main()
