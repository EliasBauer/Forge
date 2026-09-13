# Forge alert runbook

Use the linked dashboard to establish the affected instance and interval before changing service state. HTTP 401 and 403 responses on the auth API are permission-denial outcomes, not server failures; investigate them through the API dashboard rather than treating them as failure alerts.

## ForgeMaintenanceActive
### Impact
Maintenance-sensitive alerts are intentionally inhibited.
### First three checks
1. Confirm the approved window and owner.
2. Verify the suppression deadline.
3. Check that maintenance work is progressing.
### Recovery criteria
Maintenance mode is cleared and suppression has ended.
### Escalation
Contact the maintenance owner if the window is unexpected.

## ForgeMaintenanceOverrun
### Impact
Maintenance continues beyond its alert-suppression window.
### First three checks
1. Contact the maintenance owner.
2. Confirm whether services are safe to restore.
3. Review active operational alerts.
### Recovery criteria
Maintenance mode is cleared or an approved window is established.
### Escalation
Escalate immediately to the incident commander when ownership is unclear.

## ForgePublicProbeDown
### Impact
Users may be unable to reach public workflows.
### First three checks
1. Open the API dashboard for the failing probe.
2. Check Nginx and web health.
3. Review probe and application logs for the interval.
### Recovery criteria
The public probe succeeds continuously for five minutes.
### Escalation
Page the application owner if the endpoint remains unavailable.

## ForgeTlsExpiryWarning
### Impact
Public HTTPS will fail if renewal does not complete.
### First three checks
1. Verify the served certificate expiry.
2. Check renewal automation state.
3. Confirm DNS and challenge reachability.
### Recovery criteria
The served certificate has more than 30 days remaining.
### Escalation
Assign the certificate owner during business hours.

## ForgeTlsExpiryCritical
### Impact
Public HTTPS is at imminent risk.
### First three checks
1. Verify the served certificate expiry.
2. Start emergency renewal.
3. Confirm the replacement certificate is served publicly.
### Recovery criteria
The served certificate has more than seven days remaining.
### Escalation
Page the certificate and ingress owners immediately.

## ForgeGraphqlServerFaultsWarning
### Impact
Some GraphQL workflows are failing.
### First three checks
1. Identify the dominant failing operation.
2. Inspect correlated web exceptions.
3. Compare failures with recent deployments.
### Recovery criteria
Server faults remain below three per ten minutes.
### Escalation
Assign the API owner if faults continue.

## ForgeGraphqlServerFaultsCritical
### Impact
GraphQL workflows are failing at high volume.
### First three checks
1. Identify the dominant failing operation.
2. Inspect web and dependency errors.
3. Consider rollback of a correlated deployment.
### Recovery criteria
Server faults remain below the critical floor for ten minutes.
### Escalation
Escalate to the API incident owner during the notification window.

## ForgeGraphqlErrorRatioInfo
### Impact
A meaningful share of GraphQL requests returns errors.
### First three checks
1. Break errors down by status and operation.
2. Confirm traffic is representative.
3. Compare the ratio with deployments and dependencies.
### Recovery criteria
The error ratio remains at or below five percent for 15 minutes.
### Escalation
Create follow-up work if the baseline remains elevated.

## ForgeApiLatencyWarning
### Impact
API workflows are noticeably slow.
### First three checks
1. Break latency down by API.
2. Check web process saturation.
3. Correlate dependency latency and recent releases.
### Recovery criteria
P95 API latency remains at or below one second for 15 minutes.
### Escalation
Assign the application owner if latency persists.

## ForgeApiLatencyCritical
### Impact
Active API workflows are severely degraded.
### First three checks
1. Identify the slowest API paths.
2. Check web and host saturation.
3. Inspect dependency latency and errors.
### Recovery criteria
P95 latency remains below three seconds with representative traffic.
### Escalation
Escalate to the application incident owner during the notification window.

## ForgePostgresDown
### Impact
Database-backed application and worker operations may fail.
### First three checks
1. Check PostgreSQL container health.
2. Inspect recent PostgreSQL logs.
3. Verify exporter connectivity to the database.
### Recovery criteria
The PostgreSQL target remains up and queries succeed.
### Escalation
Page the database owner if recovery is not immediate.

## ForgeRedisDown
### Impact
Caching and asynchronous task delivery may fail.
### First three checks
1. Check Redis container health.
2. Inspect recent Redis logs.
3. Verify clients can connect and issue a ping.
### Recovery criteria
The Redis target remains up and client operations succeed.
### Escalation
Page the platform owner if recovery is not immediate.

## ForgeMeilisearchTargetDown
### Impact
Search telemetry is unavailable and search may be degraded.
### First three checks
1. Check the scrape target error.
2. Check Meilisearch container health.
3. Inspect recent service logs.
### Recovery criteria
The Meilisearch target remains up for five minutes.
### Escalation
Assign the search owner if the target remains down.

## ForgeMeilisearchUnavailable
### Impact
Search-backed workflows are unavailable.
### First three checks
1. Check the `meilisearch_health` blackbox probe and Meilisearch container health.
2. Inspect resource pressure and startup logs.
3. Verify index and storage availability.
### Recovery criteria
The internal `/health` probe remains successful and a search request succeeds.
### Escalation
Escalate to the search owner during the notification window.

## ForgePgbouncerSaturation
### Impact
New database clients are approaching the connection limit.
### First three checks
1. Inspect active clients by pool.
2. Identify connection-heavy services.
3. Check PostgreSQL connection capacity.
### Recovery criteria
Active clients remain at or below 85 percent of the limit.
### Escalation
Assign the database owner if saturation persists.

## ForgePgbouncerWaitingClients
### Impact
Database requests are queued behind connection capacity.
### First three checks
1. Inspect waiting clients by pool.
2. Check active and idle client counts.
3. Verify PostgreSQL health and capacity.
### Recovery criteria
No clients remain waiting for five minutes.
### Escalation
Escalate to the database owner during the notification window.

## ForgeCeleryQueueAgeWarning
### Impact
Background work is delayed.
### First three checks
1. Identify the affected queue.
2. Inspect worker throughput and concurrency.
3. Find the oldest task type.
### Recovery criteria
All queue ages remain at or below ten minutes.
### Escalation
Assign the worker owner if the backlog grows.

## ForgeCeleryQueueAgeCritical
### Impact
Background workflows are severely delayed.
### First three checks
1. Identify the affected queue and oldest task.
2. Inspect worker health and throughput.
3. Check broker and dependency health.
### Recovery criteria
All queue ages remain below 30 minutes and continue falling.
### Escalation
Escalate to the worker incident owner during the notification window.

## ForgeCeleryNoWorker
### Impact
No background tasks can be processed.
### First three checks
1. Check worker container health.
2. Inspect worker startup logs.
3. Verify broker connectivity.
### Recovery criteria
At least one worker remains available and accepts tasks.
### Escalation
Escalate to the worker owner during the notification window.

## ForgeCeleryFailureRatio
### Impact
A significant share of background tasks is failing.
### First three checks
1. Identify the dominant failing task.
2. Inspect its exceptions and arguments safely.
3. Compare failures with deployments and dependencies.
### Recovery criteria
Failure ratio remains at or below ten percent or fewer than five tasks fail.
### Escalation
Create follow-up work if the elevated baseline persists.

## ForgeHostCpuHigh
### Impact
Services may experience contention and latency.
### First three checks
1. Identify the busiest containers and processes.
2. Compare CPU use with request and job load.
3. Review recent workload or deployment changes.
### Recovery criteria
CPU usage remains at or below 90 percent for 20 minutes.
### Escalation
Assign the platform owner if contention persists.

## ForgeMemoryLow
### Impact
Containers risk memory pressure and eviction.
### First three checks
1. Identify memory-heavy containers.
2. Check host swap and reclaim activity.
3. Review recent workload changes.
### Recovery criteria
Available memory remains at or above ten percent.
### Escalation
Assign the platform owner if pressure persists.

## ForgeMemoryCritical
### Impact
Service termination or host instability is imminent.
### First three checks
1. Identify memory-heavy containers.
2. Check for active OOM events.
3. Safely relieve pressure or add capacity.
### Recovery criteria
Available memory remains above five percent and is stable.
### Escalation
Page the platform owner immediately.

## ForgeApplicationContainerOom
### Impact
An application or dependency process was terminated.
### First three checks
1. Identify the affected Compose service.
2. Inspect its memory trend and restart logs.
3. Check host memory pressure.
### Recovery criteria
The service is healthy and no further OOM events occur.
### Escalation
Page the owning service team for repeated events.

## ForgeFilesystemLow
### Impact
Persistent services may soon be unable to write data.
### First three checks
1. Identify the affected mountpoint.
2. Inspect growth by service and directory.
3. Confirm retention and capacity plans.
### Recovery criteria
Available space remains at or above 15 percent.
### Escalation
Assign the platform owner if capacity cannot be restored promptly.

## ForgeFilesystemPredictedFull
### Impact
Current growth will fill a filesystem within one day.
### First three checks
1. Confirm the six-hour growth trend.
2. Identify the responsible files or service.
3. Review safe retention and expansion options.
### Recovery criteria
The 24-hour prediction remains non-negative.
### Escalation
Assign the platform owner before capacity is exhausted.

## ForgeFilesystemCritical
### Impact
Persistent services face imminent write failures.
### First three checks
1. Identify the affected mountpoint.
2. Find the fastest-growing safe-to-review data.
3. Reclaim space or add capacity safely.
### Recovery criteria
Available space remains above five percent and is stable.
### Escalation
Page the platform owner immediately.

## ForgeBackupTelemetryMissing
### Impact
Operators cannot verify the latest successful backup age.
### First three checks
1. Check the backup metrics producer.
2. Check the Pushgateway series.
3. Review the most recent backup job logs.
### Recovery criteria
The success timestamp is present and credible.
### Escalation
Assign the backup owner if telemetry remains absent.

## ForgeBackupStale
### Impact
The recovery point objective is at risk.
### First three checks
1. Inspect the latest backup job result.
2. Verify local artifact creation.
3. Check transfer destination health.
### Recovery criteria
A successful backup timestamp is less than 26 hours old.
### Escalation
Assign the backup owner during business hours.

## ForgeBackupCritical
### Impact
Recoverable data may be more than two days old.
### First three checks
1. Preserve failed job evidence.
2. Identify the last good local and remote backup.
3. Start a controlled backup after correcting the cause.
### Recovery criteria
A verified successful backup is less than 50 hours old.
### Escalation
Page the backup and incident owners immediately.

## ForgeBackupTransferFailed
### Impact
The newest backup may not exist off host.
### First three checks
1. Inspect transfer logs.
2. Verify destination reachability and capacity.
3. Preserve the local backup artifact.
### Recovery criteria
A transfer success timestamp is newer than the failure timestamp.
### Escalation
Page the backup owner if retry cannot begin safely.

## ForgeRestoreVerificationMissing
### Impact
Operators cannot confirm that backups can be restored.
### First three checks
1. Check the verification metrics producer.
2. Inspect the scheduled job state.
3. Review the most recent verification logs.
### Recovery criteria
A credible restore-success timestamp is present.
### Escalation
Assign the backup owner if telemetry remains absent.

## ForgeRestoreVerificationStale
### Impact
Recent backup restorability has not been demonstrated.
### First three checks
1. Inspect scheduled verification runs.
2. Identify the last successful restore test.
3. Review storage and test-environment health.
### Recovery criteria
A successful verification is less than eight days old.
### Escalation
Assign the backup owner during business hours.

## ForgeRestoreVerificationCritical
### Impact
Backup restorability has been unverified for over two weeks.
### First three checks
1. Preserve failed verification evidence.
2. Prepare a controlled restore test.
3. Validate backup and test-environment integrity.
### Recovery criteria
A successful verification is less than 15 days old.
### Escalation
Escalate to the backup and incident owners during the notification window.

## ForgeTelemetryTargetDown
### Impact
Operational visibility is incomplete.
### First three checks
1. Identify the failed scrape job and target.
2. Check target health and connectivity.
3. Inspect exporter or service logs.
### Recovery criteria
The target remains up for five minutes.
### Escalation
Page the observability owner if visibility cannot be restored.

## ForgeRuleEvaluationFailures
### Impact
Recording rules or alerts may be missing or incorrect.
### First three checks
1. Identify the failing rule group.
2. Inspect Prometheus evaluation errors.
3. Validate the loaded rule files.
### Recovery criteria
No rule evaluation failures occur for ten minutes.
### Escalation
Page the observability owner immediately.

## ForgeNotificationDeliveryFailures
### Impact
Operational alerts may not reach responders.
### First three checks
1. Identify the failing integration.
2. Inspect Alertmanager delivery errors.
3. Verify integration endpoint health and credentials.
### Recovery criteria
Notifications deliver successfully with no new failures.
### Escalation
Page the observability owner through a working alternate channel.
