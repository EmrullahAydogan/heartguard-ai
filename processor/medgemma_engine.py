"""
HeartGuard AI - Layer 2: MedGemma Engine
Handles MedGemma API calls for clinical reasoning, patient communication,
and clinician reports.
"""

import json
import os
import re
import logging

import requests

from prompts import (
    CLINICAL_REASONING_PROMPT,
    PATIENT_COMMUNICATION_PROMPT,
    CLINICIAN_REPORT_PROMPT,
    NYHA_ESTIMATION_PROMPT,
)

logger = logging.getLogger(__name__)

# MedGemma via local server, HuggingFace Inference API, or local model
HF_TOKEN = os.environ.get('HF_TOKEN', '')
MEDGEMMA_MODEL = os.environ.get('MEDGEMMA_MODEL', 'google/medgemma-1.5-4b-it')
# Local MedGemma server (preferred)
MEDGEMMA_LOCAL_URL = os.environ.get('MEDGEMMA_LOCAL_URL', 'http://host.docker.internal:8888')
MEDGEMMA_API_URL = os.environ.get(
    'MEDGEMMA_API_URL',
    f'https://api-inference.huggingface.co/models/{MEDGEMMA_MODEL}'
)
USE_LOCAL_MODEL = os.environ.get('USE_LOCAL_MODEL', 'false').lower() == 'true'


def _call_medgemma(prompt: str) -> str:
    """Call MedGemma model. Priority: local server > fallback (no cloud API)."""
    # 1. Try local MedGemma server first (fastest, GPU-accelerated)
    if MEDGEMMA_LOCAL_URL:
        result = _call_local_server(prompt)
        if result:
            return result

    # 2. Try loading model directly (if configured)
    if USE_LOCAL_MODEL:
        return _call_local_model(prompt)

    # 3. Fallback to rule-based (skip cloud API — adds 60s timeout per call)
    return _fallback_response(prompt)


def _call_local_server(prompt: str) -> str:
    """Call local MedGemma server."""
    try:
        resp = requests.post(
            f'{MEDGEMMA_LOCAL_URL}/generate',
            json={'prompt': prompt, 'max_tokens': 512, 'temperature': 0.3},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get('generated_text', '')
    except requests.exceptions.RequestException:
        return ''


def _call_hf_api(prompt: str) -> str:
    """Call HuggingFace Inference API."""
    headers = {'Authorization': f'Bearer {HF_TOKEN}'}
    payload = {
        'inputs': prompt,
        'parameters': {'max_new_tokens': 512, 'temperature': 0.3, 'return_full_text': False}
    }
    try:
        resp = requests.post(MEDGEMMA_API_URL, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        result = resp.json()
        if isinstance(result, list) and len(result) > 0:
            return result[0].get('generated_text', '')
        elif isinstance(result, dict):
            return result.get('generated_text', str(result))
        return str(result)
    except requests.exceptions.RequestException as e:
        logger.warning(f"HF API call failed: {e}")
        return ''


def _call_local_model(prompt: str) -> str:
    """Call local MedGemma model (transformers)."""
    try:
        from transformers import AutoTokenizer, AutoModelForCausalLM
        import torch

        model_name = MEDGEMMA_MODEL
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )

        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        outputs = model.generate(**inputs, max_new_tokens=512, temperature=0.3)
        return tokenizer.decode(outputs[0], skip_special_tokens=True)

    except Exception as e:
        logger.warning(f"Local model call failed: {e}")
        return _fallback_response(prompt)


def _fallback_response(prompt: str) -> str:
    """Generate a rule-based fallback when MedGemma is unavailable."""
    # Return a meaningful rule-based response instead of empty string
    logger.warning("MedGemma unavailable — generating rule-based fallback response.")
    return json.dumps({
        "risk_level": "MODERATE",
        "reasoning": "MedGemma AI engine is currently unavailable. This is an automated rule-based assessment. Please consult the deterministic vital sign scoring for accurate risk evaluation.",
        "recommendation": "Continue monitoring. Review Z-score thresholds and vital trends on the dashboard for clinical decision support.",
        "confidence": "LOW — AI engine offline, using rule-based fallback"
    })


def _parse_json_response(text: str) -> dict:
    """Extract JSON from MedGemma response."""
    # Strip markdown code block wrapper if present
    cleaned = re.sub(r'```(?:json)?\s*', '', text).strip()
    cleaned = cleaned.rstrip('`').strip()

    # Try parsing cleaned text directly
    try:
        result = json.loads(cleaned)
        return _normalize_keys(result)
    except json.JSONDecodeError:
        pass

    # Try to find JSON block in text
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
    if json_match:
        try:
            result = json.loads(json_match.group())
            return _normalize_keys(result)
        except json.JSONDecodeError:
            pass

    # Try to find JSON with nested arrays
    json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if json_match:
        try:
            result = json.loads(json_match.group())
            return _normalize_keys(result)
        except json.JSONDecodeError:
            pass

    return {}


def _normalize_keys(d: dict) -> dict:
    """Normalize JSON keys to lowercase snake_case."""
    normalized = {}
    for k, v in d.items():
        lower_key = k.lower()
        normalized[lower_key] = v
    # Ensure risk_score is float
    if 'risk_score' in normalized:
        try:
            normalized['risk_score'] = float(normalized['risk_score'])
        except (ValueError, TypeError):
            pass
    return normalized


def clinical_reasoning(analysis: dict, state, context_history: str = None) -> dict:
    """
    Usage 1: Clinical risk assessment.
    Takes vital analysis and patient state, returns MedGemma assessment.
    """
    profile = state.profile
    baselines = state.baselines
    labs = profile.get('latest_labs', {})

    lab_str = '\n'.join([f"- {k}: {v}" for k, v in labs.items()]) if labs else "No recent labs available"

    meds = profile.get('medications', [])
    med_str = ', '.join([m.get('name', 'unknown') for m in meds[:10]]) if meds else 'None documented'

    comorbidities = profile.get('comorbidities', [])
    # Shorten comorbidity strings
    comorb_short = [c.split('|')[-1] if '|' in c else c for c in comorbidities[:5]]
    comorb_str = ', '.join(comorb_short) if comorb_short else 'None documented'

    prompt = CLINICAL_REASONING_PROMPT.format(
        patient_id=state.patient_id,
        age=profile.get('age', 'unknown'),
        gender=profile.get('gender', 'unknown'),
        primary_dx=profile.get('primary_dx', 'CHF'),
        comorbidities=comorb_str,
        medications=med_str,
        apache_score=profile.get('apache_score', 'N/A'),
        nyha_class=profile.get('estimated_nyha_class', 'N/A'),
        hr_mean=baselines.get('hr_mean', 'N/A'),
        hr_std=baselines.get('hr_std', 'N/A'),
        spo2_mean=baselines.get('spo2_mean', 'N/A'),
        spo2_std=baselines.get('spo2_std', 'N/A'),
        rr_mean=baselines.get('rr_mean', 'N/A'),
        rr_std=baselines.get('rr_std', 'N/A'),
        hr_current=analysis.get('heart_rate', 'N/A'),
        hr_1hr=analysis.get('hr_1hr', 'N/A'),
        hr_6hr=analysis.get('hr_6hr', 'N/A'),
        z_hr=analysis.get('z_hr', 0),
        spo2_current=analysis.get('spo2', 'N/A'),
        spo2_1hr=analysis.get('spo2_1hr', 'N/A'),
        spo2_6hr=analysis.get('spo2_6hr', 'N/A'),
        z_spo2=analysis.get('z_spo2', 0),
        rr_current=analysis.get('respiration', 'N/A'),
        rr_1hr=analysis.get('rr_1hr', 'N/A'),
        rr_6hr=analysis.get('rr_6hr', 'N/A'),
        z_rr=analysis.get('z_rr', 0),
        temp_current=analysis.get('temperature', 'N/A'),
        lab_values=lab_str,
        active_flags=', '.join(analysis.get('active_flags', [])) or 'None',
        trigger_reason=analysis.get('trigger_reason', 'periodic'),
        risk_score=analysis.get('risk_score', 0.0),
        risk_category=analysis.get('risk_category', 'stable'),
        context_history=context_history or "No previous tools used."
    )

    response_text = _call_medgemma(prompt)
    parsed = _parse_json_response(response_text)

    # Merge Rule-Based risk metrics with AI text reasoning
    result = {
        'risk_score': analysis.get('risk_score', 0.0),
        'risk_category': analysis.get('risk_category', 'stable'),
        'source': 'medgemma'
    }

    if parsed and 'clinical_reasoning' in parsed:
        result['clinical_reasoning'] = parsed['clinical_reasoning']
        result['recommendation'] = parsed.get('recommendation', '')
        result['key_concerns'] = parsed.get('key_concerns', [])
    else:
        rule_assessment = _rule_based_assessment(analysis, state)
        result['clinical_reasoning'] = rule_assessment.get('clinical_reasoning', 'Monitoring in progress.')
        result['recommendation'] = rule_assessment.get('recommendation', 'Continue monitoring.')
        result['key_concerns'] = rule_assessment.get('key_concerns', [])
        result['source'] = 'rule_based'

    return result


def patient_communication(patient_id: str, assessment: dict) -> str:
    """Usage 2: Generate patient-friendly message."""
    pid_map = {"341781": "A", "447543": "B", "3141080": "C"}
    p_name = pid_map.get(str(patient_id), str(patient_id))
    
    prompt = PATIENT_COMMUNICATION_PROMPT.format(
        patient_name=p_name,
        clinical_reasoning=assessment.get('clinical_reasoning', 'Monitoring in progress.'),
        risk_category=assessment.get('risk_category', 'stable'),
        recommendation=assessment.get('recommendation', 'Continue monitoring.'),
    )

    response = _call_medgemma(prompt)
    if not response or len(response) < 10:
        # Fallback
        cat = assessment.get('risk_category', 'stable')
        if cat == 'stable':
            return "Your vitals look good today! Keep up the great work with your medications and daily routine."
        elif cat == 'watch':
            return "We're noticing some small changes in your readings. Nothing to worry about yet, but please make sure to take your medications on time and get some rest."
        elif cat == 'warning':
            return "We've noticed some changes in your heart readings that we'd like to keep an eye on. Please check in with your healthcare team today if possible."
        else:
            return "Some of your readings need attention. Please contact your healthcare provider or go to your nearest clinic as soon as possible."

    return response


def clinician_report(analysis: dict, state, alerts_summary: str = '') -> str:
    """Usage 3: Generate SOAP format clinician report."""
    profile = state.profile
    baselines = state.baselines
    labs = profile.get('latest_labs', {})
    lab_str = '\n'.join([f"- {k}: {v}" for k, v in labs.items()]) if labs else "No labs"

    meds = profile.get('medications', [])
    med_str = ', '.join([m.get('name', 'unknown') for m in meds[:10]]) if meds else 'None'

    comorbidities = profile.get('comorbidities', [])
    comorb_short = [c.split('|')[-1] if '|' in c else c for c in comorbidities[:5]]
    
    # --- RAG Integration ---
    from rag_engine import get_rag_engine
    rag = get_rag_engine()
    
    # Build a query based on the patient's current abnormal status
    active_flags = analysis.get('active_flags', [])
    search_terms = []
    if 'tachycardia' in active_flags: search_terms.append("tachycardia")
    if 'hypoxia' in active_flags: search_terms.append("hypoxia")
    if analysis.get('spo2_trend', 0) < -1.0: search_terms.append("fluid overload congestion")
    
    clinical_guidelines = ""
    if search_terms:
        query_str = "heart failure " + " ".join(search_terms)
        clinical_guidelines = rag.retrieve_guidelines(query_str)
    
    if not clinical_guidelines:
        clinical_guidelines = "No specific guidelines triggered for current vital signs."
    # -----------------------

    prompt = CLINICIAN_REPORT_PROMPT.format(
        patient_id=state.patient_id,
        age=profile.get('age', 'unknown'),
        gender=profile.get('gender', 'unknown'),
        primary_dx=profile.get('primary_dx', 'CHF'),
        comorbidities=', '.join(comorb_short) if comorb_short else 'None',
        medications=med_str,
        hr_current=analysis.get('heart_rate', 'N/A'),
        hr_mean=baselines.get('hr_mean', 'N/A'),
        hr_std=baselines.get('hr_std', 'N/A'),
        z_hr=analysis.get('z_hr', 0),
        spo2_current=analysis.get('spo2', 'N/A'),
        spo2_mean=baselines.get('spo2_mean', 'N/A'),
        spo2_std=baselines.get('spo2_std', 'N/A'),
        z_spo2=analysis.get('z_spo2', 0),
        rr_current=analysis.get('respiration', 'N/A'),
        rr_mean=baselines.get('rr_mean', 'N/A'),
        rr_std=baselines.get('rr_std', 'N/A'),
        z_rr=analysis.get('z_rr', 0),
        hr_trend=analysis.get('hr_trend', 0),
        spo2_trend=analysis.get('spo2_trend', 0),
        risk_category=analysis.get('risk_category', 'stable'),
        lab_values=lab_str,
        alerts_summary=alerts_summary or 'No alerts during this period',
        clinical_guidelines=clinical_guidelines,
    )

    response = _call_medgemma(prompt)
    if not response or len(response) < 20:
        return _rule_based_soap(analysis, state)

    return response


def estimate_nyha(profile: dict) -> dict:
    """Estimate NYHA class from patient profile."""
    baselines = profile.get('baselines', {})
    labs = profile.get('latest_labs', {})
    lab_str = '\n'.join([f"- {k}: {v}" for k, v in labs.items()]) if labs else "No labs"

    prompt = NYHA_ESTIMATION_PROMPT.format(
        age=profile.get('age', 'unknown'),
        gender=profile.get('gender', 'unknown'),
        primary_dx=profile.get('primary_dx', 'CHF'),
        comorbidities=str(profile.get('comorbidities', [])[:5]),
        apache_score=profile.get('apache_score', 'N/A'),
        hr_mean=baselines.get('hr_mean', 'N/A'),
        spo2_mean=baselines.get('spo2_mean', 'N/A'),
        rr_mean=baselines.get('rr_mean', 'N/A'),
        lab_values=lab_str,
    )

    response = _call_medgemma(prompt)
    parsed = _parse_json_response(response)

    if not parsed or 'nyha_class' not in parsed:
        # Rule-based estimation
        return _rule_based_nyha(profile)

    return parsed


def _rule_based_assessment(analysis: dict, state) -> dict:
    """Rule-based fallback when MedGemma is unavailable."""
    risk_score = analysis.get('risk_score', 0.0)
    risk_category = analysis.get('risk_category', 'stable')
    active_flags = analysis.get('active_flags', [])
    z_hr = analysis.get('z_hr', 0)
    z_spo2 = analysis.get('z_spo2', 0)
    spo2 = analysis.get('spo2')
    hr = analysis.get('heart_rate')

    # Enhance risk score based on clinical context
    enhanced_risk = risk_score

    # BNP-based adjustment
    labs = state.profile.get('latest_labs', {})
    bnp = labs.get('BNP', 0)
    if bnp > 1000:
        enhanced_risk = min(1.0, enhanced_risk + 0.1)
    if bnp > 5000:
        enhanced_risk = min(1.0, enhanced_risk + 0.15)

    # Creatinine-based adjustment (renal function)
    creatinine = labs.get('creatinine', 1.0)
    if creatinine > 2.0:
        enhanced_risk = min(1.0, enhanced_risk + 0.05)

    # Determine category
    if enhanced_risk >= 0.8:
        risk_category = 'critical'
    elif enhanced_risk >= 0.6:
        risk_category = 'warning'
    elif enhanced_risk >= 0.3:
        risk_category = 'watch'
    else:
        risk_category = 'stable'

    # Generate reasoning
    reasons = []
    if abs(z_hr) > 2:
        direction = 'elevated' if z_hr > 0 else 'decreased'
        reasons.append(f"Heart rate is {direction} at {hr} bpm (z={z_hr:.1f} from personal baseline)")
    if z_spo2 < -2:
        reasons.append(f"SpO2 significantly below personal baseline at {spo2}% (z={z_spo2:.1f})")
    if 'tachycardia' in active_flags:
        reasons.append("Tachycardia detected")
    if 'hypoxia' in active_flags:
        reasons.append("Hypoxia detected")
    if analysis.get('hr_trend', 0) > 5:
        reasons.append(f"HR trending upward (+{analysis['hr_trend']:.1f} bpm/hr)")
    if analysis.get('spo2_trend', 0) < -2:
        reasons.append(f"SpO2 trending downward ({analysis['spo2_trend']:.1f}%/hr)")

    if not reasons:
        reasons.append("Vital signs within acceptable range for this patient's baseline")

    clinical_reasoning = '. '.join(reasons) + '.'

    # Recommendation
    if risk_category == 'critical':
        recommendation = "URGENT: Immediate clinical review recommended. Consider emergency department evaluation."
    elif risk_category == 'warning':
        recommendation = "Contact healthcare team within 4 hours. Verify medication adherence. Consider diuretic adjustment."
    elif risk_category == 'watch':
        recommendation = "Increase monitoring frequency. Ensure medication compliance. Schedule follow-up within 24-48 hours."
    else:
        recommendation = "Continue current monitoring schedule. No immediate intervention needed."

    # Key concerns
    key_concerns = []
    if z_spo2 < -1.5:
        key_concerns.append("SpO2 below personal baseline - possible fluid overload")
    if z_hr > 1.5:
        key_concerns.append("Elevated heart rate above baseline - compensatory mechanism")
    if bnp > 500:
        key_concerns.append(f"Elevated BNP ({bnp} pg/mL) suggests worsening heart failure")
    if creatinine > 1.5:
        key_concerns.append(f"Elevated creatinine ({creatinine}) - monitor renal function")
    if 'hypoxia' in active_flags and 'tachycardia' in active_flags:
        key_concerns.append("Combined hypoxia and tachycardia - possible decompensation")

    if not key_concerns:
        key_concerns.append("No significant concerns at this time")

    return {
        'risk_score': round(enhanced_risk, 3),
        'risk_category': risk_category,
        'clinical_reasoning': clinical_reasoning,
        'recommendation': recommendation,
        'key_concerns': key_concerns,
    }


def _rule_based_nyha(profile: dict) -> dict:
    """Rule-based NYHA estimation."""
    baselines = profile.get('baselines', {})
    apache = profile.get('apache_score')
    spo2_mean = baselines.get('spo2_mean', 96)
    hr_mean = baselines.get('hr_mean', 75)
    rr_mean = baselines.get('rr_mean', 16)

    score = 0
    reasons = []

    if apache is not None:
        if apache > 60:
            score += 2
            reasons.append(f"High APACHE score ({apache})")
        elif apache > 40:
            score += 1
            reasons.append(f"Moderate APACHE score ({apache})")

    if spo2_mean is not None and spo2_mean < 92:
        score += 2
        reasons.append(f"Low baseline SpO2 ({spo2_mean}%)")
    elif spo2_mean is not None and spo2_mean < 95:
        score += 1
        reasons.append(f"Mildly reduced baseline SpO2 ({spo2_mean}%)")

    if hr_mean is not None and hr_mean > 100:
        score += 1
        reasons.append(f"Resting tachycardia ({hr_mean} bpm)")

    if rr_mean is not None and rr_mean > 22:
        score += 1
        reasons.append(f"Elevated resting RR ({rr_mean})")

    bnp = profile.get('latest_labs', {}).get('BNP', 0)
    if bnp > 1000:
        score += 1
        reasons.append(f"Elevated BNP ({bnp})")

    if score >= 4:
        nyha = 4
    elif score >= 3:
        nyha = 3
    elif score >= 1:
        nyha = 2
    else:
        nyha = 1

    return {
        'nyha_class': nyha,
        'reasoning': '; '.join(reasons) if reasons else 'No significant findings suggesting advanced HF',
    }


def _rule_based_soap(analysis: dict, state) -> str:
    """Rule-based SOAP note fallback."""
    profile = state.profile
    risk_cat = analysis.get('risk_category', 'stable')

    status_map = {
        'stable': 'Patient is hemodynamically stable.',
        'watch': 'Patient showing early signs requiring closer observation.',
        'warning': 'Patient showing concerning vital sign changes.',
        'critical': 'Patient in acute decompensation, requires immediate attention.',
    }

    soap = f"""S (Subjective): Heart failure patient under continuous monitoring. {status_map.get(risk_cat, '')}

O (Objective):
- HR: {analysis.get('heart_rate', 'N/A')} bpm (baseline: {state.baselines.get('hr_mean', 'N/A')}±{state.baselines.get('hr_std', 'N/A')}, z={analysis.get('z_hr', 0)})
- SpO2: {analysis.get('spo2', 'N/A')}% (baseline: {state.baselines.get('spo2_mean', 'N/A')}±{state.baselines.get('spo2_std', 'N/A')}, z={analysis.get('z_spo2', 0)})
- RR: {analysis.get('respiration', 'N/A')} (baseline: {state.baselines.get('rr_mean', 'N/A')}±{state.baselines.get('rr_std', 'N/A')}, z={analysis.get('z_rr', 0)})
- Trends: HR {'+' if analysis.get('hr_trend', 0) > 0 else ''}{analysis.get('hr_trend', 0)}, SpO2 {'+' if analysis.get('spo2_trend', 0) > 0 else ''}{analysis.get('spo2_trend', 0)}
- Active flags: {', '.join(analysis.get('active_flags', [])) or 'None'}
- Risk score: {analysis.get('risk_score', 0):.2f} ({risk_cat})

A (Assessment): {risk_cat.upper()} - Risk score {analysis.get('risk_score', 0):.2f}/1.00

P (Plan): Continue telemetry monitoring. {'Urgent clinical review needed.' if risk_cat == 'critical' else 'Standard monitoring protocol.' if risk_cat == 'stable' else 'Increased monitoring frequency recommended.'}"""

    return soap
