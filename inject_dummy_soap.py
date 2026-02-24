from influxdb_client import InfluxDBClient, Point, WritePrecision
from datetime import datetime, timezone

client = InfluxDBClient(url="http://localhost:8087", token="heartguard-super-secret-token", org="heartguard")
from influxdb_client.client.write_api import SYNCHRONOUS
write_api = client.write_api(write_options=SYNCHRONOUS)

report_text = """S: Patient reports feeling increasingly short of breath over the past 24 hours.
O: HR elevated (129 bpm), SpO2 dropping (86%). Patient exhibits signs of acute fluid overload and respiratory distress.
A: Acute decompensated heart failure (NYHA Class IV).
P: Increase diuretic dosage immediately. Closely monitor fluid intake/output and vital signs. Consider transferring to higher acuity care if SpO2 continues to decline."""

point = (
    Point("clinician_reports")
    .tag("patient_id", "447543")
    .field("report", report_text)
    .time(datetime.now(timezone.utc), WritePrecision.S)
)

write_api.write(bucket="heartguard", record=point)
client.close()
print("Dummy SOAP report injected for Patient B (447543).")
