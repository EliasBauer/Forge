from __future__ import annotations

from typing import Any

from dashboardlib import Dashboard, Panel, Query

OVERVIEW_LINK = ("Overview", "/d/forge-overview?${__url_time_range}")
LOGS_LINK = ("Logs and Changes", "/d/forge-logs-changes?${__url_time_range}")
SERVICE_LOG_LINK = (
    "Service logs",
    "/d/forge-logs-changes?var-compose_service="
    "${__field.labels.compose_service}&${__url_time_range}",
)

DASHBOARDS: tuple[Dashboard, ...] = (
    Dashboard(
        folder="Operations",
        uid="forge-overview",
        title="Forge Overview",
        panels=(
            Panel(
                "Public probes",
                (Query('min by (probe) (probe_success{job="blackbox"})', "{{probe}}"),),
                kind="stat",
                width=4,
                thresholds=((None, "red"), (1, "green")),
            ),
            Panel(
                "GraphQL outcomes / server faults",
                (
                    Query(
                        'round(sum(increase(graphql_requests_total{status="error"}[15m])))',
                        "Error outcomes",
                    ),
                    Query(
                        'round(sum(increase(graphql_errors_total{code=~"INTERNAL_SERVER_ERROR|unknown"}[15m])))',
                        "Server faults",
                        thresholds=((None, "green"), (3, "orange"), (10, "red")),
                    ),
                ),
                kind="stat",
                width=4,
                description=(
                    "GraphQL error outcomes include expected client and permission "
                    "outcomes; server faults isolate actionable backend failures."
                ),
            ),
            Panel(
                "API p95 latency",
                (Query("forge:api_request_duration_seconds:p95_5m", "{{api}}"),),
                kind="stat",
                unit="s",
                width=4,
                thresholds=((None, "green"), (1, "orange"), (3, "red")),
            ),
            Panel(
                "Backup age / transfer state",
                (
                    Query(
                        "time() - backup_last_success_timestamp_seconds",
                        "Backup age",
                    ),
                    Query(
                        "backup_transfer_last_failure_timestamp_seconds > bool "
                        "backup_transfer_last_success_timestamp_seconds",
                        "Latest transfer failed",
                        unit="short",
                        thresholds=((None, "green"), (1, "red")),
                    ),
                ),
                kind="stat",
                unit="s",
                width=4,
                thresholds=(
                    (None, "green"),
                    (26 * 3600, "orange"),
                    (50 * 3600, "red"),
                ),
            ),
            Panel(
                "Firing alerts",
                (
                    Query(
                        'sum by (severity) (ALERTS{alertstate="firing",severity=~"warning|critical"})',
                        "{{severity}}",
                    ),
                ),
                kind="stat",
                width=4,
                thresholds=((None, "green"), (1, "red")),
            ),
            Panel(
                "Request rate by protocol",
                (Query("forge:api_requests:rate5m", "{{api}}"),),
                unit="reqps",
                width=12,
            ),
            Panel(
                "GraphQL server-fault rate",
                (
                    Query(
                        "forge:graphql_server_faults:rate5m",
                        "GraphQL",
                    ),
                ),
                unit="reqps",
                width=12,
                description=(
                    "Actionable backend faults only; expected permission and "
                    "validation outcomes are not counted."
                ),
            ),
            Panel(
                "API latency p50 / p95",
                (
                    Query(
                        "histogram_quantile(0.50, sum by (api, le) "
                        "(rate(forge_api_request_duration_seconds_bucket[5m])))",
                        "{{api}} p50",
                    ),
                    Query(
                        "forge:api_request_duration_seconds:p95_5m",
                        "{{api}} p95",
                    ),
                ),
                unit="s",
                width=12,
                thresholds=((None, "green"), (1, "orange"), (3, "red")),
            ),
            Panel(
                "Dependency quick scan",
                (
                    Query(
                        'min by (job) (up{job=~"forge-web|nginx|pgbouncer|postgres|celery|redis|meilisearch|prometheus|alertmanager|loki|alloy"})',
                        "{{job}}",
                    ),
                ),
                kind="stat",
                width=12,
                thresholds=((None, "red"), (1, "green")),
            ),
            Panel(
                "Host pressure",
                (
                    Query(
                        '1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))',
                        "CPU used",
                        thresholds=((None, "green"), (0.90, "orange")),
                    ),
                    Query(
                        "1 - node_memory_MemAvailable_bytes / "
                        "node_memory_MemTotal_bytes",
                        "Memory used",
                        thresholds=(
                            (None, "green"),
                            (0.90, "orange"),
                            (0.95, "red"),
                        ),
                    ),
                    Query(
                        '1 - min(node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / '
                        'node_filesystem_size_bytes{fstype!~"tmpfs|overlay"})',
                        "Filesystem used",
                        thresholds=(
                            (None, "green"),
                            (0.85, "orange"),
                            (0.95, "red"),
                        ),
                    ),
                ),
                kind="gauge",
                unit="percentunit",
                width=12,
            ),
            Panel(
                "Container pressure",
                (
                    Query(
                        "topk(8, sum by (compose_service) "
                        "(rate(container_cpu_usage_seconds_total[5m])))",
                        "{{compose_service}} CPU",
                        unit="percentunit",
                    ),
                    Query(
                        "topk(8, sum by (compose_service) "
                        "(container_memory_working_set_bytes))",
                        "{{compose_service}} memory",
                        unit="bytes",
                    ),
                    Query(
                        "sum by (compose_service) "
                        "(increase(container_oom_events_total[1h]))",
                        "{{compose_service}} OOM",
                        unit="short",
                        thresholds=((None, "green"), (1, "red")),
                    ),
                ),
                width=12,
                data_links=(SERVICE_LOG_LINK,),
            ),
            Panel(
                "Error logs by Compose service",
                (
                    Query(
                        'sum by (compose_service) (count_over_time({compose_service=~".+"} '
                        '|~ "(?i)error|critical" [$__auto]))',
                        "{{compose_service}}",
                        datasource="loki",
                    ),
                ),
                width=24,
                data_links=(SERVICE_LOG_LINK,),
            ),
        ),
        links=tuple(
            (title, f"/d/{uid}?${{__url_time_range}}")
            for title, uid in (
                ("API", "forge-api"),
                ("Async & Redis", "forge-async-redis"),
                ("Postgres & PgBouncer", "forge-postgres-pgbouncer"),
                ("Search", "forge-search"),
                ("Host & Containers", "forge-host-containers"),
                ("Continuity", "forge-continuity"),
                ("Logs & Changes", "forge-logs-changes"),
            )
        ),
        annotations=(
            {
                "name": "Deploy revision",
                "expr": (
                    "(changes(max(forge_deployment_timestamp_seconds)[1m:]) "
                    "> 0) * on() group_left(revision) "
                    "topk(1, forge_deployment_timestamp_seconds)"
                ),
                "tagKeys": "revision",
            },
            {
                "name": "Maintenance",
                "expr": (
                    "(changes(forge_maintenance_mode[1m]) != 0) "
                    "* on(instance, job) group_left(reason, revision) "
                    "forge_maintenance_info"
                ),
                "tagKeys": "reason revision",
            },
        ),
    ),
)


def _prom_variable(
    name: str, metric: str, label: str, job: str | None = None
) -> dict[str, Any]:
    selector = f'job="{job}"' if job is not None else f'{label}=~".+"'
    query = f"label_values({metric}{{{selector}}}, {label})"
    return {
        "allValue": ".*",
        "current": {"text": "All", "value": ".*"},
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "definition": query,
        "includeAll": True,
        "label": name.replace("_", " ").title(),
        "multi": True,
        "name": name,
        "options": [],
        "query": query,
        "refresh": 1,
        "regex": "",
        "type": "query",
    }


def _detail_links(parent_title: str, parent_uid: str) -> tuple[tuple[str, str], ...]:
    return (
        OVERVIEW_LINK,
        (parent_title, f"/d/{parent_uid}?${{__url_time_range}}"),
        LOGS_LINK,
    )


def _exporter_health(
    job: str,
    build_metric: str | None,
    *,
    instance_variable: bool = False,
    process_health: bool = True,
) -> tuple[Panel, ...]:
    selector = f'job="{job}"'
    if instance_variable:
        selector += ',instance=~"$instance"'
    panels: tuple[Panel, ...] = (
        Panel(
            "Target health",
            (Query(f"up{{{selector}}}", "{{instance}}"),),
            kind="stat",
            width=6,
            thresholds=((None, "red"), (1, "green")),
        ),
        Panel(
            "Scrape duration and samples",
            (
                Query(f"scrape_duration_seconds{{{selector}}}", "Duration", unit="s"),
                Query(f"scrape_samples_scraped{{{selector}}}", "Samples", unit="short"),
            ),
            width=6,
            unit="s",
        ),
    )
    if process_health:
        panels += (
            Panel(
                "Process CPU and resident memory",
                (
                    Query(
                        f"rate(process_cpu_seconds_total{{{selector}}}[5m])",
                        "CPU",
                        unit="percentunit",
                    ),
                    Query(
                        f"process_resident_memory_bytes{{{selector}}}",
                        "Resident memory",
                        unit="bytes",
                    ),
                ),
                width=6,
            ),
        )
    if build_metric is None:
        return panels
    return panels + (
        Panel(
            "Build information",
            (Query(f"{build_metric}{{{selector}}}", "{{version}}"),),
            kind="table",
            width=6,
        ),
    )


DASHBOARDS += (
    Dashboard(
        folder="Exporters",
        uid="forge-node-exporter",
        title="Node Exporter Detail",
        panels=_exporter_health("node", "node_exporter_build_info")
        + (
            Panel(
                "CPU modes and load",
                (
                    Query(
                        "sum by (mode) (rate(node_cpu_seconds_total[5m]))", "{{mode}}"
                    ),
                    Query("node_load1", "Load 1m", unit="short"),
                    Query("node_load5", "Load 5m", unit="short"),
                    Query("node_load15", "Load 15m", unit="short"),
                ),
            ),
            Panel(
                "Memory classes and swap",
                (
                    Query("node_memory_MemAvailable_bytes", "Available"),
                    Query("node_memory_Cached_bytes", "Cached"),
                    Query("node_memory_Buffers_bytes", "Buffers"),
                    Query(
                        "node_memory_SwapTotal_bytes - node_memory_SwapFree_bytes",
                        "Swap used",
                    ),
                ),
                unit="bytes",
            ),
            Panel(
                "Filesystem bytes and inode free ratios",
                (
                    Query(
                        'node_filesystem_avail_bytes{mountpoint=~"$mountpoint",fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{mountpoint=~"$mountpoint",fstype!~"tmpfs|overlay"}',
                        "{{mountpoint}} bytes",
                    ),
                    Query(
                        'node_filesystem_files_free{mountpoint=~"$mountpoint",fstype!~"tmpfs|overlay"} / node_filesystem_files{mountpoint=~"$mountpoint",fstype!~"tmpfs|overlay"}',
                        "{{mountpoint}} inodes",
                    ),
                ),
                unit="percentunit",
            ),
            Panel(
                "Disk throughput, IOPS and I/O time",
                (
                    Query(
                        'rate(node_disk_read_bytes_total{device=~"$device"}[5m])',
                        "{{device}} read",
                        unit="Bps",
                    ),
                    Query(
                        'rate(node_disk_written_bytes_total{device=~"$device"}[5m])',
                        "{{device}} write",
                        unit="Bps",
                    ),
                    Query(
                        'rate(node_disk_reads_completed_total{device=~"$device"}[5m]) + rate(node_disk_writes_completed_total{device=~"$device"}[5m])',
                        "{{device}} IOPS",
                        unit="iops",
                    ),
                    Query(
                        'rate(node_disk_io_time_seconds_total{device=~"$device"}[5m])',
                        "{{device}} busy",
                        unit="percentunit",
                    ),
                ),
            ),
            Panel(
                "Network throughput, errors and drops",
                (
                    Query(
                        "sum by (device) (rate(node_network_receive_bytes_total[5m]))",
                        "{{device}} receive",
                        unit="Bps",
                    ),
                    Query(
                        "sum by (device) (rate(node_network_transmit_bytes_total[5m]))",
                        "{{device}} transmit",
                        unit="Bps",
                    ),
                    Query(
                        "sum by (device) (rate(node_network_receive_errs_total[5m]) + rate(node_network_transmit_errs_total[5m]))",
                        "{{device}} errors",
                    ),
                    Query(
                        "sum by (device) (rate(node_network_receive_drop_total[5m]) + rate(node_network_transmit_drop_total[5m]))",
                        "{{device}} drops",
                    ),
                ),
            ),
            Panel(
                "Boot age",
                (Query("time() - node_boot_time_seconds", "Age"),),
                kind="stat",
                unit="s",
            ),
            Panel(
                "Textfile collector errors",
                (Query("node_textfile_scrape_error", "Errors"),),
                kind="stat",
                thresholds=((None, "green"), (1, "red")),
            ),
        ),
        links=_detail_links("Host and Containers", "forge-host-containers"),
        variables=(
            _prom_variable("device", "node_disk_read_bytes_total", "device", "node"),
            _prom_variable(
                "mountpoint", "node_filesystem_size_bytes", "mountpoint", "node"
            ),
        ),
    ),
    Dashboard(
        folder="Exporters",
        uid="forge-cadvisor",
        title="cAdvisor Detail",
        panels=_exporter_health("alloy", "alloy_build_info")
        + (
            Panel(
                "CPU by service",
                (
                    Query(
                        'sum by (compose_service) (rate(container_cpu_usage_seconds_total{compose_service=~"$compose_service"}[5m]))',
                        "{{compose_service}}",
                    ),
                ),
                data_links=(SERVICE_LOG_LINK,),
            ),
            Panel(
                "CPU throttling",
                (
                    Query(
                        'sum by (compose_service) (rate(container_cpu_cfs_throttled_periods_total{compose_service=~"$compose_service"}[5m]))',
                        "{{compose_service}} periods",
                    ),
                    Query(
                        'sum by (compose_service) (rate(container_cpu_cfs_throttled_seconds_total{compose_service=~"$compose_service"}[5m]))',
                        "{{compose_service}} seconds / s",
                        unit="percentunit",
                    ),
                ),
                data_links=(SERVICE_LOG_LINK,),
            ),
            Panel(
                "Working set, RSS and cache",
                (
                    Query(
                        'sum by (compose_service) (container_memory_working_set_bytes{compose_service=~"$compose_service"})',
                        "{{compose_service}} working set",
                    ),
                    Query(
                        'sum by (compose_service) (container_memory_rss{compose_service=~"$compose_service"})',
                        "{{compose_service}} RSS",
                    ),
                    Query(
                        'sum by (compose_service) (container_memory_cache{compose_service=~"$compose_service"})',
                        "{{compose_service}} cache",
                    ),
                ),
                unit="bytes",
                data_links=(SERVICE_LOG_LINK,),
            ),
            Panel(
                "OOM events and starts",
                (
                    Query(
                        'sum by (compose_service) (increase(container_oom_events_total{compose_service=~"$compose_service"}[1h]))',
                        "{{compose_service}} OOM",
                    ),
                    Query(
                        'changes((max by (compose_service) (container_start_time_seconds{compose_service=~"$compose_service"}))[1h:])',
                        "{{compose_service}} starts",
                    ),
                ),
                data_links=(SERVICE_LOG_LINK,),
            ),
            Panel(
                "Network traffic and errors",
                (
                    Query(
                        'sum by (compose_service) (rate(container_network_receive_bytes_total{compose_service=~"$compose_service"}[5m]))',
                        "{{compose_service}} receive",
                        unit="Bps",
                    ),
                    Query(
                        'sum by (compose_service) (rate(container_network_transmit_bytes_total{compose_service=~"$compose_service"}[5m]))',
                        "{{compose_service}} transmit",
                        unit="Bps",
                    ),
                    Query(
                        'sum by (compose_service) (rate(container_network_receive_errors_total{compose_service=~"$compose_service"}[5m]) + rate(container_network_transmit_errors_total{compose_service=~"$compose_service"}[5m]))',
                        "{{compose_service}} errors",
                    ),
                ),
                data_links=(SERVICE_LOG_LINK,),
            ),
            Panel(
                "Filesystem usage and limits",
                (
                    Query(
                        'sum by (compose_service) (container_fs_usage_bytes{compose_service=~"$compose_service"})',
                        "{{compose_service}} used",
                    ),
                    Query(
                        'sum by (compose_service) (container_fs_limit_bytes{compose_service=~"$compose_service"})',
                        "{{compose_service}} limit",
                    ),
                ),
                unit="bytes",
                data_links=(SERVICE_LOG_LINK,),
            ),
            Panel(
                "Processes and threads",
                (
                    Query(
                        'sum by (compose_service) (container_processes{compose_service=~"$compose_service"})',
                        "{{compose_service}} processes",
                    ),
                    Query(
                        'sum by (compose_service) (container_threads{compose_service=~"$compose_service"})',
                        "{{compose_service}} threads",
                    ),
                ),
                data_links=(SERVICE_LOG_LINK,),
            ),
            Panel(
                "CPU quota and memory specification",
                (
                    Query(
                        'max by (compose_service) (container_spec_cpu_quota{compose_service=~"$compose_service"})',
                        "{{compose_service}} CPU quota",
                    ),
                    Query(
                        'max by (compose_service) (container_spec_memory_limit_bytes{compose_service=~"$compose_service"})',
                        "{{compose_service}} memory",
                        unit="bytes",
                    ),
                ),
                data_links=(SERVICE_LOG_LINK,),
            ),
        ),
        links=_detail_links("Host and Containers", "forge-host-containers"),
        variables=(
            _prom_variable(
                "compose_service",
                "container_cpu_usage_seconds_total",
                "compose_service",
            ),
        ),
    ),
    Dashboard(
        folder="Exporters",
        uid="forge-postgres-exporter",
        title="PostgreSQL Exporter Detail",
        panels=_exporter_health("postgres", "postgres_exporter_build_info")
        + (
            Panel(
                "Exporter errors and connections",
                (
                    Query("pg_exporter_last_scrape_error", "Scrape error"),
                    Query(
                        'sum(pg_stat_activity_count{datname=~"$datname"})',
                        "Connections",
                    ),
                    Query("pg_settings_max_connections", "Limit"),
                ),
            ),
            Panel(
                "Sessions and longest transaction",
                (
                    Query(
                        'sum by (state) (pg_stat_activity_count{datname=~"$datname"})',
                        "{{state}}",
                    ),
                    Query(
                        "max(pg_long_running_transactions_oldest_timestamp_seconds) and on() (sum(pg_long_running_transactions) > 0)",
                        "Oldest transaction",
                        unit="s",
                    ),
                ),
            ),
            Panel(
                "Locks, commits, rollbacks and deadlocks",
                (
                    Query(
                        'sum by (mode) (pg_locks_count{datname=~"$datname"})',
                        "{{mode}} locks",
                    ),
                    Query(
                        'sum(rate(pg_stat_database_xact_commit{datname=~"$datname"}[5m]))',
                        "Commits",
                    ),
                    Query(
                        'sum(rate(pg_stat_database_xact_rollback{datname=~"$datname"}[5m]))',
                        "Rollbacks",
                    ),
                    Query(
                        'sum(rate(pg_stat_database_deadlocks{datname=~"$datname"}[5m]))',
                        "Deadlocks",
                    ),
                ),
            ),
            Panel(
                "Cache block hits and reads",
                (
                    Query(
                        'sum(rate(pg_stat_database_blks_hit{datname=~"$datname"}[5m]))',
                        "Hits",
                    ),
                    Query(
                        'sum(rate(pg_stat_database_blks_read{datname=~"$datname"}[5m]))',
                        "Reads",
                    ),
                ),
            ),
            Panel(
                "Temporary files and bytes",
                (
                    Query(
                        'sum(rate(pg_stat_database_temp_files{datname=~"$datname"}[5m]))',
                        "Files",
                    ),
                    Query(
                        'sum(rate(pg_stat_database_temp_bytes{datname=~"$datname"}[5m]))',
                        "Bytes",
                        unit="Bps",
                    ),
                ),
            ),
            Panel(
                "Tuple activity",
                (
                    Query(
                        'sum(rate(pg_stat_database_tup_fetched{datname=~"$datname"}[5m]))',
                        "Fetched",
                    ),
                    Query(
                        'sum(rate(pg_stat_database_tup_returned{datname=~"$datname"}[5m]))',
                        "Returned",
                    ),
                    Query(
                        'sum(rate(pg_stat_database_tup_inserted{datname=~"$datname"}[5m]))',
                        "Inserted",
                    ),
                    Query(
                        'sum(rate(pg_stat_database_tup_updated{datname=~"$datname"}[5m]))',
                        "Updated",
                    ),
                    Query(
                        'sum(rate(pg_stat_database_tup_deleted{datname=~"$datname"}[5m]))',
                        "Deleted",
                    ),
                ),
            ),
            Panel(
                "Database size and 24h growth",
                (
                    Query(
                        'pg_database_size_bytes{datname=~"$datname"}',
                        "{{datname}} size",
                        unit="bytes",
                    ),
                    Query(
                        'pg_database_size_bytes{datname=~"$datname"} - pg_database_size_bytes{datname=~"$datname"} offset 24h',
                        "{{datname}} growth",
                        unit="bytes",
                    ),
                ),
            ),
            Panel(
                "WAL and background writes",
                (
                    Query(
                        "pg_wal_size_bytes",
                        "WAL size",
                        unit="bytes",
                    ),
                    Query(
                        "rate(pg_stat_bgwriter_buffers_alloc_total[5m])",
                        "Buffers allocated",
                    ),
                    Query(
                        'sum(rate(pg_stat_database_conflicts{datname=~"$datname"}[5m]))',
                        "Database conflicts",
                    ),
                ),
            ),
            Panel(
                "Table scans and dead tuples",
                (
                    Query(
                        'topk(10, rate(pg_stat_user_tables_seq_scan{datname=~"$datname"}[5m]))',
                        "{{relname}} sequential",
                    ),
                    Query(
                        'topk(10, rate(pg_stat_user_tables_idx_scan{datname=~"$datname"}[5m]))',
                        "{{relname}} index",
                    ),
                    Query(
                        'topk(10, pg_stat_user_tables_n_dead_tup{datname=~"$datname"})',
                        "{{relname}} dead tuples",
                    ),
                ),
            ),
        ),
        links=_detail_links("PostgreSQL and PgBouncer", "forge-postgres-pgbouncer"),
        variables=(
            _prom_variable("datname", "pg_database_size_bytes", "datname", "postgres"),
        ),
    ),
    Dashboard(
        folder="Exporters",
        uid="forge-pgbouncer-exporter",
        title="PgBouncer Exporter Detail",
        panels=_exporter_health("pgbouncer", "pgbouncer_exporter_build_info")
        + (
            Panel(
                "Client capacity",
                (
                    Query("pgbouncer_config_max_client_connections", "Max clients"),
                    Query(
                        'sum by (database) (pgbouncer_pools_client_active_connections{database=~"$database"})',
                        "{{database}} active",
                    ),
                    Query(
                        'sum by (database) (pgbouncer_pools_client_waiting_connections{database=~"$database"})',
                        "{{database}} waiting",
                    ),
                    Query(
                        'sum by (database) (pgbouncer_pools_client_cancel_req_connections{database=~"$database"})',
                        "{{database}} cancel",
                    ),
                ),
            ),
            Panel(
                "Server pool states",
                (
                    Query(
                        'sum by (database) (pgbouncer_pools_server_active_connections{database=~"$database"})',
                        "{{database}} active",
                    ),
                    Query(
                        'sum by (database) (pgbouncer_pools_server_idle_connections{database=~"$database"})',
                        "{{database}} idle",
                    ),
                    Query(
                        'sum by (database) (pgbouncer_pools_server_used_connections{database=~"$database"})',
                        "{{database}} used",
                    ),
                    Query(
                        'sum by (database) (pgbouncer_pools_server_tested_connections{database=~"$database"})',
                        "{{database}} tested",
                    ),
                    Query(
                        'sum by (database) (pgbouncer_pools_server_login_connections{database=~"$database"})',
                        "{{database}} login",
                    ),
                ),
            ),
            Panel(
                "Pool utilization",
                (
                    Query(
                        '(sum(pgbouncer_pools_client_active_connections{database=~"$database"}) / max(pgbouncer_config_max_client_connections)) and on() (max(pgbouncer_config_max_client_connections) > 0)',
                        "Utilization",
                    ),
                ),
                unit="percentunit",
            ),
            Panel(
                "Client wait",
                (
                    Query(
                        'max(pgbouncer_pools_client_maxwait_seconds{database=~"$database"})',
                        "Oldest wait",
                        unit="s",
                    ),
                    Query(
                        '(rate(pgbouncer_stats_client_wait_seconds_total{database=~"$database"}[5m]) / rate(pgbouncer_stats_queries_total{database=~"$database"}[5m])) and (rate(pgbouncer_stats_queries_total{database=~"$database"}[5m]) > 0)',
                        "Average wait",
                        unit="s",
                    ),
                ),
            ),
            Panel(
                "Transactions and queries",
                (
                    Query(
                        'sum by (database) (rate(pgbouncer_stats_transactions_total{database=~"$database"}[5m]))',
                        "{{database}} transactions",
                    ),
                    Query(
                        'sum by (database) (rate(pgbouncer_stats_queries_total{database=~"$database"}[5m]))',
                        "{{database}} queries",
                    ),
                ),
            ),
            Panel(
                "Network bytes",
                (
                    Query(
                        'sum by (database) (rate(pgbouncer_stats_received_bytes_total{database=~"$database"}[5m]))',
                        "{{database}} received",
                        unit="Bps",
                    ),
                    Query(
                        'sum by (database) (rate(pgbouncer_stats_sent_bytes_total{database=~"$database"}[5m]))',
                        "{{database}} sent",
                        unit="Bps",
                    ),
                ),
            ),
            Panel(
                "Transaction and query duration",
                (
                    Query(
                        '(rate(pgbouncer_stats_transaction_duration_seconds_total{database=~"$database"}[5m]) / rate(pgbouncer_stats_transactions_total{database=~"$database"}[5m])) and (rate(pgbouncer_stats_transactions_total{database=~"$database"}[5m]) > 0)',
                        "Transaction duration",
                        unit="s",
                    ),
                    Query(
                        '(rate(pgbouncer_stats_query_duration_seconds_total{database=~"$database"}[5m]) / rate(pgbouncer_stats_queries_total{database=~"$database"}[5m])) and (rate(pgbouncer_stats_queries_total{database=~"$database"}[5m]) > 0)',
                        "Query duration",
                        unit="s",
                    ),
                ),
            ),
        ),
        links=_detail_links("PostgreSQL and PgBouncer", "forge-postgres-pgbouncer"),
        variables=(
            _prom_variable(
                "database",
                "pgbouncer_pools_client_active_connections",
                "database",
                "pgbouncer",
            ),
        ),
    ),
)

DASHBOARDS += (
    Dashboard(
        folder="Curated",
        uid="forge-api",
        title="Forge API and User Experience",
        panels=(
            Panel(
                "Public HTTPS and GraphQL probes",
                (
                    Query('probe_success{job="blackbox"}', "{{probe}} success"),
                    Query(
                        'probe_duration_seconds{job="blackbox"}',
                        "{{probe}} duration",
                        unit="s",
                    ),
                ),
            ),
            Panel(
                "GraphQL query and mutation rate",
                (
                    Query(
                        "sum by (operation_type) (rate(graphql_requests_total[5m]))",
                        "{{operation_type}}",
                    ),
                ),
                unit="reqps",
            ),
            Panel(
                "GraphQL server faults",
                (
                    Query(
                        'sum by (code) (rate(graphql_errors_total{code=~"INTERNAL_SERVER_ERROR|unknown"}[5m]))',
                        "{{code}}",
                    ),
                ),
                unit="reqps",
            ),
            Panel(
                "GraphQL expected domain outcomes",
                (
                    Query(
                        'sum by (code) (rate(graphql_errors_total{code=~"PERMISSION_DENIED|BAD_USER_INPUT|NOT_FOUND"}[5m]))',
                        "{{code}}",
                    ),
                ),
                unit="reqps",
                description=(
                    "Expected authorization outcomes; visible for client and policy "
                    "regressions, excluded from service-error alerts."
                ),
            ),
            Panel(
                "GraphQL latency p50 / p95",
                (
                    Query(
                        "histogram_quantile(0.50, sum by (operation_type, le) (rate(graphql_request_duration_seconds_bucket[5m])))",
                        "{{operation_type}} p50",
                    ),
                    Query(
                        "forge:graphql_request_duration_seconds:p95_5m",
                        "{{operation_type}} p95",
                    ),
                ),
                unit="s",
            ),
            Panel(
                "Top slow GraphQL operations",
                (
                    Query(
                        "topk(10, histogram_quantile(0.95, sum by (operation_name, le) (rate(graphql_request_duration_seconds_bucket[5m]))))",
                        "{{operation_name}}",
                    ),
                ),
                kind="table",
                unit="s",
            ),
            Panel(
                "Top failing GraphQL operations",
                (
                    Query(
                        'topk(10, round(sum by (operation_name, code) (increase(graphql_errors_total{code=~"INTERNAL_SERVER_ERROR|unknown"}[$__range]))))',
                        "{{operation_name}} {{code}}",
                    ),
                ),
                kind="table",
            ),
            Panel(
                "Unknown GraphQL operation share / requests",
                (
                    Query(
                        'sum(rate(graphql_requests_total{operation_name="unknown"}[5m])) / sum(rate(graphql_requests_total[5m]))',
                        "Unknown share",
                    ),
                    Query(
                        "round(sum(increase(graphql_requests_total[$__range])))",
                        "Requests",
                        unit="short",
                    ),
                ),
                unit="percentunit",
            ),
            Panel(
                "Request methods and status codes",
                (
                    Query(
                        "sum by (api, method, status) (rate(forge_api_requests_total[5m]))",
                        "{{api}} {{method}} {{status}}",
                    ),
                ),
                unit="reqps",
            ),
        ),
        links=(
            OVERVIEW_LINK,
            ("Nginx detail", "/d/forge-nginx-exporter?${__url_time_range}"),
            LOGS_LINK,
        ),
    ),
    Dashboard(
        folder="Curated",
        uid="forge-async-redis",
        title="Forge Async and Redis",
        panels=(
            Panel(
                "Workers online",
                (
                    Query("sum(celery_worker_up)", "Worker up"),
                    Query("sum(celery_active_worker_count)", "Active workers"),
                ),
                kind="stat",
            ),
            Panel(
                "Active tasks",
                (Query("sum(celery_worker_tasks_active)", "Active tasks"),),
                kind="stat",
            ),
            Panel(
                "Queue depth",
                (Query("forge_celery_queue_depth", "{{queue}}"),),
                kind="stat",
            ),
            Panel(
                "Oldest task age",
                (Query("forge_celery_oldest_task_age_seconds", "{{queue}}"),),
                kind="stat",
                unit="s",
            ),
            Panel(
                "Task outcomes",
                (
                    Query(
                        "sum by (name) (rate(celery_task_received_total[5m]))",
                        "{{name}} received",
                    ),
                    Query(
                        "sum by (name) (rate(celery_task_succeeded_total[5m]))",
                        "{{name}} succeeded",
                    ),
                    Query(
                        "sum by (name) (rate(celery_task_failed_total[5m]))",
                        "{{name}} failed",
                    ),
                    Query(
                        "sum by (name) (rate(celery_task_retried_total[5m]))",
                        "{{name}} retried",
                    ),
                ),
                unit="ops",
            ),
            Panel(
                "Task p95 duration",
                (
                    Query(
                        "histogram_quantile(0.95, sum by (name, le) (rate(celery_task_runtime_bucket[5m])))",
                        "{{name}}",
                    ),
                ),
                unit="s",
            ),
            Panel(
                "Redis memory ratio",
                (
                    Query(
                        "(redis_memory_used_bytes / redis_memory_max_bytes) "
                        "and on(instance, job) (redis_memory_max_bytes > 0)",
                        "Used ratio",
                    ),
                    Query("redis_memory_used_bytes", "Used bytes", unit="bytes"),
                ),
                unit="percentunit",
            ),
            Panel(
                "Redis evictions and rejected connections",
                (
                    Query("rate(redis_evicted_keys_total[5m])", "Evictions"),
                    Query(
                        "rate(redis_rejected_connections_total[5m])",
                        "Rejected connections",
                    ),
                ),
                unit="ops",
            ),
            Panel(
                "Redis blocked clients",
                (Query("redis_blocked_clients", "Blocked clients"),),
                kind="stat",
            ),
            Panel(
                "Redis command rate",
                (
                    Query(
                        "sum by (cmd) (rate(redis_commands_processed_total[5m]))",
                        "{{cmd}}",
                    ),
                ),
                unit="ops",
            ),
            Panel(
                "Redis persistence",
                (
                    Query("redis_rdb_last_bgsave_status", "RDB save"),
                    Query(
                        "redis_rdb_last_save_timestamp_seconds",
                        "RDB last save",
                        unit="dateTimeAsIso",
                    ),
                    Query("redis_aof_last_bgrewrite_status", "AOF rewrite"),
                ),
                kind="stat",
            ),
        ),
        links=(
            OVERVIEW_LINK,
            LOGS_LINK,
            ("Celery exporter", "/d/forge-celery-exporter?${__url_time_range}"),
            ("Redis exporter", "/d/forge-redis-exporter?${__url_time_range}"),
        ),
    ),
)

DASHBOARDS += (
    Dashboard(
        folder="Curated",
        uid="forge-continuity",
        title="Forge Continuity and Telemetry",
        panels=(
            Panel(
                "Backup age / result",
                (
                    Query(
                        "time() - backup_last_success_timestamp_seconds", "Backup age"
                    ),
                    Query(
                        "backup_last_attempt_success", "Latest attempt", unit="short"
                    ),
                ),
                unit="s",
            ),
            Panel(
                "Backup duration / size",
                (
                    Query("backup_last_duration_seconds", "Duration"),
                    Query("backup_size_bytes", "Size", unit="bytes"),
                ),
                unit="s",
            ),
            Panel(
                "Backup transfer",
                (
                    Query(
                        "backup_transfer_last_success_timestamp_seconds", "Last success"
                    ),
                    Query(
                        "backup_transfer_last_failure_timestamp_seconds", "Last failure"
                    ),
                ),
                unit="dateTimeAsIso",
            ),
            Panel(
                "Restore verification age / result",
                (
                    Query(
                        "time() - restore_verification_last_success_timestamp_seconds",
                        "Verification age",
                    ),
                    Query(
                        "restore_verification_last_attempt_success",
                        "Latest attempt",
                        unit="short",
                    ),
                    Query(
                        "restore_verification_last_duration_seconds",
                        "Duration",
                        unit="s",
                    ),
                ),
                unit="s",
            ),
            Panel(
                "Scrape health",
                (
                    Query("min by (job) (up)", "{{job}} up"),
                    Query(
                        "max by (job) (scrape_duration_seconds)",
                        "{{job}} duration",
                        unit="s",
                    ),
                    Query(
                        "sum by (job) (scrape_samples_scraped)",
                        "{{job}} samples",
                        unit="short",
                    ),
                ),
            ),
            Panel(
                "Rule evaluation",
                (
                    Query(
                        "rate(prometheus_rule_evaluation_failures_total[5m])",
                        "Failures",
                    ),
                    Query(
                        "prometheus_rule_group_last_duration_seconds",
                        "{{rule_group}} duration",
                        unit="s",
                    ),
                ),
                unit="ops",
            ),
            Panel(
                "Prometheus storage",
                (
                    Query("prometheus_tsdb_head_series", "Head series"),
                    Query(
                        "rate(prometheus_tsdb_head_samples_appended_total[5m])",
                        "Samples appended",
                        unit="ops",
                    ),
                    Query(
                        "prometheus_tsdb_storage_blocks_bytes", "Blocks", unit="bytes"
                    ),
                ),
            ),
            Panel(
                "Loki ingestion",
                (
                    Query(
                        "sum(rate(loki_distributor_lines_received_total[5m]))", "Lines"
                    ),
                    Query("sum(rate(loki_discarded_samples_total[5m]))", "Discarded"),
                ),
                unit="ops",
            ),
            Panel(
                "Alloy collection",
                (
                    Query('up{job="alloy"}', "Up"),
                    Query(
                        'rate(process_cpu_seconds_total{job="alloy"}[5m])',
                        "CPU",
                        unit="percentunit",
                    ),
                    Query(
                        'process_resident_memory_bytes{job="alloy"}',
                        "Memory",
                        unit="bytes",
                    ),
                ),
            ),
            Panel(
                "Alertmanager delivery",
                (
                    Query(
                        "sum by (integration) (rate(alertmanager_notifications_total[5m]))",
                        "{{integration}} sent",
                    ),
                    Query(
                        "sum by (integration, reason) (rate(alertmanager_notifications_failed_total[5m]))",
                        "{{integration}} {{reason}} failed",
                    ),
                ),
                unit="ops",
            ),
            Panel(
                "Alert state",
                (
                    Query(
                        "sum by (severity, alertstate) (ALERTS)",
                        "{{severity}} {{alertstate}}",
                    ),
                ),
            ),
        ),
        links=(
            OVERVIEW_LINK,
            LOGS_LINK,
            (
                "Prometheus detail",
                "/d/forge-prometheus-detail?${__url_time_range}",
            ),
            (
                "Alertmanager detail",
                "/d/forge-alertmanager-detail?${__url_time_range}",
            ),
            ("Loki detail", "/d/forge-loki-detail?${__url_time_range}"),
            ("Alloy detail", "/d/forge-alloy-detail?${__url_time_range}"),
        ),
    ),
    Dashboard(
        folder="Curated",
        uid="forge-logs-changes",
        title="Forge Logs and Changes",
        panels=(
            Panel(
                "Warning and error count by service",
                (
                    Query(
                        'sum by (compose_service, level) (count_over_time({compose_project=~"$compose_project",compose_service=~"$compose_service",level=~"(?i)warn|warning|error|critical"}[$__auto]))',
                        "{{compose_service}} {{level}}",
                        datasource="loki",
                    ),
                ),
                data_links=(SERVICE_LOG_LINK,),
            ),
            Panel(
                "Recent warnings and errors",
                (
                    Query(
                        '{compose_project=~"$compose_project",compose_service=~"$compose_service"} | level=~"(?i)warn|warning|error|critical"',
                        datasource="loki",
                    ),
                ),
                kind="logs",
            ),
            Panel(
                "Logger frequency",
                (
                    Query(
                        'topk(20, sum by (logger) (count_over_time({compose_project=~"$compose_project",compose_service=~"$compose_service"} | json logger="name" | logger=~"[A-Za-z0-9_.-]{1,80}" [$__auto])))',
                        "{{logger}}",
                        datasource="loki",
                    ),
                ),
                kind="table",
            ),
            Panel(
                "Container lifecycle",
                (
                    Query(
                        '{compose_project=~"$compose_project",compose_service=~"$compose_service"} |~ "(?i)start|restart|oom|killed"',
                        datasource="loki",
                    ),
                ),
                kind="logs",
            ),
            Panel(
                "Maintenance state",
                (
                    Query("forge_maintenance_mode", "Mode"),
                    Query(
                        "forge_maintenance_suppress_until_timestamp_seconds - time()",
                        "Suppression remaining",
                        unit="s",
                    ),
                ),
            ),
            Panel(
                "Deployment revisions",
                (Query("forge_deployment_timestamp_seconds", "{{revision}}"),),
                unit="dateTimeAsIso",
            ),
        ),
        links=(
            OVERVIEW_LINK,
            ("Alloy detail", "/d/forge-alloy-detail?${__url_time_range}"),
        ),
        variables=(
            {
                "allValue": ".+",
                "current": {"text": "All", "value": ".+"},
                "datasource": {"type": "loki", "uid": "loki"},
                "definition": "label_values(compose_project)",
                "includeAll": True,
                "label": "Compose project",
                "multi": True,
                "name": "compose_project",
                "options": [],
                "query": "label_values(compose_project)",
                "refresh": 2,
                "type": "query",
            },
            {
                "allValue": ".+",
                "current": {"text": "All", "value": ".+"},
                "datasource": {"type": "loki", "uid": "loki"},
                "definition": 'label_values({compose_project=~"$compose_project"}, compose_service)',
                "includeAll": True,
                "label": "Compose service",
                "multi": True,
                "name": "compose_service",
                "options": [],
                "query": 'label_values({compose_project=~"$compose_project"}, compose_service)',
                "refresh": 2,
                "type": "query",
            },
        ),
    ),
)

DASHBOARDS += (
    Dashboard(
        folder="Curated",
        uid="forge-postgres-pgbouncer",
        title="Forge PostgreSQL and PgBouncer",
        panels=(
            Panel(
                "PgBouncer active / waiting clients",
                (
                    Query("sum(pgbouncer_pools_client_active_connections)", "Active"),
                    Query("sum(pgbouncer_pools_client_waiting_connections)", "Waiting"),
                ),
            ),
            Panel(
                "Pool utilization",
                (
                    Query(
                        "sum(pgbouncer_pools_client_active_connections) / max(pgbouncer_config_max_client_connections)",
                        "Utilization",
                    ),
                    Query(
                        "sum(pgbouncer_pools_client_active_connections)",
                        "Active clients",
                        unit="short",
                    ),
                    Query(
                        "max(pgbouncer_config_max_client_connections)",
                        "Client limit",
                        unit="short",
                    ),
                ),
                unit="percentunit",
            ),
            Panel(
                "Pool wait time",
                (
                    Query(
                        "pgbouncer_pools_client_maxwait_seconds",
                        "{{database}} {{user}} max",
                    ),
                    Query(
                        "(rate(pgbouncer_stats_client_wait_seconds_total[5m]) / "
                        "rate(pgbouncer_stats_queries_total[5m])) and "
                        "(rate(pgbouncer_stats_queries_total[5m]) > 0)",
                        "{{database}} average",
                    ),
                ),
                unit="s",
            ),
            Panel(
                "PostgreSQL connections / limit",
                (
                    Query("sum(pg_stat_activity_count)", "Connections"),
                    Query("pg_settings_max_connections", "Limit"),
                ),
            ),
            Panel(
                "Session states",
                (Query("sum by (state) (pg_stat_activity_count)", "{{state}}"),),
            ),
            Panel(
                "Commits / rollbacks",
                (
                    Query("sum(rate(pg_stat_database_xact_commit[5m]))", "Commits"),
                    Query("sum(rate(pg_stat_database_xact_rollback[5m]))", "Rollbacks"),
                ),
                unit="ops",
            ),
            Panel(
                "Deadlocks",
                (Query("sum(rate(pg_stat_database_deadlocks[5m]))", "Deadlocks"),),
                unit="ops",
            ),
            Panel("Locks", (Query("sum by (mode) (pg_locks_count)", "{{mode}}"),)),
            Panel(
                "Longest transaction",
                (
                    Query(
                        "max(pg_long_running_transactions_oldest_timestamp_seconds) "
                        "and on() (sum(pg_long_running_transactions) > 0)",
                        "Longest transaction",
                    ),
                ),
                unit="s",
            ),
            Panel(
                "Cache hit ratio",
                (
                    Query(
                        "(sum(rate(pg_stat_database_blks_hit[5m])) / "
                        "(sum(rate(pg_stat_database_blks_hit[5m])) + "
                        "sum(rate(pg_stat_database_blks_read[5m])))) and on() "
                        "((sum(rate(pg_stat_database_blks_hit[5m])) + "
                        "sum(rate(pg_stat_database_blks_read[5m]))) > 0)",
                        "Cache hit ratio",
                    ),
                    Query(
                        "sum(rate(pg_stat_database_blks_read[5m]))",
                        "Block reads",
                        unit="ops",
                    ),
                ),
                unit="percentunit",
            ),
            Panel(
                "Temporary files",
                (
                    Query("sum(rate(pg_stat_database_temp_files[5m]))", "Files"),
                    Query(
                        "sum(rate(pg_stat_database_temp_bytes[5m]))",
                        "Bytes",
                        unit="Bps",
                    ),
                ),
                unit="ops",
            ),
            Panel(
                "Database size and 24h growth",
                (
                    Query("sum(pg_database_size_bytes)", "Size"),
                    Query(
                        "sum(pg_database_size_bytes) - sum(pg_database_size_bytes offset 24h)",
                        "24h growth",
                    ),
                ),
                unit="bytes",
            ),
        ),
        links=(
            OVERVIEW_LINK,
            LOGS_LINK,
            (
                "Postgres exporter",
                "/d/forge-postgres-exporter?${__url_time_range}",
            ),
            (
                "PgBouncer exporter",
                "/d/forge-pgbouncer-exporter?${__url_time_range}",
            ),
        ),
    ),
    Dashboard(
        folder="Curated",
        uid="forge-search",
        title="Forge Search",
        panels=(
            Panel(
                "Health and scrape",
                (
                    Query('up{job="meilisearch"}', "Up"),
                    Query(
                        'scrape_duration_seconds{job="meilisearch"}',
                        "Scrape duration",
                        unit="s",
                    ),
                ),
                kind="stat",
            ),
            Panel(
                "HTTP request rate",
                (
                    Query(
                        'sum by (method, path) (rate(meilisearch_http_requests_total{path!~"/health|/metrics"}[5m]))',
                        "{{method}} {{path}}",
                    ),
                ),
                unit="reqps",
            ),
            Panel(
                "HTTP p95 latency",
                (
                    Query(
                        'histogram_quantile(0.95, sum by (le) (rate(meilisearch_http_response_time_seconds_bucket{path!~"/health|/metrics"}[5m])))',
                        "p95",
                    ),
                ),
                unit="s",
            ),
            Panel("Indexing state", (Query("meilisearch_is_indexing", "Indexing"),)),
            Panel(
                "Task backlog and failures",
                (
                    Query(
                        "sum by (kind, value) (meilisearch_nb_tasks)",
                        "{{kind}} {{value}}",
                    ),
                ),
            ),
            Panel(
                "Documents and indexes",
                (Query("meilisearch_index_count", "Indexes"),),
                description=(
                    "The pinned Meilisearch version exposes the index count but no "
                    "per-index document-count metric."
                ),
            ),
            Panel(
                "Database size and 24h growth",
                (
                    Query("meilisearch_db_size_bytes", "Size"),
                    Query(
                        "meilisearch_db_size_bytes - meilisearch_db_size_bytes offset 24h",
                        "24h growth",
                    ),
                ),
                unit="bytes",
            ),
        ),
        links=(
            OVERVIEW_LINK,
            LOGS_LINK,
            (
                "Meilisearch detail",
                "/d/forge-meilisearch-detail?${__url_time_range}",
            ),
        ),
    ),
    Dashboard(
        folder="Curated",
        uid="forge-host-containers",
        title="Forge Host and Containers",
        panels=(
            Panel(
                "Host CPU and load",
                (
                    Query(
                        '1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))',
                        "CPU used",
                    ),
                    Query("node_load1", "Load 1m", unit="short"),
                    Query("node_load5", "Load 5m", unit="short"),
                    Query("node_load15", "Load 15m", unit="short"),
                ),
                unit="percentunit",
            ),
            Panel(
                "Available memory and swap",
                (
                    Query("node_memory_MemAvailable_bytes", "Available memory"),
                    Query(
                        "node_memory_SwapTotal_bytes - node_memory_SwapFree_bytes",
                        "Swap used",
                    ),
                ),
                unit="bytes",
            ),
            Panel(
                "Filesystem and inode free ratio",
                (
                    Query(
                        'node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}',
                        "{{mountpoint}} bytes free",
                    ),
                    Query(
                        'node_filesystem_files_free{fstype!~"tmpfs|overlay"} / node_filesystem_files{fstype!~"tmpfs|overlay"}',
                        "{{mountpoint}} inodes free",
                    ),
                ),
                unit="percentunit",
            ),
            Panel(
                "Disk I/O",
                (
                    Query(
                        "sum by (device) (rate(node_disk_read_bytes_total[5m]))",
                        "{{device}} read",
                        unit="Bps",
                    ),
                    Query(
                        "sum by (device) (rate(node_disk_written_bytes_total[5m]))",
                        "{{device}} write",
                        unit="Bps",
                    ),
                    Query(
                        "sum by (device) (rate(node_disk_io_time_seconds_total[5m]))",
                        "{{device}} busy",
                        unit="percentunit",
                    ),
                ),
            ),
            Panel(
                "Host network errors",
                (
                    Query(
                        "sum by (device) (rate(node_network_receive_errs_total[5m]) + rate(node_network_transmit_errs_total[5m]))",
                        "{{device}}",
                    ),
                ),
                unit="ops",
            ),
            Panel(
                "Container CPU / throttling",
                (
                    Query(
                        "sum by (compose_service) (rate(container_cpu_usage_seconds_total[5m]))",
                        "{{compose_service}} CPU",
                    ),
                    Query(
                        "sum by (compose_service) (rate(container_cpu_cfs_throttled_seconds_total[5m]))",
                        "{{compose_service}} throttled",
                    ),
                ),
                unit="percentunit",
                data_links=(SERVICE_LOG_LINK,),
            ),
            Panel(
                "Container working set",
                (
                    Query(
                        "sum by (compose_service) (container_memory_working_set_bytes)",
                        "{{compose_service}}",
                    ),
                ),
                unit="bytes",
                data_links=(SERVICE_LOG_LINK,),
            ),
            Panel(
                "Container restart / OOM events",
                (
                    Query(
                        "changes((max by (compose_service) "
                        "(container_start_time_seconds))[1h:])",
                        "{{compose_service}} restarts",
                    ),
                    Query(
                        "sum by (compose_service) (increase(container_oom_events_total[1h]))",
                        "{{compose_service}} OOM",
                    ),
                ),
                data_links=(SERVICE_LOG_LINK,),
            ),
            Panel(
                "Container network traffic",
                (
                    Query(
                        "sum by (compose_service) (rate(container_network_receive_bytes_total[5m]))",
                        "{{compose_service}} receive",
                    ),
                    Query(
                        "sum by (compose_service) (rate(container_network_transmit_bytes_total[5m]))",
                        "{{compose_service}} transmit",
                    ),
                ),
                unit="Bps",
                data_links=(SERVICE_LOG_LINK,),
            ),
            Panel(
                "Container filesystem",
                (
                    Query(
                        "sum by (compose_service) (container_fs_usage_bytes)",
                        "{{compose_service}} used",
                    ),
                    Query(
                        "sum by (compose_service) (container_fs_limit_bytes)",
                        "{{compose_service}} limit",
                    ),
                ),
                unit="bytes",
                data_links=(SERVICE_LOG_LINK,),
            ),
        ),
        links=(
            OVERVIEW_LINK,
            LOGS_LINK,
            ("Node exporter", "/d/forge-node-exporter?${__url_time_range}"),
            ("cAdvisor", "/d/forge-cadvisor?${__url_time_range}"),
        ),
    ),
)

DASHBOARDS += (
    Dashboard(
        folder="Exporters",
        uid="forge-redis-exporter",
        title="Redis Exporter Detail",
        panels=_exporter_health("redis", "redis_exporter_build_info")
        + (
            Panel(
                "Uptime and clients",
                (
                    Query("redis_uptime_in_seconds", "Uptime", unit="s"),
                    Query("redis_connected_clients", "Connected"),
                    Query("redis_blocked_clients", "Blocked"),
                ),
            ),
            Panel(
                "Memory and fragmentation",
                (
                    Query("redis_memory_used_bytes", "Used", unit="bytes"),
                    Query("redis_memory_used_rss_bytes", "RSS", unit="bytes"),
                    Query("redis_memory_max_bytes", "Maximum", unit="bytes"),
                    Query("redis_mem_fragmentation_ratio", "Fragmentation"),
                ),
            ),
            Panel(
                "Keys and expiry",
                (
                    Query("sum by (db) (redis_db_keys)", "{{db}} keys"),
                    Query("sum by (db) (redis_db_keys_expiring)", "{{db}} expiring"),
                ),
            ),
            Panel(
                "Cache hits and misses",
                (
                    Query("rate(redis_keyspace_hits_total[5m])", "Hits"),
                    Query("rate(redis_keyspace_misses_total[5m])", "Misses"),
                    Query(
                        "(rate(redis_keyspace_hits_total[5m]) / (rate(redis_keyspace_hits_total[5m]) + rate(redis_keyspace_misses_total[5m]))) and on() ((rate(redis_keyspace_hits_total[5m]) + rate(redis_keyspace_misses_total[5m])) > 0)",
                        "Hit ratio",
                        unit="percentunit",
                    ),
                ),
            ),
            Panel(
                "Commands",
                (
                    Query(
                        'sum by (cmd) (rate(redis_commands_total{cmd=~"$cmd"}[5m]))',
                        "{{cmd}}",
                    ),
                ),
            ),
            Panel(
                "Evictions, expirations and rejected connections",
                (
                    Query("rate(redis_evicted_keys_total[5m])", "Evicted"),
                    Query("rate(redis_expired_keys_total[5m])", "Expired"),
                    Query("rate(redis_rejected_connections_total[5m])", "Rejected"),
                ),
            ),
            Panel(
                "Network traffic",
                (
                    Query("rate(redis_net_input_bytes_total[5m])", "Input", unit="Bps"),
                    Query(
                        "rate(redis_net_output_bytes_total[5m])", "Output", unit="Bps"
                    ),
                ),
            ),
            Panel(
                "Persistence state",
                (
                    Query("redis_rdb_last_bgsave_status", "RDB"),
                    Query("redis_aof_enabled", "AOF enabled"),
                    Query("redis_aof_last_bgrewrite_status", "AOF rewrite"),
                ),
            ),
            Panel(
                "Replication",
                (
                    Query("redis_instance_info", "{{role}}"),
                    Query("redis_connected_slaves", "Replicas"),
                    Query("redis_master_repl_offset", "Master offset"),
                    Query("redis_slave_repl_offset", "Replica offset"),
                ),
            ),
            Panel(
                "Redis CPU and slowlog",
                (
                    Query("rate(redis_cpu_sys_seconds_total[5m])", "System CPU"),
                    Query("rate(redis_cpu_user_seconds_total[5m])", "User CPU"),
                    Query("redis_slowlog_length", "Slowlog length"),
                ),
            ),
        ),
        links=_detail_links("Async and Redis", "forge-async-redis"),
        variables=(_prom_variable("cmd", "redis_commands_total", "cmd", "redis"),),
    ),
    Dashboard(
        folder="Exporters",
        uid="forge-celery-exporter",
        title="Celery Exporter Detail",
        panels=_exporter_health("celery", None, process_health=False)
        + (
            Panel(
                "Workers and processes",
                (
                    Query(
                        'sum by (worker) (celery_worker_up{worker=~"$worker"})',
                        "{{worker}} heartbeat",
                    ),
                    Query("sum(celery_active_worker_count)", "Workers"),
                    Query("sum(celery_active_process_count)", "Processes"),
                ),
            ),
            Panel(
                "Active tasks and queue state",
                (
                    Query(
                        'sum by (worker) (celery_worker_tasks_active{worker=~"$worker"})',
                        "{{worker}} active",
                    ),
                    Query(
                        'forge_celery_queue_depth{queue=~"$queue"}',
                        "{{queue}} depth",
                    ),
                    Query(
                        'forge_celery_oldest_task_age_seconds{queue=~"$queue"}',
                        "{{queue}} oldest",
                        unit="s",
                    ),
                ),
            ),
            Panel(
                "Task lifecycle rates",
                (
                    Query(
                        'sum by (name) (rate(celery_task_sent_total{name=~"$name"}[5m]))',
                        "{{name}} sent",
                    ),
                    Query(
                        'sum by (name) (rate(celery_task_received_total{name=~"$name"}[5m]))',
                        "{{name}} received",
                    ),
                    Query(
                        'sum by (name) (rate(celery_task_started_total{name=~"$name"}[5m]))',
                        "{{name}} started",
                    ),
                ),
            ),
            Panel(
                "Task outcome rates",
                (
                    Query(
                        'sum by (name) (rate(celery_task_succeeded_total{name=~"$name"}[5m]))',
                        "{{name}} succeeded",
                    ),
                    Query(
                        'sum by (name) (rate(celery_task_failed_total{name=~"$name"}[5m]))',
                        "{{name}} failed",
                    ),
                    Query(
                        'sum by (name) (rate(celery_task_retried_total{name=~"$name"}[5m]))',
                        "{{name}} retried",
                    ),
                ),
            ),
            Panel(
                "Rejected and revoked tasks",
                (
                    Query(
                        'sum by (name) (rate(celery_task_rejected_total{name=~"$name"}[5m]))',
                        "{{name}} rejected",
                    ),
                    Query(
                        'sum by (name) (rate(celery_task_revoked_total{name=~"$name"}[5m]))',
                        "{{name}} revoked",
                    ),
                ),
            ),
            Panel(
                "Task runtime percentiles",
                (
                    Query(
                        'histogram_quantile(0.50, sum by (name, le) (rate(celery_task_runtime_bucket{name=~"$name"}[5m])))',
                        "{{name}} p50",
                    ),
                    Query(
                        'histogram_quantile(0.95, sum by (name, le) (rate(celery_task_runtime_bucket{name=~"$name"}[5m])))',
                        "{{name}} p95",
                    ),
                    Query(
                        'histogram_quantile(0.99, sum by (name, le) (rate(celery_task_runtime_bucket{name=~"$name"}[5m])))',
                        "{{name}} p99",
                    ),
                ),
                unit="s",
            ),
            Panel(
                "Top tasks by throughput",
                (
                    Query(
                        'topk(10, sum by (name) (rate(celery_task_received_total{name=~"$name"}[5m])))',
                        "{{name}}",
                    ),
                ),
                kind="table",
            ),
            Panel(
                "Top tasks by failures",
                (
                    Query(
                        'topk(10, sum by (name) (rate(celery_task_failed_total{name=~"$name"}[5m])))',
                        "{{name}}",
                    ),
                ),
                kind="table",
            ),
            Panel(
                "Top tasks by p95 runtime",
                (
                    Query(
                        'topk(10, histogram_quantile(0.95, sum by (name, le) (rate(celery_task_runtime_bucket{name=~"$name"}[5m]))))',
                        "{{name}}",
                    ),
                ),
                kind="table",
                unit="s",
            ),
        ),
        links=_detail_links("Async and Redis", "forge-async-redis"),
        variables=(
            _prom_variable("name", "celery_task_received_total", "name", "celery"),
            _prom_variable("worker", "celery_worker_up", "worker", "celery"),
            _prom_variable("queue", "forge_celery_queue_depth", "queue", "celery"),
        ),
    ),
    Dashboard(
        folder="Exporters",
        uid="forge-nginx-exporter",
        title="Nginx Exporter Detail",
        panels=_exporter_health("nginx", "nginx_exporter_build_info")
        + (
            Panel(
                "Nginx health",
                (Query("nginx_up", "Nginx"),),
                kind="stat",
                thresholds=((None, "red"), (1, "green")),
            ),
            Panel(
                "Connections by state",
                (
                    Query("nginx_connections_active", "Active"),
                    Query("nginx_connections_reading", "Reading"),
                    Query("nginx_connections_writing", "Writing"),
                    Query("nginx_connections_waiting", "Waiting"),
                ),
            ),
            Panel(
                "Accepted and handled connections",
                (
                    Query("rate(nginx_connections_accepted[5m])", "Accepted"),
                    Query("rate(nginx_connections_handled[5m])", "Handled"),
                ),
            ),
            Panel(
                "Request rate",
                (Query("rate(nginx_http_requests_total[5m])", "Requests"),),
                unit="reqps",
            ),
            Panel(
                "Connection drops",
                (
                    Query(
                        "rate(nginx_connections_accepted[5m]) - rate(nginx_connections_handled[5m])",
                        "Dropped",
                    ),
                ),
                thresholds=((None, "green"), (1, "red")),
            ),
        ),
        links=_detail_links("API", "forge-api"),
    ),
    Dashboard(
        folder="Exporters",
        uid="forge-meilisearch-detail",
        title="Meilisearch Detail",
        panels=_exporter_health("meilisearch", None)
        + (
            Panel(
                "HTTP request rate",
                (
                    Query(
                        'sum by (status) (rate(meilisearch_http_requests_total{path!~"/health|/metrics"}[5m]))',
                        "{{status}}",
                    ),
                ),
                unit="reqps",
            ),
            Panel(
                "HTTP latency",
                (
                    Query(
                        'histogram_quantile(0.95, sum by (le) (rate(meilisearch_http_response_time_seconds_bucket{path!~"/health|/metrics"}[5m])))',
                        "p95",
                    ),
                ),
                unit="s",
            ),
            Panel(
                "HTTP status share",
                (
                    Query(
                        'sum(rate(meilisearch_http_requests_total{status=~"2..|3..",path!~"/health|/metrics"}[5m])) / sum(rate(meilisearch_http_requests_total{path!~"/health|/metrics"}[5m])) and on() (sum(rate(meilisearch_http_requests_total{path!~"/health|/metrics"}[5m])) > 0)',
                        "Successful",
                    ),
                    Query(
                        'sum(rate(meilisearch_http_requests_total{status=~"4..|5..",path!~"/health|/metrics"}[5m])) / sum(rate(meilisearch_http_requests_total{path!~"/health|/metrics"}[5m])) and on() (sum(rate(meilisearch_http_requests_total{path!~"/health|/metrics"}[5m])) > 0)',
                        "Error",
                    ),
                ),
                unit="percentunit",
            ),
            Panel(
                "Index count and indexing state",
                (
                    Query("meilisearch_index_count", "Indexes"),
                    Query("meilisearch_is_indexing", "Indexing"),
                ),
            ),
            Panel(
                "Tasks by status and kind",
                (
                    Query(
                        "sum by (kind, value) (meilisearch_nb_tasks)",
                        "{{kind}} {{value}}",
                    ),
                ),
            ),
            Panel(
                "Database used and allocated size",
                (
                    Query("meilisearch_used_db_size_bytes", "Used", unit="bytes"),
                    Query(
                        "meilisearch_db_size_bytes",
                        "Allocated",
                        unit="bytes",
                    ),
                ),
            ),
            Panel(
                "Database 24h growth",
                (
                    Query(
                        "meilisearch_used_db_size_bytes - meilisearch_used_db_size_bytes offset 24h",
                        "Used growth",
                        unit="bytes",
                    ),
                    Query(
                        "meilisearch_db_size_bytes - meilisearch_db_size_bytes offset 24h",
                        "Allocated growth",
                        unit="bytes",
                    ),
                ),
            ),
        ),
        links=_detail_links("Search", "forge-search"),
    ),
    Dashboard(
        folder="Exporters",
        uid="forge-prometheus-detail",
        title="Prometheus Detail",
        panels=_exporter_health(
            "prometheus", "prometheus_build_info", instance_variable=True
        )
        + (
            Panel(
                "Target scrape health",
                (
                    Query("sum by (job) (up)", "{{job}} up"),
                    Query(
                        "max by (job) (scrape_duration_seconds)",
                        "{{job}} duration",
                        unit="s",
                    ),
                    Query("sum by (job) (scrape_samples_scraped)", "{{job}} samples"),
                    Query("sum by (job) (scrape_series_added)", "{{job}} series added"),
                ),
                description=(
                    "Global cross-target scrape overview; intentionally not filtered "
                    "by the Prometheus self-instance variable."
                ),
            ),
            Panel(
                "Rule evaluation",
                (
                    Query(
                        'max(prometheus_rule_group_duration_seconds{instance=~"$instance"})',
                        "Group duration",
                        unit="s",
                    ),
                    Query(
                        'rate(prometheus_rule_evaluation_failures_total{instance=~"$instance"}[5m])',
                        "Failures",
                    ),
                    Query(
                        'rate(prometheus_rule_group_iterations_missed_total{instance=~"$instance"}[5m])',
                        "Missed",
                    ),
                ),
            ),
            Panel(
                "Alert states and notification queue",
                (
                    Query(
                        'sum by (alertstate) (ALERTS{alertstate=~"firing|pending"})',
                        "{{alertstate}}",
                    ),
                    Query(
                        'prometheus_notifications_queue_length{instance=~"$instance"}',
                        "Queue",
                    ),
                    Query(
                        'rate(prometheus_notifications_errors_total{instance=~"$instance"}[5m])',
                        "Errors",
                    ),
                ),
                description=(
                    "Alert states are global synthetic series; notification queue "
                    "and error metrics honor the selected Prometheus instance."
                ),
            ),
            Panel(
                "TSDB head",
                (
                    Query(
                        'prometheus_tsdb_head_series{instance=~"$instance"}', "Series"
                    ),
                    Query(
                        'prometheus_tsdb_head_chunks{instance=~"$instance"}', "Chunks"
                    ),
                    Query(
                        'rate(prometheus_tsdb_head_samples_appended_total{instance=~"$instance"}[5m])',
                        "Samples",
                    ),
                ),
            ),
            Panel(
                "WAL and compaction",
                (
                    Query(
                        'rate(prometheus_tsdb_wal_fsync_duration_seconds_sum{instance=~"$instance"}[5m])',
                        "WAL fsync",
                        unit="s",
                    ),
                    Query(
                        'rate(prometheus_tsdb_compactions_total{instance=~"$instance"}[5m])',
                        "Compactions",
                    ),
                    Query(
                        'rate(prometheus_tsdb_compactions_failed_total{instance=~"$instance"}[5m])',
                        "Failures",
                    ),
                ),
            ),
            Panel(
                "Block storage",
                (
                    Query(
                        'prometheus_tsdb_storage_blocks_bytes{instance=~"$instance"}',
                        "Blocks",
                        unit="bytes",
                    ),
                ),
            ),
            Panel(
                "Engine concurrency and duration",
                (
                    Query('prometheus_engine_queries{instance=~"$instance"}', "Active"),
                    Query(
                        'prometheus_engine_queries_concurrent_max{instance=~"$instance"}',
                        "Maximum",
                    ),
                    Query(
                        'histogram_quantile(0.95, sum by (slice, le) (rate(prometheus_engine_query_duration_histogram_seconds_bucket{instance=~"$instance"}[5m])))',
                        "{{slice}} p95",
                        unit="s",
                    ),
                ),
            ),
            Panel(
                "Go runtime",
                (
                    Query(
                        'go_goroutines{job="prometheus",instance=~"$instance"}',
                        "Goroutines",
                    ),
                    Query(
                        'go_memstats_heap_alloc_bytes{job="prometheus",instance=~"$instance"}',
                        "Heap",
                        unit="bytes",
                    ),
                ),
            ),
        ),
        links=_detail_links("Continuity", "forge-continuity"),
        variables=(
            _prom_variable(
                "instance", "prometheus_build_info", "instance", "prometheus"
            ),
        ),
    ),
    Dashboard(
        folder="Exporters",
        uid="forge-alertmanager-detail",
        title="Alertmanager Detail",
        panels=_exporter_health(
            "alertmanager", "alertmanager_build_info", instance_variable=True
        )
        + (
            Panel(
                "Cluster health",
                (
                    Query(
                        'alertmanager_cluster_members{instance=~"$instance"}',
                        "Members",
                    ),
                    Query(
                        'alertmanager_cluster_health_score{instance=~"$instance"}',
                        "Health",
                    ),
                ),
            ),
            Panel(
                "Alerts received and invalid",
                (
                    Query(
                        'rate(alertmanager_alerts_received_total{instance=~"$instance"}[5m])',
                        "Received",
                    ),
                    Query(
                        'rate(alertmanager_alerts_invalid_total{instance=~"$instance"}[5m])',
                        "Invalid",
                    ),
                ),
            ),
            Panel(
                "Notifications and failures",
                (
                    Query(
                        'sum by (integration) (rate(alertmanager_notifications_total{instance=~"$instance"}[5m]))',
                        "{{integration}} sent",
                    ),
                    Query(
                        'sum by (integration) (rate(alertmanager_notifications_failed_total{instance=~"$instance"}[5m]))',
                        "{{integration}} failed",
                    ),
                ),
            ),
            Panel(
                "Notification latency",
                (
                    Query(
                        'histogram_quantile(0.95, sum by (integration, le) (rate(alertmanager_notification_latency_seconds_bucket{instance=~"$instance"}[5m])))',
                        "{{integration}} p95",
                    ),
                ),
                unit="s",
            ),
            Panel(
                "Cluster message queue",
                (
                    Query(
                        'alertmanager_cluster_messages_queued{instance=~"$instance"}',
                        "Queued",
                    ),
                ),
            ),
            Panel(
                "Silences and inhibition",
                (
                    Query(
                        'sum by (state) (alertmanager_silences{state=~"active|pending",instance=~"$instance"})',
                        "{{state}} silences",
                    ),
                    Query(
                        'alertmanager_inhibition_rules{instance=~"$instance"}',
                        "Inhibition rules",
                    ),
                ),
            ),
            Panel(
                "Configuration reload",
                (
                    Query(
                        'alertmanager_config_last_reload_successful{instance=~"$instance"}',
                        "Success",
                    ),
                    Query(
                        'time() - alertmanager_config_last_reload_success_timestamp_seconds{instance=~"$instance"}',
                        "Age",
                        unit="s",
                    ),
                ),
            ),
            Panel(
                "Dispatcher groups",
                (
                    Query(
                        'alertmanager_dispatcher_aggregation_groups{instance=~"$instance"}',
                        "Groups",
                    ),
                ),
            ),
            Panel(
                "Go runtime",
                (
                    Query(
                        'go_goroutines{job="alertmanager",instance=~"$instance"}',
                        "Goroutines",
                    ),
                    Query(
                        'go_memstats_heap_alloc_bytes{job="alertmanager",instance=~"$instance"}',
                        "Heap",
                        unit="bytes",
                    ),
                ),
            ),
        ),
        links=_detail_links("Continuity", "forge-continuity"),
        variables=(
            _prom_variable(
                "instance", "alertmanager_build_info", "instance", "alertmanager"
            ),
        ),
    ),
    Dashboard(
        folder="Exporters",
        uid="forge-loki-detail",
        title="Loki Detail",
        panels=_exporter_health("loki", "loki_build_info", instance_variable=True)
        + (
            Panel(
                "Distributor ingestion",
                (
                    Query(
                        'sum(rate(loki_distributor_bytes_received_total{instance=~"$instance"}[5m]))',
                        "Bytes",
                        unit="Bps",
                    ),
                    Query(
                        'sum(rate(loki_distributor_lines_received_total{instance=~"$instance"}[5m]))',
                        "Lines",
                    ),
                    Query(
                        'sum(rate(loki_discarded_bytes_total{instance=~"$instance"}[5m]))',
                        "Discarded bytes",
                        unit="Bps",
                    ),
                    Query(
                        'sum(rate(loki_discarded_samples_total{instance=~"$instance"}[5m]))',
                        "Discarded lines",
                    ),
                ),
            ),
            Panel(
                "Request traffic",
                (
                    Query(
                        'sum(rate(loki_request_duration_seconds_count{instance=~"$instance"}[5m]))',
                        "Request rate",
                    ),
                    Query(
                        'histogram_quantile(0.95, sum by (le) (rate(loki_request_duration_seconds_bucket{instance=~"$instance"}[5m])))',
                        "p95",
                        unit="s",
                    ),
                    Query(
                        'sum by (status_code) (rate(loki_request_duration_seconds_count{instance=~"$instance"}[5m]))',
                        "{{status_code}}",
                    ),
                ),
            ),
            Panel(
                "Ingester streams and chunks",
                (
                    Query(
                        'sum(loki_ingester_memory_streams{instance=~"$instance"})',
                        "Streams",
                    ),
                    Query(
                        'sum(rate(loki_ingester_chunks_created_total{instance=~"$instance"}[5m]))',
                        "Chunks created / s",
                    ),
                    Query(
                        'sum(rate(loki_ingester_chunks_flush_requests_total{instance=~"$instance"}[5m]))',
                        "Flushes",
                    ),
                    Query(
                        'sum(rate(loki_ingester_chunks_flush_failures_total{instance=~"$instance"}[5m]))',
                        "Failures",
                    ),
                ),
            ),
            Panel(
                "WAL activity",
                (
                    Query(
                        'sum(rate(loki_ingester_wal_records_logged_total{instance=~"$instance"}[5m]))',
                        "Records",
                    ),
                    Query(
                        'sum(rate(loki_ingester_wal_disk_full_failures_total{instance=~"$instance"}[5m]))',
                        "Disk-full failures",
                    ),
                ),
            ),
            Panel(
                "Compactor",
                (
                    Query(
                        'loki_boltdb_shipper_compactor_running{instance=~"$instance"}',
                        "Running",
                    ),
                    Query(
                        '(time() - loki_boltdb_shipper_compact_tables_operation_last_successful_run_timestamp_seconds{instance=~"$instance"}) and on(instance) (loki_boltdb_shipper_compact_tables_operation_last_successful_run_timestamp_seconds{instance=~"$instance"} > 0)',
                        "Last success age",
                        unit="s",
                    ),
                ),
            ),
            Panel(
                "Storage and cache integrity",
                (
                    Query(
                        'rate(loki_cache_corrupt_chunks_total{instance=~"$instance"}[5m])',
                        "Corrupt chunks",
                    ),
                    Query(
                        'rate(loki_querier_index_cache_corruptions_total{instance=~"$instance"}[5m])',
                        "Index cache corruptions",
                    ),
                ),
            ),
            Panel(
                "Query frontend",
                (
                    Query(
                        'loki_query_frontend_queries_in_progress{instance=~"$instance"}',
                        "In progress",
                    ),
                    Query(
                        'loki_query_scheduler_inflight_requests{instance=~"$instance",quantile="0.95"}',
                        "Scheduler inflight p95",
                    ),
                ),
            ),
            Panel(
                "Go runtime",
                (
                    Query(
                        'go_goroutines{job="loki",instance=~"$instance"}',
                        "Goroutines",
                    ),
                    Query(
                        'go_memstats_heap_alloc_bytes{job="loki",instance=~"$instance"}',
                        "Heap",
                        unit="bytes",
                    ),
                ),
            ),
        ),
        links=_detail_links("Logs and Changes", "forge-logs-changes"),
        variables=(_prom_variable("instance", "loki_build_info", "instance", "loki"),),
    ),
    Dashboard(
        folder="Exporters",
        uid="forge-alloy-detail",
        title="Alloy Detail",
        panels=_exporter_health("alloy", "alloy_build_info")
        + (
            Panel(
                "Component health",
                (
                    Query(
                        'alloy_component_controller_running_components{health_type=~"$health_type"}',
                        "{{controller_path}} {{controller_id}} {{health_type}}",
                    ),
                ),
            ),
            Panel(
                "Docker log collection",
                (
                    Query(
                        "rate(loki_source_docker_target_entries_total[5m])", "Entries"
                    ),
                    Query(
                        "rate(loki_source_docker_target_parsing_errors_total[5m])",
                        "Parsing errors",
                    ),
                ),
            ),
            Panel(
                "Loki write",
                (
                    Query("rate(loki_write_sent_entries_total[5m])", "Sent"),
                    Query(
                        "rate(loki_write_dropped_entries_total[5m])",
                        "Dropped {{reason}}",
                    ),
                ),
            ),
            Panel(
                "cAdvisor collection",
                (
                    Query(
                        "(rate(prometheus_target_scrape_duration_seconds_sum[5m]) / rate(prometheus_target_scrape_duration_seconds_count[5m])) and (rate(prometheus_target_scrape_duration_seconds_count[5m]) > 0)",
                        "Scrape duration",
                        unit="s",
                    ),
                    Query(
                        "prometheus_scrape_targets_gauge",
                        "Targets",
                    ),
                ),
            ),
            Panel(
                "Remote write samples",
                (
                    Query("rate(prometheus_remote_storage_samples_total[5m])", "Sent"),
                    Query(
                        "rate(prometheus_remote_storage_samples_failed_total[5m])",
                        "Failed",
                    ),
                    Query(
                        "rate(prometheus_remote_storage_samples_retried_total[5m])",
                        "Retried",
                    ),
                ),
            ),
            Panel(
                "Remote write queue",
                (
                    Query("prometheus_remote_storage_shards", "Shards"),
                    Query("prometheus_remote_storage_samples_pending", "Pending"),
                ),
            ),
            Panel(
                "Configuration reload",
                (
                    Query("alloy_config_last_load_successful", "Success"),
                    Query(
                        "time() - alloy_config_last_load_success_timestamp_seconds",
                        "Age",
                        unit="s",
                    ),
                ),
            ),
            Panel(
                "Go runtime",
                (
                    Query('go_goroutines{job="alloy"}', "Goroutines"),
                    Query(
                        'go_memstats_heap_alloc_bytes{job="alloy"}',
                        "Heap",
                        unit="bytes",
                    ),
                ),
            ),
        ),
        links=_detail_links("Logs and Changes", "forge-logs-changes"),
        variables=(
            _prom_variable(
                "health_type",
                "alloy_component_controller_running_components",
                "health_type",
                "alloy",
            ),
        ),
    ),
)
