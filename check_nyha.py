from influxdb_client import InfluxDBClient

client = InfluxDBClient(url="http://localhost:8087", token="heartguard-super-secret-token", org="heartguard")
query_api = client.query_api()

flux = 'from(bucket: "heartguard") |> range(start: 0) |> filter(fn: (r) => r._field == "nyha_class")'
tables = query_api.query(flux)
print(f"Total tables: {len(tables)}")
for table in tables:
    for record in table.records:
        print(f"Measurement: {record.get_measurement()}, Patient: {record.values.get('patient_id')}, Value: {record.get_value()}")

client.close()
