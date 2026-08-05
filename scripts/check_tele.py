import clickhouse_connect
import time

def query_logs(service_name: str, start_time_ns: int, end_time_ns: int):
    client = clickhouse_connect.get_client(host='127.0.0.1', port=8123)
    
    query = """
        SELECT timestamp, trace_id, body
        FROM signoz_logs.distributed_logs_v2
        WHERE timestamp >= {start_time:UInt64}
          AND timestamp <= {end_time:UInt64}
          AND resources_string['service.name'] = {service_name:String}
          AND severity_text = 'ERROR'
        ORDER BY timestamp DESC
        LIMIT 10
    """
    
    parameters = {
        'start_time': start_time_ns,
        'end_time': end_time_ns,
        'service_name': service_name
    }
    
    result = client.query(query, parameters=parameters)
    
    print(f"Found {len(result.result_rows)} ERROR logs for {service_name}:")
    for row in result.result_rows:
        print(f"Timestamp: {row[0]}, Trace ID: {row[1]}, Body: {row[2]}")

if __name__ == '__main__':
    # Default window: last 1 hour
    now_ns = int(time.time() * 1e9)
    hour_ago_ns = now_ns - int(3600 * 1e9)
    
    query_logs('paymentservice', hour_ago_ns, now_ns)
