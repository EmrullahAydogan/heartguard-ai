import sys
import os
sys.path.append('/home/developer/Desktop/The MedGemma Impact Challenge/heartguard-ai/dashboard')
from data_client import get_clinician_report, get_alerts

pid = "3141080"
time, report = get_clinician_report(pid)
print(f"REPORT FOR {pid}: time={time}, report={report}")

alerts = get_alerts(pid, limit=5)
print(f"ALERTS FOR {pid}: {len(alerts)}")
