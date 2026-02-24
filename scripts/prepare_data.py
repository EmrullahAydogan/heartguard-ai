#!/usr/bin/env python3
"""
HeartGuard AI - Data Preparation Script
Filters CHF patients from eICU, builds profiles, selects demo patients.
"""

import pandas as pd
import numpy as np
import json
import os
import gzip
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EICU_DIR = os.path.join(os.path.dirname(BASE_DIR), "eicu-collaborative-research-database-demo-2.0.1")
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
PROFILES_DIR = os.path.join(DATA_DIR, "patient_profiles")

for d in [RAW_DIR, PROCESSED_DIR, PROFILES_DIR]:
    os.makedirs(d, exist_ok=True)


def load_eicu_table(name):
    """Load a gzipped CSV from eICU dataset."""
    path = os.path.join(EICU_DIR, f"{name}.csv.gz")
    if not os.path.exists(path):
        print(f"WARNING: {path} not found")
        return pd.DataFrame()
    print(f"Loading {name}...")
    return pd.read_csv(path)


def filter_chf_patients(diagnosis_df):
    """Filter CHF patients from diagnosis table."""
    chf_terms = [
        'congestive heart failure',
        'cardiomyopathy',
        'systolic dysfunction',
        'diastolic dysfunction',
    ]
    pattern = '|'.join(chf_terms)
    # Exclude rows that mention "not due to CHF" or "without CHF" or "absence of CHF"
    chf_mask = (
        diagnosis_df['diagnosisstring'].str.contains(pattern, case=False, na=False)
        & ~diagnosis_df['diagnosisstring'].str.contains(
            'not due to CHF|without CHF|absence of CHF', case=False, na=False
        )
    )
    chf_patients = diagnosis_df[chf_mask]['patientunitstayid'].unique()
    print(f"Found {len(chf_patients)} CHF patients")
    return chf_patients


def select_demo_patients(vitals_df, patient_df, chf_patient_ids):
    """Hand-picked demo patients based on comprehensive data analysis.
    A: Stable (341781) - 1,470 records, 88.8% complete, HR std=3.3
    B: Deteriorating (447543) - 1,826 records, 86.4% complete, clear HR 72→92 pattern
    C: Personalization (3141080) - 911 records, 72.2% complete, SpO2 mean=88.9%, HR mean=98.3
    """
    pid_a = 341781    # Stable: very low HR variability, 88.8% complete data
    pid_b = 447543    # Deteriorating: clear deterioration pattern, 1826 records
    pid_c = 3141080   # Personalization: chronically low SpO2=88.9%, elevated HR=98.3

    print("\n=== SELECTED DEMO PATIENTS (hand-picked from comprehensive analysis) ===")
    for label, pid in [('A (Stable)', pid_a), ('B (Deteriorating)', pid_b), ('C (Personalization)', pid_c)]:
        pv = vitals_df[vitals_df['patientunitstayid'] == pid]
        pv = pv.replace(0, np.nan)
        pv_valid = pv.dropna(subset=['heartrate', 'sao2'])
        pat = patient_df[patient_df['patientunitstayid'] == pid]
        age = pat['age'].values[0] if len(pat) > 0 else '?'
        gender = pat['gender'].values[0] if len(pat) > 0 else '?'
        print(f"  Patient {label}: ID={pid}, Age={age}, Gender={gender}, "
              f"Points={len(pv_valid)}, HR={pv_valid['heartrate'].mean():.1f}±{pv_valid['heartrate'].std():.1f}, "
              f"SpO2={pv_valid['sao2'].mean():.1f}±{pv_valid['sao2'].std():.1f}")

    return pid_a, pid_b, pid_c


def build_patient_profile(pid, patient_df, diagnosis_df, medication_df,
                          admission_drug_df, past_history_df, lab_df,
                          apache_df, vitals_df):
    """Build comprehensive patient profile."""
    profile = {'patient_id': int(pid)}

    # Patient demographics
    pat = patient_df[patient_df['patientunitstayid'] == pid]
    if len(pat) > 0:
        pat = pat.iloc[0]
        profile['age'] = str(pat.get('age', 'unknown'))
        profile['gender'] = str(pat.get('gender', 'unknown'))
        profile['ethnicity'] = str(pat.get('ethnicity', 'unknown'))
        profile['hospital_id'] = int(pat.get('hospitalid', 0))
        profile['unit_type'] = str(pat.get('unittype', 'unknown'))
        profile['unit_stay_type'] = str(pat.get('unitstaytype', 'unknown'))
        profile['hospital_discharge_status'] = str(pat.get('hospitaldischargestatus', 'unknown'))

    # Diagnoses
    diags = diagnosis_df[diagnosis_df['patientunitstayid'] == pid]
    chf_diags = diags[diags['diagnosisstring'].str.contains(
        'heart failure|cardiomyopathy|systolic dysfunction|diastolic dysfunction',
        case=False, na=False
    )]
    profile['primary_dx'] = chf_diags.iloc[0]['diagnosisstring'] if len(chf_diags) > 0 else 'CHF'
    profile['icd9_code'] = str(chf_diags.iloc[0].get('icd9code', '428.0')) if len(chf_diags) > 0 else '428.0'

    other_diags = diags[~diags.index.isin(chf_diags.index)]
    profile['comorbidities'] = other_diags['diagnosisstring'].tolist()[:10]

    # Past history
    if len(past_history_df) > 0:
        ph = past_history_df[past_history_df['patientunitstayid'] == pid]
        profile['past_history'] = ph['pasthistorypath'].tolist()[:10] if 'pasthistorypath' in ph.columns else []
    else:
        profile['past_history'] = []

    # Medications (current)
    meds = []
    if len(medication_df) > 0:
        med = medication_df[medication_df['patientunitstayid'] == pid]
        for _, row in med.iterrows():
            name = row.get('drugname', '')
            if pd.isna(name) or str(name).lower() == 'nan' or str(name).strip() == '':
                continue
            meds.append({
                'name': str(name),
                'dose': str(row.get('dosage', '')) if pd.notna(row.get('dosage')) else '',
                'route': str(row.get('routeadmin', '')) if pd.notna(row.get('routeadmin')) else '',
                'frequency': str(row.get('frequency', '')) if pd.notna(row.get('frequency')) else '',
            })

    # Admission drugs (pre-ICU)
    if len(admission_drug_df) > 0:
        adrug = admission_drug_df[admission_drug_df['patientunitstayid'] == pid]
        for _, row in adrug.iterrows():
            name = row.get('drugname', '')
            if pd.isna(name) or str(name).lower() == 'nan' or str(name).strip() == '':
                continue
            meds.append({
                'name': str(name),
                'dose': str(row.get('drugdosage', '')) if pd.notna(row.get('drugdosage')) else '',
                'route': str(row.get('drugroute', '')) if pd.notna(row.get('drugroute')) else '',
                'frequency': '',
                'source': 'admission',
            })
    profile['medications'] = meds[:20]

    # APACHE score
    if len(apache_df) > 0:
        ap = apache_df[apache_df['patientunitstayid'] == pid]
        if len(ap) > 0:
            ap = ap.iloc[0]
            profile['apache_score'] = float(ap.get('apachescore', 0)) if pd.notna(ap.get('apachescore')) else None
            profile['predicted_mortality'] = float(ap.get('predictedicumortality', 0)) if pd.notna(ap.get('predictedicumortality')) else None
        else:
            profile['apache_score'] = None
            profile['predicted_mortality'] = None

    # Latest lab values
    labs = {}
    if len(lab_df) > 0:
        plab = lab_df[lab_df['patientunitstayid'] == pid].sort_values('labresultoffset', ascending=False)
        lab_map = {
            'BNP': ['BNP', 'NT-proBNP', 'pro-BNP'],
            'creatinine': ['creatinine'],
            'potassium': ['potassium'],
            'sodium': ['sodium'],
            'troponin': ['troponin - I', 'troponin - T'],
        }
        for key, names in lab_map.items():
            for name in names:
                match = plab[plab['labname'].str.contains(name, case=False, na=False)]
                if len(match) > 0:
                    val = match.iloc[0].get('labresult')
                    if pd.notna(val):
                        try:
                            labs[key] = float(val)
                        except (ValueError, TypeError):
                            pass
                    break
    profile['latest_labs'] = labs

    # Compute baselines from first 6 hours of vitals
    pv = vitals_df[vitals_df['patientunitstayid'] == pid].copy()
    # Replace 0 values with NaN
    for col in ['heartrate', 'sao2', 'respiration', 'systemicsystolic', 'systemicdiastolic', 'systemicmean']:
        if col in pv.columns:
            pv.loc[pv[col] == 0, col] = np.nan
    pv = pv.sort_values('observationoffset')
    # First 6 hours = first 360 minutes offset
    baseline_data = pv[pv['observationoffset'] <= 360]
    if len(baseline_data) < 10:
        baseline_data = pv.head(max(10, len(pv) // 4))

    baselines = {}
    for col, key in [('heartrate', 'hr'), ('sao2', 'spo2'), ('respiration', 'rr'),
                     ('systemicsystolic', 'sbp'), ('temperature', 'temp')]:
        vals = baseline_data[col].dropna()
        if len(vals) > 5:
            # Remove outliers (beyond 3 std)
            mean = vals.mean()
            std = vals.std()
            if std > 0:
                vals = vals[(vals - mean).abs() <= 3 * std]
            baselines[f'{key}_mean'] = round(float(vals.mean()), 2)
            baselines[f'{key}_std'] = round(float(max(vals.std(), 0.1)), 2)
        else:
            baselines[f'{key}_mean'] = None
            baselines[f'{key}_std'] = None

    profile['baselines'] = baselines
    profile['estimated_nyha_class'] = None  # Will be estimated by MedGemma

    return profile


def extract_patient_vitals(pid, vitals_periodic_df, vitals_aperiodic_df, label):
    """Extract and save vital signs for a specific patient."""
    pv = vitals_periodic_df[vitals_periodic_df['patientunitstayid'] == pid].copy()
    pv = pv.sort_values('observationoffset')

    # Replace 0 values with NaN (sensor artifacts)
    for col in ['heartrate', 'sao2', 'respiration', 'systemicsystolic', 'systemicdiastolic', 'systemicmean']:
        if col in pv.columns:
            pv.loc[pv[col] == 0, col] = np.nan

    # Select and rename columns
    cols_map = {
        'observationoffset': 'offset_minutes',
        'heartrate': 'heart_rate',
        'sao2': 'spo2',
        'respiration': 'respiration',
        'temperature': 'temperature',
        'systemicsystolic': 'systolic_bp',
        'systemicdiastolic': 'diastolic_bp',
        'systemicmean': 'mean_bp',
    }

    available = {k: v for k, v in cols_map.items() if k in pv.columns}
    pv_clean = pv[list(available.keys())].rename(columns=available)

    # Try to supplement BP from aperiodic
    if len(vitals_aperiodic_df) > 0:
        pva = vitals_aperiodic_df[vitals_aperiodic_df['patientunitstayid'] == pid]
        if len(pva) > 0 and 'noninvasivesystolic' in pva.columns:
            # Fill missing BP values
            pass  # BP from periodic is usually sufficient

    # Drop rows where all vitals are NaN
    vital_cols = [c for c in pv_clean.columns if c != 'offset_minutes']
    pv_clean = pv_clean.dropna(subset=vital_cols, how='all')

    output_path = os.path.join(PROCESSED_DIR, f"patient_{label}_{pid}.csv")
    pv_clean.to_csv(output_path, index=False)
    print(f"  Saved {len(pv_clean)} vital records for Patient {label} (ID: {pid})")
    return pv_clean


def main():
    print("=" * 60)
    print("HeartGuard AI - Data Preparation")
    print("=" * 60)

    # Load all required tables
    diagnosis_df = load_eicu_table('diagnosis')
    patient_df = load_eicu_table('patient')
    vitals_periodic_df = load_eicu_table('vitalPeriodic')
    vitals_aperiodic_df = load_eicu_table('vitalAperiodic')
    medication_df = load_eicu_table('medication')
    admission_drug_df = load_eicu_table('admissiondrug')
    past_history_df = load_eicu_table('pastHistory')
    lab_df = load_eicu_table('lab')
    apache_df = load_eicu_table('apachePatientResult')

    # Step 1: Filter CHF patients
    print("\n--- Step 1: Filter CHF Patients ---")
    chf_patient_ids = filter_chf_patients(diagnosis_df)

    # Step 2: Select demo patients
    print("\n--- Step 2: Select Demo Patients ---")
    pid_a, pid_b, pid_c = select_demo_patients(
        vitals_periodic_df, patient_df, chf_patient_ids
    )

    if pid_a is None:
        print("Failed to select demo patients!")
        return

    # Step 3: Build profiles and extract vitals
    print("\n--- Step 3: Build Profiles & Extract Vitals ---")
    demo_patients = {'A': int(pid_a), 'B': int(pid_b), 'C': int(pid_c)}

    for label, pid in demo_patients.items():
        print(f"\nProcessing Patient {label} (ID: {pid})...")

        # Build profile
        profile = build_patient_profile(
            pid, patient_df, diagnosis_df, medication_df,
            admission_drug_df, past_history_df, lab_df,
            apache_df, vitals_periodic_df
        )

        # Save profile
        profile_path = os.path.join(PROFILES_DIR, f"patient_{label}_{pid}.json")
        with open(profile_path, 'w') as f:
            json.dump(profile, f, indent=2, default=str)
        print(f"  Saved profile to {profile_path}")

        # Extract vitals
        extract_patient_vitals(pid, vitals_periodic_df, vitals_aperiodic_df, label)

    # Save demo patient mapping
    mapping = {
        'patients': demo_patients,
        'labels': {
            'A': 'Stable Control',
            'B': 'Deteriorating (Main Demo)',
            'C': 'Personalization Demo',
        }
    }
    mapping_path = os.path.join(DATA_DIR, 'demo_patients.json')
    with open(mapping_path, 'w') as f:
        json.dump(mapping, f, indent=2)
    print(f"\nSaved demo patient mapping to {mapping_path}")

    print("\n" + "=" * 60)
    print("Data preparation complete!")
    print("=" * 60)


if __name__ == '__main__':
    main()
