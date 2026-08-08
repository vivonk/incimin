import clickhouse_connect
client = clickhouse_connect.get_client(host='127.0.0.1', port=8123)
query = "INSERT INTO system_changes (timestamp, repository_url, commit_sha, service_name, source, external_id, fetched_at, schema_version) VALUES (now(), 'repo', 'sha', 'srv', 'src', 'ext', now(), '1.0')"
client.command(query)
print("Done!")
