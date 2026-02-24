"""HeartGuard AI - MedGemma Prompt Templates"""

CLINICAL_REASONING_PROMPT = """You are a cardiology clinical decision support system analyzing a heart failure patient's current status.

PATIENT PROFILE:
- ID: {patient_id}, Age: {age}, Sex: {gender}
- Primary Diagnosis: {primary_dx}
- Comorbidities: {comorbidities}
- Current Medications: {medications}
- Baseline Severity Index: {apache_score}
- Estimated NYHA Class: {nyha_class}

PERSONALIZED BASELINES (from stable period):
- HR: μ={hr_mean} ± {hr_std} bpm
- SpO2: μ={spo2_mean} ± {spo2_std}%
- RR: μ={rr_mean} ± {rr_std} breaths/min

CURRENT VITAL TRENDS (last 24 hours):
- HR: current={hr_current}, 1hr_avg={hr_1hr}, 6hr_avg={hr_6hr}, z-score={z_hr}
- SpO2: current={spo2_current}, 1hr_avg={spo2_1hr}, 6hr_avg={spo2_6hr}, z-score={z_spo2}
- RR: current={rr_current}, 1hr_avg={rr_1hr}, 6hr_avg={rr_6hr}, z-score={z_rr}
- Temp: {temp_current}°C

RECENT LAB VALUES:
{lab_values}

CALCULATED RISK SCORE: {risk_score} (0.0=stable, 1.0=critical)
CALCULATED RISK CATEGORY: {risk_category} (stable | watch | warning | critical)
ACTIVE RISK FLAGS: {active_flags}
TRIGGER REASON: {trigger_reason}

Based on the CALCULATED RISK CATEGORY and the patient's vitals, provide:
1. "clinical_reasoning": 2-3 sentences explaining why the patient is in the {risk_category} category.
2. "recommendation": Specific clinical action recommendation appropriate for the {risk_category} level.
3. "key_concerns": List of specific concerns in priority order.

Respond in JSON format only."""


PATIENT_COMMUNICATION_PROMPT = """You are a patient communication assistant. Translate the following clinical assessment into patient-friendly language. Be caring but clear. Do not use medical jargon. The patient has heart failure.

Clinical Assessment: {clinical_reasoning}
Risk Level: {risk_category}
Recommendation: {recommendation}

Write a brief, empathetic notification message for the patient (3-4 sentences max). Start with 'Hi Patient {patient_name},' and how they're doing today."""


CLINICIAN_REPORT_PROMPT = """Generate a clinical summary report in SOAP format for the following heart failure patient's last monitoring period.

PATIENT PROFILE:
- ID: {patient_id}, Age: {age}, Sex: {gender}
- Primary Diagnosis: {primary_dx}
- Comorbidities: {comorbidities}
- Current Medications: {medications}

VITAL SIGNS SUMMARY:
- HR: current={hr_current}, baseline μ={hr_mean}±{hr_std}, z-score={z_hr}
- SpO2: current={spo2_current}, baseline μ={spo2_mean}±{spo2_std}, z-score={z_spo2}
- RR: current={rr_current}, baseline μ={rr_mean}±{rr_std}, z-score={z_rr}
- Trends: HR_trend={hr_trend}, SpO2_trend={spo2_trend}
- CURRENT RISK CATEGORY: {risk_category}

LAB VALUES:
{lab_values}

ALERTS DURING PERIOD:
{alerts_summary}

RELEVANT CLINICAL GUIDELINES (AHA/ACC):
{clinical_guidelines}

Format as:
S (Subjective): [patient symptoms/status]
O (Objective): [vital signs, lab values, monitoring data]
A (Assessment): [clinical assessment]
P (Plan): [recommended actions]"""


NYHA_ESTIMATION_PROMPT = """Based on the following heart failure patient profile, estimate their NYHA functional class (I, II, III, or IV).

PATIENT PROFILE:
- Age: {age}, Sex: {gender}
- Primary Diagnosis: {primary_dx}
- Comorbidities: {comorbidities}
- Baseline Severity Index: {apache_score}
- Resting HR: {hr_mean} bpm
- Resting SpO2: {spo2_mean}%
- Resting RR: {rr_mean} breaths/min
- Lab Values: {lab_values}

Respond with only: {{"nyha_class": <1-4>, "reasoning": "<brief explanation>"}}"""
