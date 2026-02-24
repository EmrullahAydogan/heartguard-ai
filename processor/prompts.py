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

AGENT CONTEXT (historical data retrieved by AI tools):
{context_history}

Based on the CALCULATED RISK CATEGORY, the patient's vitals, and the AGENT CONTEXT above, provide:
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


NYHA_ESTIMATION_PROMPT = """You are MedGemma, a cardiology AI specialist. Classify this heart failure patient's NYHA functional class using the structured reasoning framework below.

STEP 1 — ASSESS DISEASE SEVERITY (most important factor):
Score each indicator. A SINGLE severe indicator is enough to classify Class III+.
- APACHE Score: mild (<30), moderate (30-70), severe (70-100), critical (>100)
- Troponin: normal (<0.04), elevated (0.04-1.0), high (1.0-5.0), critical (>5.0)
- Creatinine: normal (<1.2), elevated (1.2-2.0), high (2.0-4.0), critical (>4.0)
- BNP: normal (<100), elevated (100-400), high (>400)
- Number of comorbidities: few (1-2), several (3-5), many (>5)

STEP 2 — CHECK VITAL SIGNS (secondary factor, can be misleading):
Resting vital signs may appear normal even in severely ill patients due to medications (beta-blockers, vasopressors) or being at bedrest. Do NOT let normal resting vitals override severe disease markers from Step 1.

STEP 3 — APPLY CLASSIFICATION:
- Class I: APACHE <30 AND normal biomarkers AND few comorbidities
- Class II: APACHE 30-70 OR mildly elevated biomarkers OR several comorbidities
- Class III: APACHE >70 OR Troponin >1.0 OR Creatinine >2.0 OR many comorbidities (>5) OR acute organ failure
- Class IV: APACHE >100 AND multi-organ dysfunction OR active pulmonary edema OR cardiogenic shock

EXAMPLES:
- Patient with APACHE=45, Troponin=0.02, HR=78, SpO2=97 → Class II (moderate severity, normal biomarkers)
- Patient with APACHE=112, Troponin=4.95, HR=80, SpO2=96, 10 comorbidities including acute renal failure and sepsis → Class IV (critical APACHE + critical Troponin + multi-organ dysfunction, ignore normal vitals)
- Patient with APACHE=67, Troponin=0.15, Creatinine=1.8, HR=90, SpO2=94 → Class III (severe APACHE + elevated biomarkers)

PATIENT PROFILE:
- Age: {age}, Sex: {gender}
- Primary Diagnosis: {primary_dx}
- Comorbidities: {comorbidities}
- APACHE Severity Score: {apache_score}
- Resting HR: {hr_mean} bpm
- Resting SpO2: {spo2_mean}%
- Resting RR: {rr_mean} breaths/min
- Lab Values: {lab_values}

Now follow Steps 1-3 above and respond with ONLY: {{"nyha_class": <1-4>, "reasoning": "<your step-by-step reasoning>"}}"""

