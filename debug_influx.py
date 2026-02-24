from influxdb_client import InfluxDBClient
import os

INFLUX_URL = "http://localhost:8087"  # External port
INFLUX_TOKEN = "heartguard-super-secret-token"
INFLUX_ORG = "heartguard"
INFLUX_BUCKET = "heartguard"

client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
query_api = client.query_api()

def check_measurement(measurement):
    print(f"\n--- Checking {measurement} ---")
    flux = f'from(bucket: "{INFLUX_BUCKET}") |> range(start: -1h) |> filter(fn: (r) => r._measurement == "{measurement}") |> limit(n: 5)'
    tables = query_api.query(flux)
    for table in tables:
        for record in table.records:
            print(f"Time: {record.get_time()}, Field: {record.get_field()}, Value: {record.get_value()}, Tags: {record.values.get('patient_id')}")

check_measurement("patient_baselines")
check_measurement("medgemma_assessments")
check_measurement("clinician_reports")
client.close()
