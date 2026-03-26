# Audit Logging in Etherion

## Overview

Etherion's audit logging system records every security-relevant event for forensic investigation, compliance reporting, and anomaly detection. Audit logs are immutable once written, stored in separate files from application logs, and automatically published to real-time monitoring channels.

## What Gets Logged

The audit logger records 16 event types across three dimensions: authentication, authorization, data access, and security violations.

### Event Types

```python
AUTHENTICATION_SUCCESS         # User logged in
AUTHENTICATION_FAILURE         # Bad credentials
AUTHORIZATION_SUCCESS          # User accessed allowed resource
AUTHORIZATION_FAILURE          # Permission denied
DATA_ACCESS                     # Query executed
DATA_MODIFICATION               # Mutation executed
ADMIN_ACTION                    # Admin-only operation
SECURITY_VIOLATION              # Attack detected
RATE_LIMIT_EXCEEDED             # Rate limiter triggered
INPUT_VALIDATION_FAILURE        # Malformed request
SQL_INJECTION_ATTEMPT           # SQL injection pattern detected
XSS_ATTEMPT                     # XSS pattern detected
CSRF_ATTEMPT                    # CSRF token invalid
FILE_UPLOAD                     # File uploaded
FILE_DOWNLOAD                   # File downloaded
API_ACCESS                      # API key used
SYSTEM_ERROR                    # Internal error
```

### Severity Levels

Events are classified as LOW, MEDIUM, HIGH, or CRITICAL:

- **LOW**: Routine access (authenticated user reading their own data)
- **MEDIUM**: Suspicious but not blocking (rate limit exceeded, failed auth, validation error)
- **HIGH**: Potential attack (authorization failure, input validation failure)
- **CRITICAL**: Active attack (SQL injection attempt, XSS attempt, security violation)

## Audit Log Structure

Each audit event is a JSON object stored in a file and published to Redis:

```json
{
  "event_id": "a1b2c3d4e5f6g7h8",
  "timestamp": "2026-03-26T14:23:45.123456Z",
  "event_type": "data_access",
  "severity": "low",
  "user_id": "user_12345",
  "tenant_id": "tenant_67890",
  "session_id": "f7e6d5c4b3a2",
  "ip_address": "203.0.113.42",
  "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
  "endpoint": "/graphql",
  "method": "POST",
  "request_id": null,
  "success": true,
  "error_message": null,
  "details": {
    "operation": "GetUserProfile",
    "data_type": "user",
    "fields_accessed": ["id", "email", "name"]
  },
  "metadata": null
}
```

### Field Meanings

- **event_id**: Unique deterministic hash of the event (SHA256 of timestamp + event data, truncated to 16 chars). Used to correlate duplicate events.

- **timestamp**: ISO 8601 UTC timestamp with microsecond precision. All audit events are in UTC for consistency.

- **event_type**: One of the 16 event types listed above.

- **severity**: LOW, MEDIUM, HIGH, or CRITICAL. Dashboards can filter/alert on severity.

- **user_id**, **tenant_id**: Identifies the actor and the affected tenant. If an event happens before authentication (e.g., failed login), user_id may be null.

- **session_id**: SHA256 hash of the JWT token itself. Used to group events within a session.

- **ip_address**: Client IP extracted from `X-Forwarded-For`, `X-Real-IP`, or the direct connection address. Reveals geographic location or proxy usage.

- **user_agent**: Browser/client identifier. Used to detect automated access or bots.

- **endpoint**: API endpoint path (e.g., "/graphql", "/api/v1/credentials").

- **method**: HTTP method (GET, POST, PUT, DELETE).

- **success**: Boolean. True if the operation succeeded, false if it failed.

- **error_message**: If success is false, the reason why (e.g., "Rate limit exceeded").

- **details**: Event-specific data. For DATA_MODIFICATION, this includes what was changed. For SECURITY_VIOLATION, it includes the attack type.

- **metadata**: Additional context (optional). Used for future extensibility.

## Log Files and Rotation

Audit logs are written to separate files by category:

```
/tmp/etherion/audit/
├─ audit.log              # General events (admin actions, system errors)
├─ audit.log.1            # Rotated backup
├─ auth.log               # Authentication events
├─ security.log           # Security violations
├─ data_access.log        # Data queries and access
└─ data_access.log.1      # Rotated backup
```

### Rotation Policy

- **Max File Size**: 100 MB (configurable via `AUDIT_LOG_MAX_FILE_SIZE`)
- **Backup Count**: 10 (up to 1 GB total per log file)
- **Retention**: 90 days (configurable via `AUDIT_LOG_RETENTION_DAYS`)

When a log file exceeds 100 MB, it's rotated:

```
audit.log (100 MB) → audit.log.1 (rotated)
audit.log (new, 0 MB) ← new events written
```

After 90 days, the oldest backups are deleted. This bounds storage and ensures compliance with data retention policies.

## Reading Audit Logs

### Example: Finding Suspicious Logins

```bash
# Extract failed authentications from the last hour
cat /tmp/etherion/audit/auth.log | \
  jq 'select(.event_type == "authentication_failure" and
            .timestamp > (now - 3600 | todate))' | \
  jq '.ip_address, .user_id, .error_message'

# Example output:
# "203.0.113.5"
# null
# "Invalid password"
#
# "203.0.113.5"
# null
# "User not found"
```

**Interpretation**: The same IP tried to log in twice with different user IDs. This is a brute-force attack.

### Example: Auditing Data Access

```bash
# Find all data access by user_12345 in the last 24 hours
cat /tmp/etherion/audit/data_access.log | \
  jq 'select(.user_id == "user_12345" and
            .timestamp > (now - 86400 | todate))' | \
  jq '{timestamp, user_id, operation: .details.operation, data_type: .details.data_type}'

# Example output:
# {
#   "timestamp": "2026-03-26T14:23:45.123456Z",
#   "user_id": "user_12345",
#   "operation": "GetUserProfile",
#   "data_type": "user"
# }
```

**Interpretation**: User 12345 queried user data once. This is normal.

### Example: Detecting Anomalies

```bash
# Count data access by user in the last hour
cat /tmp/etherion/audit/data_access.log | \
  jq 'select(.timestamp > (now - 3600 | todate))' | \
  jq -s 'group_by(.user_id) |
         map({user_id: .[0].user_id, count: length}) |
         sort_by(-.count)'

# Example output:
# [
#   {"user_id": "user_12345", "count": 150},
#   {"user_id": "user_67890", "count": 8},
#   {"user_id": "user_11111", "count": 5}
# ]
```

**Interpretation**: User 12345 made 150 queries in one hour. This is unusual (normal users make 5-20 queries/hour). Investigate whether user 12345's session is compromised.

## Real-Time Monitoring with Redis

Audit events are published to Redis channels for real-time dashboards:

```python
# Event is published to these channels:
redis.publish("audit:events", event_dict)           # All events
redis.publish("audit:low", event_dict)              # By severity
redis.publish("audit:critical", event_dict)
redis.publish("audit:tenant:tenant_67890", event_dict)  # By tenant
```

A monitoring dashboard can subscribe:

```python
import redis

r = redis.Redis()
pubsub = r.pubsub()

# Listen for all CRITICAL events
pubsub.subscribe("audit:critical")

for message in pubsub.listen():
    if message['type'] == 'message':
        event = json.loads(message['data'])
        alert_on_critical_event(event)
```

## Common Audit Queries

### 1. User Access Timeline

Show all actions by a user in a specific time window:

```python
from datetime import datetime, timedelta

query = f"""
SELECT timestamp, event_type, endpoint, method, success
FROM audit_events
WHERE user_id = 'user_12345'
  AND timestamp > '{(datetime.now() - timedelta(hours=1)).isoformat()}'
ORDER BY timestamp DESC
LIMIT 100
"""
```

### 2. Tenant Data Leakage Detection

Find accesses to data from different tenants in the same session:

```python
query = """
SELECT DISTINCT session_id, user_id, tenant_id, COUNT(*) as access_count
FROM audit_events
WHERE event_type IN ('data_access', 'data_modification')
GROUP BY session_id, user_id
HAVING COUNT(DISTINCT tenant_id) > 1
"""
```

If a single session/user accesses data from multiple tenants, it's a potential data leakage.

### 3. Credential Access

Track who accessed which credentials and when:

```python
query = """
SELECT timestamp, user_id, tenant_id, details->'service' as service
FROM audit_events
WHERE event_type = 'data_access'
  AND details->>'data_type' = 'credential'
ORDER BY timestamp DESC
LIMIT 50
"""
```

### 4. Failed Authorizations

Find users trying to access resources they don't own:

```python
query = """
SELECT timestamp, user_id, tenant_id, endpoint, error_message
FROM audit_events
WHERE event_type = 'authorization_failure'
  AND timestamp > NOW() - INTERVAL 24 HOURS
ORDER BY timestamp DESC
"""
```

### 5. Security Violations

Alert on active attacks:

```python
query = """
SELECT timestamp, ip_address, event_type, details
FROM audit_events
WHERE severity = 'CRITICAL'
  AND timestamp > NOW() - INTERVAL 1 HOUR
"""
```

## Compliance Use Cases

### SOC 2 Type II Reporting

Audit logs provide evidence for:
- **CC5.2**: Logic and integrity of processing is maintained
  - Data modification events show what changed and who changed it
- **CC6.1**: Logical access is restricted
  - Authorization failure events show access control is working
- **CC7.2**: System monitoring and user activity is monitored
  - All audit events demonstrate continuous logging

**Report**: Export all authorization failures and successful access events for the audit period.

### HIPAA Compliance

Audit logs track Protected Health Information (PHI) access:
- **Security Rule 164.312(b)**: Audit controls
  - Who accessed patient data, when, and why

**Report**: Weekly export of all PHI access (data_access events where data_type contains "patient" or "medical").

### PCI DSS Requirement 10

Audit logs meet "User activity and network transactions" logging requirements:
- **10.1**: Log access to cardholder data
  - Credential access events
- **10.2**: Log administrative actions
  - Admin action events
- **10.3**: Log failed access attempts
  - Authentication failure, authorization failure events

**Report**: Monthly export of all events with severity >= MEDIUM.

## Retention and Archival

### Default Retention (90 days)

Logs older than 90 days are automatically deleted. This balances storage costs with forensic availability.

### Custom Retention by Environment

```bash
# Production: 1 year
AUDIT_LOG_RETENTION_DAYS=365

# Staging: 30 days
AUDIT_LOG_RETENTION_DAYS=30

# Development: 7 days
AUDIT_LOG_RETENTION_DAYS=7
```

### Archival

For compliance, logs should be archived before deletion:

```python
# Before the cleanup job deletes logs, archive them
import tarfile
from datetime import datetime, timedelta

cutoff_date = datetime.now() - timedelta(days=90)

# Tar old logs
with tarfile.open(f"audit_archive_{cutoff_date.isoformat()}.tar.gz", "w:gz") as tar:
    for log_file in audit_dir.glob("*.log.*"):
        if log_file.stat().st_mtime < cutoff_date.timestamp():
            tar.add(log_file)

# Upload to S3 or cold storage
s3.upload_file(
    f"audit_archive_{cutoff_date.isoformat()}.tar.gz",
    bucket="etherion-audit-archive",
    key=f"archives/{cutoff_date.year}/{cutoff_date.month:02d}/"
)
```

## Performance Considerations

### Async Logging

Audit logging is non-blocking. Events are logged asynchronously using a thread pool:

```python
await audit_logger.log_event(event)  # Returns immediately
# Actual file write happens in background
```

This prevents audit logging from slowing down API responses.

### Redis Publishing

Events are published to Redis in parallel with file logging. If Redis is unavailable, events are still logged to files.

### Log Volume

A typical Etherion deployment generates:
- 100-500 events/second under normal load
- ~8.6 GB/day of audit logs (varies by verbosity)
- ~258 GB/month

Plan disk space accordingly.

## Troubleshooting

**Q: Audit logs are growing too fast**
- Reduce `AUDIT_LOG_RETENTION_DAYS`
- Disable logging of low-severity events (optional, requires code change)
- Archive old logs more frequently

**Q: I can't find an event**
- Check the correct log file (auth.log vs. data_access.log vs. security.log)
- Verify the timestamp format (ISO 8601 UTC)
- Use jq to parse JSON: `cat audit.log | jq '.user_id'`

**Q: Redis is slow**
- Reduce the number of channels (don't publish every event)
- Increase Redis memory and CPU
- Use Redis cluster for horizontal scaling

**Q: How do I integrate audit logs with a SIEM?**
- Stream logs from Redis to Kafka
- Ship from Kafka to your SIEM (Splunk, ELK, etc.)
- Parse JSON and map fields to your SIEM schema
