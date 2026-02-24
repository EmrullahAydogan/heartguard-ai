#!/usr/bin/env python3
"""
HeartGuard AI - Comprehensive eICU Dataset Analysis
Find the best 3 CHF patients for the demo:
  Patient A: STABLE (control)
  Patient B: DETERIORATING (main demo)
  Patient C: PERSONALIZATION (unusual baselines)
"""

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = "/home/developer/Desktop/The MedGemma Impact Challenge/eicu-collaborative-research-database-demo-2.0.1"

print("=" * 80)
print("HeartGuard AI - eICU Dataset Analysis for Best CHF Patients")
print("=" * 80)

# ── Step 1: Load tables ──────────────────────────────────────────────────────
print("\n[1/6] Loading eICU tables...")

patient = pd.read_csv(f"{DATA_DIR}/patient.csv.gz", compression='gzip')
print(f"  patient.csv: {len(patient)} rows")

vitals = pd.read_csv(f"{DATA_DIR}/vitalPeriodic.csv.gz", compression='gzip')
print(f"  vitalPeriodic.csv: {len(vitals)} rows")

diagnosis = pd.read_csv(f"{DATA_DIR}/diagnosis.csv.gz", compression='gzip')
print(f"  diagnosis.csv: {len(diagnosis)} rows")

lab = pd.read_csv(f"{DATA_DIR}/lab.csv.gz", compression='gzip')
print(f"  lab.csv: {len(lab)} rows")

medication = pd.read_csv(f"{DATA_DIR}/medication.csv.gz", compression='gzip')
print(f"  medication.csv: {len(medication)} rows")

apache = pd.read_csv(f"{DATA_DIR}/apachePatientResult.csv.gz", compression='gzip')
print(f"  apachePatientResult.csv: {len(apache)} rows")

# ── Step 2: Find CHF patients ────────────────────────────────────────────────
print("\n[2/6] Filtering CHF/Heart Failure patients...")

chf_keywords = ['heart failure', 'chf', 'congestive heart']

# Search in diagnosis table
diag_chf = diagnosis[
    diagnosis['diagnosisstring'].str.lower().str.contains('|'.join(chf_keywords), na=False)
]
chf_from_diag = set(diag_chf['patientunitstayid'].unique())

# Search in patient apacheadmissiondx
pat_chf = patient[
    patient['apacheadmissiondx'].str.lower().str.contains('|'.join(chf_keywords), na=False)
]
chf_from_pat = set(pat_chf['patientunitstayid'].unique())

chf_patient_ids = chf_from_diag | chf_from_pat
print(f"  CHF patients from diagnosis table: {len(chf_from_diag)}")
print(f"  CHF patients from patient admission dx: {len(chf_from_pat)}")
print(f"  Total unique CHF patients: {len(chf_patient_ids)}")

if len(chf_patient_ids) == 0:
    print("\nERROR: No CHF patients found. Checking what diagnoses exist...")
    print(diagnosis['diagnosisstring'].str.lower().str.extract(r'(cardiovascular[^|]*)')[0].dropna().unique()[:20])
    # Broaden search
    broader = ['cardiac', 'cardiomyopathy', 'ventricular', 'cardio']
    diag_broader = diagnosis[
        diagnosis['diagnosisstring'].str.lower().str.contains('|'.join(broader), na=False)
    ]
    print(f"\n  Broader cardiac search found: {len(diag_broader['patientunitstayid'].unique())} patients")
    print("  Sample diagnoses:")
    for d in diag_broader['diagnosisstring'].unique()[:20]:
        print(f"    - {d}")

# ── Step 3: Compute vital statistics per CHF patient ─────────────────────────
print("\n[3/6] Computing vital sign statistics for CHF patients...")

# Filter vitals to CHF patients only
vitals_chf = vitals[vitals['patientunitstayid'].isin(chf_patient_ids)].copy()
print(f"  Total vital records for CHF patients: {len(vitals_chf)}")

# Clean: treat 0 as missing for sao2 and temperature
vitals_chf['sao2_clean'] = vitals_chf['sao2'].replace(0, np.nan)
vitals_chf['temperature_clean'] = vitals_chf['temperature'].replace(0, np.nan)
vitals_chf['heartrate_clean'] = vitals_chf['heartrate']
vitals_chf['respiration_clean'] = vitals_chf['respiration']

results = []

for pid in chf_patient_ids:
    v = vitals_chf[vitals_chf['patientunitstayid'] == pid]
    if len(v) == 0:
        continue

    total = len(v)

    hr = v['heartrate_clean'].dropna()
    sp = v['sao2_clean'].dropna()
    rr = v['respiration_clean'].dropna()
    temp = v['temperature_clean'].dropna()

    # Completeness: rows where ALL 4 vitals are non-null (after cleaning)
    complete_mask = (
        v['heartrate_clean'].notna() &
        v['sao2_clean'].notna() &
        v['respiration_clean'].notna() &
        v['temperature_clean'].notna()
    )
    completeness = complete_mask.sum() / total * 100 if total > 0 else 0

    # Duration in hours
    duration_hrs = (v['observationoffset'].max() - v['observationoffset'].min()) / 60.0

    # Lab and medication counts
    lab_count = len(lab[lab['patientunitstayid'] == pid])
    med_count = len(medication[medication['patientunitstayid'] == pid])
    has_apache = pid in apache['patientunitstayid'].values

    # Split into first/second half for deterioration detection
    midpoint = v['observationoffset'].median()
    first_half = v[v['observationoffset'] <= midpoint]
    second_half = v[v['observationoffset'] > midpoint]

    hr_first = first_half['heartrate_clean'].dropna().mean()
    hr_second = second_half['heartrate_clean'].dropna().mean()
    sp_first = first_half['sao2_clean'].dropna().mean()
    sp_second = second_half['sao2_clean'].dropna().mean()
    rr_first = first_half['respiration_clean'].dropna().mean()
    rr_second = second_half['respiration_clean'].dropna().mean()

    row = {
        'patientunitstayid': pid,
        'total_records': total,
        'hr_count': len(hr), 'hr_mean': hr.mean(), 'hr_std': hr.std(), 'hr_min': hr.min(), 'hr_max': hr.max(),
        'spo2_count': len(sp), 'spo2_mean': sp.mean(), 'spo2_std': sp.std(), 'spo2_min': sp.min(), 'spo2_max': sp.max(),
        'rr_count': len(rr), 'rr_mean': rr.mean(), 'rr_std': rr.std(), 'rr_min': rr.min(), 'rr_max': rr.max(),
        'temp_count': len(temp), 'temp_mean': temp.mean(), 'temp_std': temp.std(), 'temp_min': temp.min(), 'temp_max': temp.max(),
        'completeness': completeness,
        'duration_hrs': duration_hrs,
        'lab_count': lab_count,
        'med_count': med_count,
        'has_apache': has_apache,
        'hr_first_half': hr_first, 'hr_second_half': hr_second,
        'spo2_first_half': sp_first, 'spo2_second_half': sp_second,
        'rr_first_half': rr_first, 'rr_second_half': rr_second,
        'hr_change': hr_second - hr_first if pd.notna(hr_first) and pd.notna(hr_second) else np.nan,
        'spo2_change': sp_second - sp_first if pd.notna(sp_first) and pd.notna(sp_second) else np.nan,
        'rr_change': rr_second - rr_first if pd.notna(rr_first) and pd.notna(rr_second) else np.nan,
    }
    results.append(row)

df = pd.DataFrame(results)
print(f"  CHF patients with vital data: {len(df)}")

# ── Step 4: Filter for quality ───────────────────────────────────────────────
print("\n[4/6] Filtering for data quality (200+ records, good completeness)...")

# Require minimum records and at least some data in each vital
df_quality = df[
    (df['total_records'] >= 200) &
    (df['hr_count'] >= 100) &
    (df['spo2_count'] >= 100) &
    (df['rr_count'] >= 100) &
    (df['temp_count'] >= 20)  # temperature often recorded less frequently
].copy()

print(f"  Patients meeting quality threshold: {len(df_quality)}")

if len(df_quality) == 0:
    print("\n  WARNING: No patients meet strict threshold. Relaxing criteria...")
    # Show distribution
    print(f"  Records distribution: {df['total_records'].describe()}")
    print(f"  HR count distribution: {df['hr_count'].describe()}")
    print(f"  SpO2 count distribution: {df['spo2_count'].describe()}")
    print(f"  RR count distribution: {df['rr_count'].describe()}")
    print(f"  Temp count distribution: {df['temp_count'].describe()}")
    print(f"  Completeness distribution: {df['completeness'].describe()}")

    # Relax to top patients by total records
    df_quality = df.nlargest(min(30, len(df)), 'total_records')
    print(f"\n  Using top {len(df_quality)} patients by record count instead.")

# ── Step 5: Rank candidates for each role ────────────────────────────────────
print("\n[5/6] Ranking candidates for each patient role...")

# ─── Patient A: STABLE ───
# Want: normal vitals, low variability, high completeness
def score_stable(row):
    score = 0
    # HR in normal range 60-90
    if 60 <= row['hr_mean'] <= 90:
        score += 20
    elif 55 <= row['hr_mean'] <= 95:
        score += 10
    # Low HR variability
    if pd.notna(row['hr_std']) and row['hr_std'] < 10:
        score += 15
    elif pd.notna(row['hr_std']) and row['hr_std'] < 15:
        score += 8
    # SpO2 in normal range 95-100
    if pd.notna(row['spo2_mean']) and 95 <= row['spo2_mean'] <= 100:
        score += 20
    elif pd.notna(row['spo2_mean']) and 93 <= row['spo2_mean']:
        score += 10
    # Low SpO2 variability
    if pd.notna(row['spo2_std']) and row['spo2_std'] < 2:
        score += 15
    elif pd.notna(row['spo2_std']) and row['spo2_std'] < 4:
        score += 8
    # Completeness
    score += row['completeness'] * 0.15
    # More records = better
    score += min(row['total_records'] / 100, 10)
    # Labs and meds
    score += min(row['lab_count'] / 10, 5)
    score += min(row['med_count'] / 5, 5)
    # Stable over time (small changes)
    if pd.notna(row['hr_change']) and abs(row['hr_change']) < 3:
        score += 10
    if pd.notna(row['spo2_change']) and abs(row['spo2_change']) < 1:
        score += 10
    return score

df_quality['stable_score'] = df_quality.apply(score_stable, axis=1)

# ─── Patient B: DETERIORATING ───
# Want: HR increases or SpO2 drops from first to second half
def score_deteriorating(row):
    score = 0
    # HR increases over time
    if pd.notna(row['hr_change']) and row['hr_change'] > 5:
        score += min(row['hr_change'] * 2, 30)
    # SpO2 drops over time
    if pd.notna(row['spo2_change']) and row['spo2_change'] < -1:
        score += min(abs(row['spo2_change']) * 5, 30)
    # RR increases over time
    if pd.notna(row['rr_change']) and row['rr_change'] > 2:
        score += min(row['rr_change'] * 3, 15)
    # Starts normal (first half)
    if pd.notna(row['hr_first_half']) and 60 <= row['hr_first_half'] <= 95:
        score += 10
    if pd.notna(row['spo2_first_half']) and row['spo2_first_half'] >= 94:
        score += 10
    # Completeness
    score += row['completeness'] * 0.1
    # More records = better
    score += min(row['total_records'] / 100, 10)
    # Labs and meds
    score += min(row['lab_count'] / 10, 5)
    score += min(row['med_count'] / 5, 5)
    return score

df_quality['deteriorating_score'] = df_quality.apply(score_deteriorating, axis=1)

# ─── Patient C: PERSONALIZATION ───
# Want: unusual but consistent baselines (low SpO2 OR high HR that's stable)
def score_personalization(row):
    score = 0
    # Naturally low SpO2 (88-93)
    if pd.notna(row['spo2_mean']) and 85 <= row['spo2_mean'] <= 93:
        score += 25
    # Or naturally high HR (>95)
    if pd.notna(row['hr_mean']) and row['hr_mean'] > 95:
        score += 20
    elif pd.notna(row['hr_mean']) and row['hr_mean'] > 90:
        score += 10
    # BUT consistent (low variability) - this is key
    if pd.notna(row['hr_std']) and row['hr_std'] < 12:
        score += 15
    if pd.notna(row['spo2_std']) and row['spo2_std'] < 3:
        score += 15
    # Stable over time (not deteriorating, just unusual baseline)
    if pd.notna(row['hr_change']) and abs(row['hr_change']) < 5:
        score += 10
    if pd.notna(row['spo2_change']) and abs(row['spo2_change']) < 2:
        score += 10
    # Completeness
    score += row['completeness'] * 0.1
    # More records = better
    score += min(row['total_records'] / 100, 10)
    # Labs and meds
    score += min(row['lab_count'] / 10, 5)
    score += min(row['med_count'] / 5, 5)
    return score

df_quality['personalization_score'] = df_quality.apply(score_personalization, axis=1)

# ── Print top 5 candidates per role ──────────────────────────────────────────
def print_candidate(row, rank):
    print(f"\n  #{rank} - Patient ID: {int(row['patientunitstayid'])}")
    print(f"    Total records: {int(row['total_records'])}  |  Duration: {row['duration_hrs']:.1f} hrs  |  Completeness: {row['completeness']:.1f}%")
    print(f"    HR:   n={int(row['hr_count'])}, mean={row['hr_mean']:.1f}, std={row['hr_std']:.1f}, range=[{row['hr_min']:.0f}-{row['hr_max']:.0f}]")
    print(f"    SpO2: n={int(row['spo2_count'])}, mean={row['spo2_mean']:.1f}, std={row['spo2_std']:.1f}, range=[{row['spo2_min']:.0f}-{row['spo2_max']:.0f}]")
    print(f"    RR:   n={int(row['rr_count'])}, mean={row['rr_mean']:.1f}, std={row['rr_std']:.1f}, range=[{row['rr_min']:.0f}-{row['rr_max']:.0f}]")
    if pd.notna(row['temp_mean']):
        print(f"    Temp: n={int(row['temp_count'])}, mean={row['temp_mean']:.1f}, std={row['temp_std']:.2f}, range=[{row['temp_min']:.1f}-{row['temp_max']:.1f}]")
    else:
        print(f"    Temp: n={int(row['temp_count'])}, insufficient data")
    print(f"    Labs: {int(row['lab_count'])}  |  Meds: {int(row['med_count'])}  |  APACHE: {'Yes' if row['has_apache'] else 'No'}")
    print(f"    HR 1st/2nd half: {row['hr_first_half']:.1f} -> {row['hr_second_half']:.1f} (change: {row['hr_change']:+.1f})")
    print(f"    SpO2 1st/2nd half: {row['spo2_first_half']:.1f} -> {row['spo2_second_half']:.1f} (change: {row['spo2_change']:+.1f})")

print("\n" + "=" * 80)
print("TOP 5 CANDIDATES FOR PATIENT A (STABLE)")
print("=" * 80)
top_stable = df_quality.nlargest(5, 'stable_score')
for i, (_, row) in enumerate(top_stable.iterrows(), 1):
    print_candidate(row, i)
    print(f"    STABLE SCORE: {row['stable_score']:.1f}")

print("\n" + "=" * 80)
print("TOP 5 CANDIDATES FOR PATIENT B (DETERIORATING)")
print("=" * 80)
top_deter = df_quality.nlargest(5, 'deteriorating_score')
for i, (_, row) in enumerate(top_deter.iterrows(), 1):
    print_candidate(row, i)
    print(f"    DETERIORATING SCORE: {row['deteriorating_score']:.1f}")

print("\n" + "=" * 80)
print("TOP 5 CANDIDATES FOR PATIENT C (PERSONALIZATION)")
print("=" * 80)
top_personal = df_quality.nlargest(5, 'personalization_score')
for i, (_, row) in enumerate(top_personal.iterrows(), 1):
    print_candidate(row, i)
    print(f"    PERSONALIZATION SCORE: {row['personalization_score']:.1f}")

# ── Step 6: Pick best 3 (no duplicates) and print full details ───────────────
print("\n\n" + "=" * 80)
print("FINAL RECOMMENDATIONS")
print("=" * 80)

# Pick best for each role, avoiding duplicates
chosen = {}
used_ids = set()

# Best stable
for _, row in top_stable.iterrows():
    pid = int(row['patientunitstayid'])
    if pid not in used_ids:
        chosen['A'] = row
        used_ids.add(pid)
        break

# Best deteriorating
for _, row in top_deter.iterrows():
    pid = int(row['patientunitstayid'])
    if pid not in used_ids:
        chosen['B'] = row
        used_ids.add(pid)
        break

# Best personalization
for _, row in top_personal.iterrows():
    pid = int(row['patientunitstayid'])
    if pid not in used_ids:
        chosen['C'] = row
        used_ids.add(pid)
        break

roles = {
    'A': 'STABLE (Control)',
    'B': 'DETERIORATING (Main Demo)',
    'C': 'PERSONALIZATION (Unusual Baselines)'
}

for role_key in ['A', 'B', 'C']:
    if role_key not in chosen:
        print(f"\n  WARNING: Could not find suitable Patient {role_key}")
        continue

    row = chosen[role_key]
    pid = int(row['patientunitstayid'])

    print(f"\n{'─' * 80}")
    print(f"  PATIENT {role_key}: {roles[role_key]}")
    print(f"  Patient Unit Stay ID: {pid}")
    print(f"{'─' * 80}")

    # Demographics
    pat_info = patient[patient['patientunitstayid'] == pid].iloc[0]
    print(f"\n  Demographics:")
    print(f"    Gender: {pat_info.get('gender', 'N/A')}")
    print(f"    Age: {pat_info.get('age', 'N/A')}")
    print(f"    Ethnicity: {pat_info.get('ethnicity', 'N/A')}")
    print(f"    Unit Type: {pat_info.get('unittype', 'N/A')}")
    print(f"    Admission Dx: {pat_info.get('apacheadmissiondx', 'N/A')}")
    print(f"    Discharge Status: {pat_info.get('unitdischargestatus', 'N/A')}")

    # Vital statistics
    print(f"\n  Vital Sign Statistics:")
    print(f"    Total records: {int(row['total_records'])}")
    print(f"    Monitoring duration: {row['duration_hrs']:.1f} hours ({row['duration_hrs']/24:.1f} days)")
    print(f"    Data completeness: {row['completeness']:.1f}%")
    print(f"    Heart Rate:   n={int(row['hr_count'])}, mean={row['hr_mean']:.1f}, std={row['hr_std']:.1f}, [{row['hr_min']:.0f}-{row['hr_max']:.0f}]")
    print(f"    SpO2:         n={int(row['spo2_count'])}, mean={row['spo2_mean']:.1f}, std={row['spo2_std']:.1f}, [{row['spo2_min']:.0f}-{row['spo2_max']:.0f}]")
    print(f"    Respiration:  n={int(row['rr_count'])}, mean={row['rr_mean']:.1f}, std={row['rr_std']:.1f}, [{row['rr_min']:.0f}-{row['rr_max']:.0f}]")
    if pd.notna(row['temp_mean']):
        print(f"    Temperature:  n={int(row['temp_count'])}, mean={row['temp_mean']:.1f}, std={row['temp_std']:.2f}, [{row['temp_min']:.1f}-{row['temp_max']:.1f}]")

    print(f"\n  Temporal Trends (1st half -> 2nd half):")
    print(f"    HR:   {row['hr_first_half']:.1f} -> {row['hr_second_half']:.1f} ({row['hr_change']:+.1f})")
    print(f"    SpO2: {row['spo2_first_half']:.1f} -> {row['spo2_second_half']:.1f} ({row['spo2_change']:+.1f})")
    print(f"    RR:   {row['rr_first_half']:.1f} -> {row['rr_second_half']:.1f} ({row['rr_change']:+.1f})")

    # Diagnoses
    pat_diags = diagnosis[diagnosis['patientunitstayid'] == pid]
    print(f"\n  Diagnoses ({len(pat_diags)} entries):")
    for _, d in pat_diags.iterrows():
        print(f"    - {d['diagnosisstring']}")
        if pd.notna(d.get('icd9code', np.nan)):
            print(f"      ICD: {d['icd9code']}")

    # Labs
    pat_labs = lab[lab['patientunitstayid'] == pid]
    print(f"\n  Lab Values ({len(pat_labs)} entries):")
    if len(pat_labs) > 0:
        lab_summary = pat_labs.groupby('labname').agg(
            count=('labresult', 'count'),
            mean=('labresult', 'mean'),
            last=('labresult', 'last')
        ).reset_index()
        for _, l in lab_summary.iterrows():
            print(f"    - {l['labname']}: count={int(l['count'])}, mean={l['mean']:.2f}, last={l['last']:.2f}")
    else:
        print(f"    (none)")

    # Medications
    pat_meds = medication[medication['patientunitstayid'] == pid]
    print(f"\n  Medications ({len(pat_meds)} entries):")
    if len(pat_meds) > 0:
        for drugname in pat_meds['drugname'].dropna().unique():
            subset = pat_meds[pat_meds['drugname'] == drugname]
            dosage = subset['dosage'].iloc[0] if len(subset) > 0 and 'dosage' in subset.columns else 'N/A'
            route = subset['routeadmin'].iloc[0] if len(subset) > 0 and 'routeadmin' in subset.columns else 'N/A'
            print(f"    - {drugname} | Dosage: {dosage} | Route: {route}")
    else:
        print(f"    (none)")

    # APACHE scores
    pat_apache = apache[apache['patientunitstayid'] == pid]
    if len(pat_apache) > 0:
        print(f"\n  APACHE Scores:")
        for _, a in pat_apache.iterrows():
            print(f"    - Version: {a.get('apacheversion', 'N/A')}, Score: {a.get('apachescore', 'N/A')}, "
                  f"Acute Physiology: {a.get('acutephysiologyscore', 'N/A')}")
            print(f"      Predicted ICU Mortality: {a.get('predictedicumortality', 'N/A')}")
            print(f"      Actual ICU Mortality: {a.get('actualicumortality', 'N/A')}")

# ── Summary table ────────────────────────────────────────────────────────────
print("\n\n" + "=" * 80)
print("SUMMARY TABLE")
print("=" * 80)
print(f"\n{'Role':<15} {'Patient ID':<15} {'Records':<10} {'Hours':<10} {'Complete%':<12} {'HR mean':<10} {'SpO2 mean':<10} {'Labs':<8} {'Meds':<8}")
print("-" * 98)
for role_key in ['A', 'B', 'C']:
    if role_key in chosen:
        r = chosen[role_key]
        print(f"Patient {role_key:<7} {int(r['patientunitstayid']):<15} {int(r['total_records']):<10} {r['duration_hrs']:<10.1f} {r['completeness']:<12.1f} {r['hr_mean']:<10.1f} {r['spo2_mean']:<10.1f} {int(r['lab_count']):<8} {int(r['med_count']):<8}")

print("\n\nAnalysis complete!")
