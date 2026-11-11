# Database connection pool exhausted

alerts: DBConnectionPoolExhausted, PostgresTooManyConnections, UpstreamTimeout
owner: DBA-Operations

## Symptoms
Applications log "connection pool exhausted" or "remaining connection slots are reserved".
Request latency rises and dependent APIs time out while the database itself may look healthy.

## Likely causes
- Connection leak in the application (connections not returned to the pool after errors)
- Long-running queries or locks holding connections
- Traffic spike or a new deployment that increased replica count without resizing the pool
- max_connections on PostgreSQL set lower than total pool size across all replicas

## Diagnosis
- Check active connections: `SELECT state, count(*) FROM pg_stat_activity GROUP BY state;`
- Find long-running queries: `SELECT pid, now()-query_start AS age, query FROM pg_stat_activity WHERE state <> 'idle' ORDER BY age DESC LIMIT 10;`
- Compare replica count x pool size with `SHOW max_connections;`

## Remediation
1. Identify and cancel long-running queries with pg_cancel_backend(pid) after confirming with the service owner
2. Roll back the most recent deployment of the affected service if the issue started right after it
3. Temporarily scale down non-critical consumers of the database to free connections
4. Increase the application pool size only if max_connections has headroom
5. Add PgBouncer in transaction mode as a long-term fix
