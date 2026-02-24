"""
HeartGuard AI - Layer 1: Vital Sign Analyzer
Computes sliding windows, z-scores, risk flags, trends and simple risk scores.
"""

from collections import deque
from dataclasses import dataclass, field
import math

from config import (
    WINDOW_5MIN, WINDOW_1HR, WINDOW_6HR, WINDOW_24HR,
    THRESHOLDS, ANOMALY_Z_THRESHOLD, CRITICAL_HR, CRITICAL_SPO2,
    CRITICAL_SBP, TREND_HR_THRESHOLD, TREND_SPO2_THRESHOLD,
    MIN_FLAGS_FOR_TRIGGER, PERIODIC_ASSESSMENT_INTERVAL,
)


@dataclass
class PatientState:
    """Maintains rolling state for a single patient."""
    patient_id: str
    baselines: dict = field(default_factory=dict)
    profile: dict = field(default_factory=dict)

    # Rolling windows (deques)
    hr_window: deque = field(default_factory=lambda: deque(maxlen=1440))
    spo2_window: deque = field(default_factory=lambda: deque(maxlen=1440))
    rr_window: deque = field(default_factory=lambda: deque(maxlen=1440))
    sbp_window: deque = field(default_factory=lambda: deque(maxlen=1440))
    temp_window: deque = field(default_factory=lambda: deque(maxlen=1440))

    message_count: int = 0
    last_medgemma_count: int = 0


def _window_mean(window, n):
    """Mean of last n items in window."""
    if not window:
        return None
    items = list(window)[-n:]
    valid = [x for x in items if x is not None]
    return sum(valid) / len(valid) if valid else None


def _window_std(window, n):
    """Std of last n items in window."""
    if not window:
        return None
    items = list(window)[-n:]
    valid = [x for x in items if x is not None]
    if len(valid) < 2:
        return None
    mean = sum(valid) / len(valid)
    variance = sum((x - mean) ** 2 for x in valid) / (len(valid) - 1)
    return math.sqrt(variance)


def compute_z_score(value, mean, std):
    """Compute z-score relative to personal baseline."""
    if value is None or mean is None or std is None or std == 0:
        return 0.0
    return (value - mean) / std


def analyze_vital(state: PatientState, message: dict) -> dict:
    """
    Analyze a single vital message. Returns analysis dict with:
    - window averages
    - z-scores
    - trends
    - risk flags
    - simple risk score
    - medgemma trigger info
    """
    state.message_count += 1

    # Extract values
    hr = message.get('heart_rate')
    spo2 = message.get('spo2')
    rr = message.get('respiration')
    sbp = message.get('systolic_bp')
    temp = message.get('temperature')

    # Append to windows
    state.hr_window.append(hr)
    state.spo2_window.append(spo2)
    state.rr_window.append(rr)
    state.sbp_window.append(sbp)
    state.temp_window.append(temp)

    baselines = state.baselines

    # --- Sliding Window Averages ---
    hr_5min = _window_mean(state.hr_window, WINDOW_5MIN)
    hr_1hr = _window_mean(state.hr_window, WINDOW_1HR)
    hr_6hr = _window_mean(state.hr_window, WINDOW_6HR)

    spo2_5min = _window_mean(state.spo2_window, WINDOW_5MIN)
    spo2_1hr = _window_mean(state.spo2_window, WINDOW_1HR)
    spo2_6hr = _window_mean(state.spo2_window, WINDOW_6HR)

    rr_5min = _window_mean(state.rr_window, WINDOW_5MIN)
    rr_1hr = _window_mean(state.rr_window, WINDOW_1HR)
    rr_6hr = _window_mean(state.rr_window, WINDOW_6HR)

    sbp_5min = _window_mean(state.sbp_window, WINDOW_5MIN)
    temp_5min = _window_mean(state.temp_window, WINDOW_5MIN)

    # --- Z-Scores (personal baselines) ---
    z_hr = compute_z_score(hr, baselines.get('hr_mean'), baselines.get('hr_std'))
    z_spo2 = compute_z_score(spo2, baselines.get('spo2_mean'), baselines.get('spo2_std'))
    z_rr = compute_z_score(rr, baselines.get('rr_mean'), baselines.get('rr_std'))

    # --- Trends (1hr avg - 6hr avg) ---
    hr_trend = (hr_1hr - hr_6hr) if hr_1hr is not None and hr_6hr is not None else 0.0
    spo2_trend = (spo2_1hr - spo2_6hr) if spo2_1hr is not None and spo2_6hr is not None else 0.0
    rr_trend = (rr_1hr - rr_6hr) if rr_1hr is not None and rr_6hr is not None else 0.0

    # --- Risk Flags ---
    flags = {
        'tachycardia': hr_5min is not None and hr_5min > THRESHOLDS['tachycardia'],
        'bradycardia': hr_5min is not None and hr_5min < THRESHOLDS['bradycardia'],
        'hypoxia': spo2_5min is not None and spo2_5min < THRESHOLDS['hypoxia'],
        'tachypnea': rr_5min is not None and rr_5min > THRESHOLDS['tachypnea'],
        'fever': temp_5min is not None and temp_5min > THRESHOLDS['fever'],
        'hypotension': sbp_5min is not None and sbp_5min < THRESHOLDS['hypotension'],
    }
    active_flags = [k for k, v in flags.items() if v]
    n_flags = len(active_flags)

    # --- Simple Risk Score (0.0 - 1.0) ---
    # Weighted combination of z-scores, trends, and flags
    z_component = min(1.0, (abs(z_hr) + abs(z_spo2) + abs(z_rr)) / 9.0)  # Max ~3 each

    trend_component = 0.0
    if hr_trend > 0:
        trend_component += min(0.5, hr_trend / 20.0)
    if spo2_trend < 0:
        trend_component += min(0.5, abs(spo2_trend) / 6.0)
    trend_component = min(1.0, trend_component)

    flag_component = min(1.0, n_flags / 3.0)

    # SpO2 absolute penalty
    spo2_penalty = 0.0
    if spo2 is not None:
        if spo2 < 88:
            spo2_penalty = 0.4
        elif spo2 < 90:
            spo2_penalty = 0.25
        elif spo2 < 93:
            spo2_penalty = 0.1

    simple_risk = min(1.0, (
        0.35 * z_component +
        0.25 * trend_component +
        0.20 * flag_component +
        0.20 * spo2_penalty
    ))

    # --- MedGemma Trigger Decision ---
    trigger_medgemma = False
    trigger_reason = None

    # a) Anomaly trigger
    if (abs(z_hr) > ANOMALY_Z_THRESHOLD or
            z_spo2 < -ANOMALY_Z_THRESHOLD or
            abs(z_rr) > ANOMALY_Z_THRESHOLD):
        trigger_medgemma = True
        trigger_reason = 'z_score_anomaly'

    if n_flags >= MIN_FLAGS_FOR_TRIGGER:
        trigger_medgemma = True
        trigger_reason = 'multiple_risk_flags'

    if hr is not None and hr > CRITICAL_HR:
        trigger_medgemma = True
        trigger_reason = 'critical_hr'
    if spo2 is not None and spo2 < CRITICAL_SPO2:
        trigger_medgemma = True
        trigger_reason = 'critical_spo2'
    if sbp is not None and sbp < CRITICAL_SBP:
        trigger_medgemma = True
        trigger_reason = 'critical_sbp'

    # b) Trend trigger
    if hr_trend > TREND_HR_THRESHOLD:
        trigger_medgemma = True
        trigger_reason = trigger_reason or 'trend_hr_rising'
    if spo2_trend < TREND_SPO2_THRESHOLD:
        trigger_medgemma = True
        trigger_reason = trigger_reason or 'trend_spo2_falling'

    # Count worsening trends
    bad_trends = sum([
        hr_trend > 5,
        spo2_trend < -1.5,
        rr_trend > 3,
    ])
    if bad_trends >= 2:
        trigger_medgemma = True
        trigger_reason = trigger_reason or 'multi_signal_deterioration'

    # c) Periodic assessment
    if (state.message_count - state.last_medgemma_count) >= PERIODIC_ASSESSMENT_INTERVAL:
        trigger_medgemma = True
        trigger_reason = trigger_reason or 'periodic_assessment'

    # Cooldown: don't trigger MedGemma too frequently (min 15 messages between triggers)
    MEDGEMMA_COOLDOWN = 60
    if trigger_medgemma and (state.message_count - state.last_medgemma_count) < MEDGEMMA_COOLDOWN:
        # Still within cooldown, only allow truly critical triggers
        # Use personalized thresholds: critical only if z-score is extreme
        is_truly_critical = (
            (hr is not None and hr > CRITICAL_HR and abs(z_hr) > 3.0) or
            (spo2 is not None and z_spo2 < -3.0 and spo2 < CRITICAL_SPO2) or
            (sbp is not None and sbp < CRITICAL_SBP)
        )
        if not is_truly_critical:
            trigger_medgemma = False
            trigger_reason = None

    # Risk category
    if simple_risk >= 0.8:
        risk_category = 'critical'
    elif simple_risk >= 0.6:
        risk_category = 'warning'
    elif simple_risk >= 0.3:
        risk_category = 'watch'
    else:
        risk_category = 'stable'

    return {
        # Current values
        'patient_id': state.patient_id,
        'timestamp': message.get('timestamp'),
        'heart_rate': hr,
        'spo2': spo2,
        'respiration': rr,
        'systolic_bp': sbp,
        'temperature': temp,

        # Window averages
        'hr_5min': hr_5min,
        'hr_1hr': hr_1hr,
        'hr_6hr': hr_6hr,
        'spo2_5min': spo2_5min,
        'spo2_1hr': spo2_1hr,
        'spo2_6hr': spo2_6hr,
        'rr_5min': rr_5min,
        'rr_1hr': rr_1hr,
        'rr_6hr': rr_6hr,

        # Z-scores
        'z_hr': round(z_hr, 2),
        'z_spo2': round(z_spo2, 2),
        'z_rr': round(z_rr, 2),

        # Trends
        'hr_trend': round(hr_trend, 2),
        'spo2_trend': round(spo2_trend, 2),
        'rr_trend': round(rr_trend, 2),

        # Flags
        'flags': flags,
        'active_flags': active_flags,
        'n_active_flags': n_flags,

        # Risk
        'risk_score': round(simple_risk, 3),
        'risk_category': risk_category,

        # MedGemma trigger
        'trigger_medgemma': trigger_medgemma,
        'trigger_reason': trigger_reason,

        # Message count
        'message_count': state.message_count,
    }
