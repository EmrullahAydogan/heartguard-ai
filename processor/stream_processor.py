#!/usr/bin/env python3
"""
HeartGuard AI - Stream Processor
Consumes vitals from Kafka, analyzes with Layer 1 (vital analyzer) and
Layer 2 (MedGemma engine), writes results to InfluxDB.

MedGemma calls are queued and processed sequentially - each call must
complete before the next one starts (GPU can only handle one at a time).
"""

import json
import os
import sys
import time
import logging
import threading
from queue import Queue

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable

from config import (
    KAFKA_BROKER, KAFKA_TOPIC_VITALS, KAFKA_TOPIC_ALERTS, DATA_DIR,
)
from vital_analyzer import PatientState, analyze_vital
from medgemma_engine import (
    clinical_reasoning, patient_communication, clinician_report,
    estimate_nyha,
)
from influx_writer import InfluxWriter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
)
logger = logging.getLogger('heartguard')


def load_patient_profiles(data_dir):
    """Load patient profiles and create initial states."""
    mapping_path = os.path.join(data_dir, 'demo_patients.json')
    if not os.path.exists(mapping_path):
        logger.error(f"Demo patients mapping not found: {mapping_path}")
        return {}

    with open(mapping_path) as f:
        mapping = json.load(f)

    states = {}
    for label, pid in mapping['patients'].items():
        profile_path = os.path.join(data_dir, 'patient_profiles', f'patient_{label}_{pid}.json')
        if not os.path.exists(profile_path):
            logger.warning(f"Profile not found: {profile_path}")
            continue

        with open(profile_path) as f:
            profile = json.load(f)

        pid_str = str(pid)
        state = PatientState(patient_id=pid_str)
        state.baselines = profile.get('baselines', {})
        state.profile = profile

        states[pid_str] = state
        logger.info(f"Loaded state for Patient {label} (ID: {pid_str})")

    return states


def wait_for_kafka(broker, max_retries=30, retry_interval=5):
    """Wait for Kafka to become available."""
    for attempt in range(max_retries):
        try:
            consumer = KafkaConsumer(
                KAFKA_TOPIC_VITALS,
                bootstrap_servers=broker,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                key_deserializer=lambda k: k.decode('utf-8') if k else None,
                group_id='heartguard-processor',
                auto_offset_reset='latest',
                enable_auto_commit=True,
                consumer_timeout_ms=5000,
                max_poll_interval_ms=600000,
                session_timeout_ms=30000,
                heartbeat_interval_ms=10000,
            )
            logger.info(f"Connected to Kafka at {broker}")
            return consumer
        except NoBrokersAvailable:
            logger.info(f"Kafka not ready (attempt {attempt + 1}/{max_retries}), waiting...")
            time.sleep(retry_interval)

    logger.error("Could not connect to Kafka!")
    sys.exit(1)


def create_alert_producer(broker):
    """Create Kafka producer for alerts."""
    try:
        return KafkaProducer(
            bootstrap_servers=broker,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8'),
        )
    except Exception as e:
        logger.warning(f"Failed to create alert producer: {e}")
        return None


def main():
    logger.info("=" * 60)
    logger.info("HeartGuard AI - Stream Processor Starting")
    logger.info(f"Kafka: {KAFKA_BROKER}")
    logger.info(f"Topics: {KAFKA_TOPIC_VITALS} -> {KAFKA_TOPIC_ALERTS}")
    logger.info("=" * 60)

    # Load patient profiles
    states = load_patient_profiles(DATA_DIR)
    if not states:
        logger.error("No patient profiles loaded!")
        sys.exit(1)

    # Connect to services
    consumer = wait_for_kafka(KAFKA_BROKER)
    alert_producer = create_alert_producer(KAFKA_BROKER)

    # Wait a bit for InfluxDB
    time.sleep(5)
    influx = InfluxWriter()
    
    from agent import MedGemmaAgent
    medgemma_agent = MedGemmaAgent(influx_client=influx)

    # 1. Write initial baselines (fast)
    for pid, state in states.items():
        influx.write_patient_baseline(
            pid, state.baselines,
            nyha_class=state.profile.get('nyha_class', 2) # Use default from profile
        )
    logger.info("Initial patient baselines written.")

    # 2. Perform AI-based NYHA Estimation (slow, but now non-blocking for basic UI)
    def async_nyha():
        for pid, state in states.items():
            try:
                nyha_result = estimate_nyha(state.profile)
                nyha_class = nyha_result.get('nyha_class', 2)
                state.profile['estimated_nyha_class'] = nyha_class
                logger.info(f"Patient {pid}: NYHA Class {nyha_class} (AI Estimated)")
                # Update baseline with AI estimate
                influx.write_patient_baseline(pid, state.baselines, nyha_class=nyha_class)
            except Exception as e:
                logger.warning(f"Failed AI NYHA estimation for {pid}: {e}")
    
    import threading
    threading.Thread(target=async_nyha, daemon=True).start()

    logger.info("Processor ready. Waiting for vital messages...")

    message_total = 0
    medgemma_calls = 0
    medgemma_lock = threading.Lock()

    # --- MedGemma Queue System ---
    # Only keep the LATEST trigger per patient (no backlog buildup)
    medgemma_queue = Queue(maxsize=0)
    # Track latest pending trigger per patient to avoid duplicates
    pending_patients = {}
    pending_lock = threading.Lock()

    def medgemma_worker():
        """Dedicated worker thread: processes MedGemma requests one at a time."""
        nonlocal medgemma_calls
        while True:
            # Block until a request is available
            item = medgemma_queue.get()
            if item is None:
                break  # Shutdown signal

            patient_id, analysis_copy, state, trigger_reason = item

            # Remove from pending tracker
            with pending_lock:
                pending_patients.pop(patient_id, None)

            try:
                logger.info(
                    f"[Patient {patient_id}] MedGemma processing: {trigger_reason} "
                    f"(risk={analysis_copy.get('risk_score', 0):.2f}, "
                    f"queue_remaining={medgemma_queue.qsize()})"
                )

                # Usage 1: Clinical reasoning (Now via Agentic ReAct Loop)
                assessment = medgemma_agent.run_clinical_reasoning(analysis_copy, state)
                
                # Add NYHA class for persistent storage with assessment
                assessment['nyha_class'] = state.profile.get('estimated_nyha_class', 0)
                
                influx.write_medgemma_assessment(
                    patient_id, assessment, trigger_reason
                )
                logger.info(
                    f"[Patient {patient_id}] Clinical reasoning complete "
                    f"(source={assessment.get('source', 'unknown')}, "
                    f"risk={assessment.get('risk_score', 'N/A')})"
                )

                # Usage 2: Patient communication
                patient_msg = patient_communication(patient_id, assessment)
                influx.write_patient_message(
                    patient_id, patient_msg,
                    assessment.get('risk_category', 'stable')
                )
                logger.info(f"[Patient {patient_id}] Patient message generated")

                # Usage 3: Clinician report (Always generate for visibility in demo)
                report = clinician_report(analysis_copy, state)
                influx.write_clinician_report(patient_id, report)
                logger.info(f"[Patient {patient_id}] Clinician SOAP report generated")

                risk_cat = assessment.get('risk_category', 'stable')

                # Generate alert if needed
                if risk_cat in ('warning', 'critical'):
                    severity = risk_cat
                    alert_msg = {
                        'patient_id': patient_id,
                        'timestamp': analysis_copy.get('timestamp'),
                        'alert_type': 'deterioration',
                        'severity': severity,
                        'risk_score': assessment.get('risk_score', 0),
                        'medgemma_analysis': assessment.get('clinical_reasoning', ''),
                        'trigger_reason': trigger_reason,
                    }

                    influx.write_alert(
                        patient_id, severity, 'deterioration',
                        assessment.get('clinical_reasoning', ''),
                        assessment.get('recommendation', ''),
                    )

                    if alert_producer:
                        alert_producer.send(
                            KAFKA_TOPIC_ALERTS,
                            key=patient_id,
                            value=alert_msg,
                        )

                    logger.warning(
                        f"[Patient {patient_id}] ALERT ({severity}): "
                        f"risk={assessment.get('risk_score', 0):.2f} - "
                        f"{assessment.get('clinical_reasoning', '')[:100]}"
                    )

                with medgemma_lock:
                    medgemma_calls += 1

                logger.info(
                    f"[Patient {patient_id}] MedGemma assessment #{medgemma_calls} complete "
                    f"(source={assessment.get('source', 'unknown')})"
                )

            except Exception as e:
                logger.error(f"[Patient {patient_id}] MedGemma worker error: {e}")

            medgemma_queue.task_done()

    # Start the MedGemma worker thread
    worker_thread = threading.Thread(target=medgemma_worker, daemon=True, name="medgemma-worker")
    worker_thread.start()
    logger.info("MedGemma worker thread started (sequential processing)")

    try:
        while True:
            # Poll for messages
            raw_messages = consumer.poll(timeout_ms=1000, max_records=100)

            for tp, messages in raw_messages.items():
                for msg in messages:
                    message = msg.value
                    patient_id = message.get('patient_id', msg.key)

                    if patient_id not in states:
                        states[patient_id] = PatientState(patient_id=patient_id)
                        logger.warning(f"Unknown patient {patient_id}, created minimal state")

                    state = states[patient_id]

                    # Layer 1: Vital Analysis (fast, always runs)
                    analysis = analyze_vital(state, message)

                    # Write vitals and risk scores to InfluxDB
                    influx.write_vitals(analysis)
                    influx.write_risk_scores(analysis, calculator='spark')

                    message_total += 1

                    # Layer 2: MedGemma (queued, sequential)
                    if analysis['trigger_medgemma']:
                        trigger_reason = analysis['trigger_reason']

                        # Deep copy analysis for thread safety
                        analysis_copy = dict(analysis)

                        with pending_lock:
                            # Replace any existing pending request for this patient
                            # (always keep the latest trigger data)
                            pending_patients[patient_id] = (
                                patient_id, analysis_copy, state, trigger_reason
                            )
                            # Only add to queue if this patient wasn't already pending
                            if patient_id not in [p[0] for p in list(medgemma_queue.queue)]:
                                medgemma_queue.put(
                                    (patient_id, analysis_copy, state, trigger_reason)
                                )
                                logger.info(
                                    f"[Patient {patient_id}] Queued for MedGemma: {trigger_reason} "
                                    f"(risk={analysis['risk_score']:.2f}, "
                                    f"queue_size={medgemma_queue.qsize()})"
                                )
                            else:
                                # Update the existing queue entry with latest data
                                # (the worker will pick up pending_patients[patient_id])
                                pass

                        state.last_medgemma_count = state.message_count

                    # Periodic log
                    if message_total % 100 == 0:
                        logger.info(
                            f"Processed {message_total} messages, "
                            f"{medgemma_calls} MedGemma assessments, "
                            f"queue={medgemma_queue.qsize()}"
                        )

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Signal worker to stop
        medgemma_queue.put(None)
        worker_thread.join(timeout=10)
        consumer.close()
        if alert_producer:
            alert_producer.close()
        influx.close()
        logger.info(f"Processor finished. Total: {message_total} msgs, {medgemma_calls} MedGemma calls")


if __name__ == '__main__':
    main()
