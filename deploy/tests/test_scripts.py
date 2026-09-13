from __future__ import annotations

import grp
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[1]
SCRIPTS = DEPLOY / "scripts"
OPERATION_LOCK_HELPER = SCRIPTS / "lib/operation-lock.sh"
ALL_SCRIPTS = sorted(
    path.relative_to(DEPLOY).as_posix()
    for path in (*SCRIPTS.rglob("*.sh"), *(DEPLOY / "backup").glob("*.sh"))
)
linux_only = pytest.mark.skipif(
    sys.platform != "linux",
    reason="script harnesses need GNU stat, chmod 2770 and flock",
)


def _deployment_group() -> str:
    return grp.getgrgid(os.getgid()).gr_name


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def _metric_value(text: str, metric: str) -> float:
    line = next(line for line in text.splitlines() if line.startswith(metric))
    return float(line.rsplit(" ", maxsplit=1)[1])


@pytest.mark.parametrize("script", ALL_SCRIPTS)
def test_scripts_are_executable_posix_shell_and_parse(script: str) -> None:
    path = DEPLOY / script
    assert path.read_text().startswith("#!/bin/sh\n"), script
    assert path.stat().st_mode & stat.S_IXUSR, script
    subprocess.run(["sh", "-n", str(path)], check=True)


def test_scripts_use_forge_names_and_no_reference_project_services() -> None:
    for script in ALL_SCRIPTS:
        text = (DEPLOY / script).read_text()
        for forbidden in (
            "wiki",
            "legacy-response",
            "celery-priority",
            "celery-automation",
            "settings.prod",
        ):
            assert forbidden not in text, (script, forbidden)


# --- lib/compose.sh -----------------------------------------------------------


def _compose_lib_harness(
    tmp_path: Path, *, plugin: bool, standalone: bool
) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "docker",
        "#!/bin/sh\n"
        'if [ "${1:-}" = compose ] && [ "${2:-}" = version ]; then exit '
        + ("0" if plugin else "1")
        + "; fi\n"
        'printf "docker %s\\n" "$*"\n',
    )
    if standalone:
        _write_executable(
            fake_bin / "docker-compose",
            '#!/bin/sh\nif [ "${1:-}" = version ]; then exit 0; fi\nprintf "docker-compose %s\\n" "$*"\n',  # noqa: E501
        )
    _write_executable(fake_bin / "getent", '#!/bin/sh\nprintf "%s:x:4242:\\n" "$2"\n')
    for command in ("awk", "sh", "printf"):
        source = shutil.which(command)
        if source and not (fake_bin / command).exists():
            (fake_bin / command).symlink_to(source)
    return subprocess.run(
        ["sh", "-c", f'. "{SCRIPTS / "lib/compose.sh"}"; compose ps'],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "DEPLOY_GROUP": "forge-deploy",
        },
        text=True,
        capture_output=True,
        check=False,
    )


def test_compose_library_prefers_v2_plugin() -> None:
    result = _compose_lib_harness(
        Path(__import__("tempfile").mkdtemp()), plugin=True, standalone=True
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "docker compose ps"


def test_compose_library_falls_back_to_standalone_binary(tmp_path: Path) -> None:
    result = _compose_lib_harness(tmp_path, plugin=False, standalone=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "docker-compose ps"


def test_compose_library_reports_missing_compose(tmp_path: Path) -> None:
    result = _compose_lib_harness(tmp_path, plugin=False, standalone=False)
    assert result.returncode != 0
    assert "docker compose or docker-compose is required" in result.stderr


def test_compose_library_rejects_unsafe_or_missing_group() -> None:
    for group, message in (("", "safe group name"), ("bad;group", "safe group name")):
        result = subprocess.run(
            ["sh", "-c", f'. "{SCRIPTS / "lib/compose.sh"}"; compose ps'],
            env={"PATH": os.environ["PATH"], "DEPLOY_GROUP": group},
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0
        assert message in result.stderr


def test_manual_compose_wrapper_requires_readable_env_file(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(SCRIPTS / "compose.sh"), "ps"],
        env={**os.environ, "ENV_FILE": str(tmp_path / "missing.env")},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "ENV_FILE is not readable" in result.stderr


# --- operation lock -------------------------------------------------------------


def _lock_env(tmp_path: Path) -> dict[str, str]:
    return {
        **os.environ,
        "DATA_ROOT": str(tmp_path),
        "DEPLOY_GROUP": _deployment_group(),
        "SOURCE_REVISION": "revision-1",
    }


@linux_only
def test_operation_lock_rejects_unknown_operations(tmp_path: Path) -> None:
    result = subprocess.run(
        ["sh", "-c", f'. "{OPERATION_LOCK_HELPER}"; acquire_operation_lock wiki-start'],
        env=_lock_env(tmp_path),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "operation must be one of deploy, restore, or reset" in result.stderr
    assert not (tmp_path / "run").exists()


@linux_only
def test_operation_lock_blocks_a_second_process_and_hides_its_token(
    tmp_path: Path,
) -> None:
    if shutil.which("flock") is None:
        pytest.skip("flock is required")
    script = (
        f'. "{OPERATION_LOCK_HELPER}"\n'
        "acquire_operation_lock deploy || exit 3\n"
        'sh -c \'. "$1"; acquire_operation_lock restore\' sh "'
        + str(OPERATION_LOCK_HELPER)
        + '" >/dev/null 2>"$SECOND_STDERR"\n'
        "second=$?\n"
        'cat "$DATA_ROOT/run/operations.lock.meta" > "$META_COPY"\n'
        "show_operation_lock\n"
        "release_operation_lock\n"
        'test ! -e "$DATA_ROOT/run/operations.lock.meta" || exit 4\n'
        'exit "$second"\n'
    )
    env = {
        **_lock_env(tmp_path),
        "SECOND_STDERR": str(tmp_path / "second.err"),
        "META_COPY": str(tmp_path / "meta.copy"),
    }
    result = subprocess.run(
        ["sh", "-c", script], env=env, text=True, capture_output=True, check=False
    )
    assert result.returncode == 1, result.stderr
    assert "operation lock is held" in (tmp_path / "second.err").read_text()
    metadata = (tmp_path / "meta.copy").read_text()
    assert "operation_lock_operation=deploy" in metadata
    assert "operation_lock_token=deploy-" in metadata
    assert "operation_lock_token" not in result.stdout
    assert "operation_lock_operation=deploy" in result.stdout
    assert stat.S_IMODE((tmp_path / "run").stat().st_mode) == 0o2770


# --- maintenance.sh --------------------------------------------------------------


def _maintenance_run(
    data_root: Path, *args: str, revision: str = "revision-1"
) -> subprocess.CompletedProcess[str]:
    fake_bin = data_root / ".maintenance-test-bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    _write_executable(fake_bin / "flock", "#!/bin/sh\nexit 0\n")
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DATA_ROOT": str(data_root),
        "DEPLOY_GROUP": _deployment_group(),
        "SOURCE_REVISION": revision,
    }
    return subprocess.run(
        [str(SCRIPTS / "maintenance.sh"), *args],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@linux_only
def test_maintenance_start_and_finish_publish_forge_metrics(tmp_path: Path) -> None:
    before_start = int(time.time())
    started = _maintenance_run(tmp_path, "start", "deploy", "900")
    after_start = int(time.time())
    assert started.returncode == 0, started.stderr
    token = started.stdout.strip()
    assert token.startswith("deploy-")
    flag = tmp_path / "runtime/maintenance"
    metrics = tmp_path / "runtime/node-exporter/forge_maintenance.prom"
    assert flag.is_file()
    text = metrics.read_text()
    assert _metric_value(text, "forge_maintenance_mode") == 1
    started_at = _metric_value(text, "forge_maintenance_started_timestamp_seconds")
    suppress_until = _metric_value(
        text, "forge_maintenance_suppress_until_timestamp_seconds"
    )
    assert before_start <= started_at <= after_start
    assert started_at <= suppress_until <= started_at + 900
    assert 'forge_maintenance_info{reason="deploy",revision="revision-1"} 1' in text

    status = _maintenance_run(tmp_path, "status")
    assert status.returncode == 0
    assert "forge_maintenance_mode 1" in status.stdout
    assert "maintenance_lease_reason deploy" in status.stdout

    wrong = _maintenance_run(tmp_path, "finish", "deploy", "not-the-token")
    assert wrong.returncode != 0
    assert "token does not match active lease" in wrong.stderr
    assert flag.is_file()

    finished = _maintenance_run(tmp_path, "finish", "deploy", token)
    assert finished.returncode == 0, finished.stderr
    assert not flag.exists()
    assert _metric_value(metrics.read_text(), "forge_maintenance_mode") == 0


@linux_only
def test_maintenance_publish_deploy_writes_revision_metric(tmp_path: Path) -> None:
    result = _maintenance_run(tmp_path, "publish-deploy", revision="abc1234")
    assert result.returncode == 0, result.stderr
    text = (tmp_path / "runtime/node-exporter/forge_deployment.prom").read_text()
    assert text.startswith('forge_deployment_timestamp_seconds{revision="abc1234"} ')


@linux_only
@pytest.mark.parametrize(
    ("args", "revision"),
    [
        (("start", "invalid", "900"), "revision-1"),
        (("start", "deploy", "seconds"), "revision-1"),
        (("start", "deploy", "59"), "revision-1"),
        (("start", "deploy", "172801"), "revision-1"),
        (("start", "deploy", "900"), "unsafe/revision"),
        (("finish", "not-a-reason", "safe-token"), "revision-1"),
    ],
)
def test_maintenance_invalid_input_preserves_existing_state(
    tmp_path: Path, args: tuple[str, ...], revision: str
) -> None:
    textfile_dir = tmp_path / "runtime/node-exporter"
    textfile_dir.mkdir(parents=True)
    metrics = textfile_dir / "forge_maintenance.prom"
    metrics.write_text("existing metrics\n")
    result = _maintenance_run(tmp_path, *args, revision=revision)
    assert result.returncode != 0
    assert metrics.read_text() == "existing metrics\n"
    assert not (tmp_path / "runtime/maintenance").exists()
    assert not (tmp_path / "runtime/maintenance.lease").exists()


@linux_only
def test_maintenance_reset_all_requires_confirmation_and_clears_state(
    tmp_path: Path,
) -> None:
    started = _maintenance_run(tmp_path, "start", "deploy", "900")
    assert started.returncode == 0, started.stderr
    refused = _maintenance_run(tmp_path, "reset-all")
    assert refused.returncode != 0
    assert "CONFIRM_RESET_ALL_LEASES=true" in refused.stderr
    assert (tmp_path / "runtime/maintenance").exists()
    fake_bin = tmp_path / ".maintenance-test-bin"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DATA_ROOT": str(tmp_path),
        "DEPLOY_GROUP": _deployment_group(),
        "SOURCE_REVISION": "revision-1",
        "CONFIRM_RESET_ALL_LEASES": "true",
    }
    reset = subprocess.run(
        [str(SCRIPTS / "maintenance.sh"), "reset-all"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert reset.returncode == 0, reset.stderr
    assert "maintenance_reset_after flag=absent lease=absent" in reset.stdout
    assert not (tmp_path / "runtime/maintenance").exists()
    assert (
        _metric_value(
            (tmp_path / "runtime/node-exporter/forge_maintenance.prom").read_text(),
            "forge_maintenance_mode",
        )
        == 0
    )


def test_maintenance_no_arguments_defaults_to_status_and_unknown_prints_usage(
    tmp_path: Path,
) -> None:
    env = {
        **os.environ,
        "DATA_ROOT": str(tmp_path),
        "DEPLOY_GROUP": _deployment_group(),
        "SOURCE_REVISION": "revision-1",
    }
    status = subprocess.run(
        [str(SCRIPTS / "maintenance.sh")],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert status.returncode == 0, status.stderr
    unknown = subprocess.run(
        [str(SCRIPTS / "maintenance.sh"), "explode"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert unknown.returncode == 2
    assert "Usage:" in unknown.stderr


# --- validate-config.sh (preflight) --------------------------------------------------


def _run_preflight(
    tmp_path: Path,
    *,
    deploy_group: str | None = None,
    group_exists: bool = True,
    member_groups: str | None = None,
    include_flock: bool = True,
    run_mode: str = "2770",
    runtime_mode: str = "2770",
    node_exporter_mode: str = "2775",
    shared_gid: str = "4242",
    env_mode: str = "640",
    secret_mode: str = "640",
    key_mismatch: bool = False,
    placeholder_secret: bool = False,
    bexio_token: str = "",
    grafana_uid: str = "472",
    docker_info_status: int = 0,
) -> subprocess.CompletedProcess[str]:
    deploy = tmp_path / "deploy"
    scripts = deploy / "scripts"
    secrets = deploy / "secrets"
    fake_bin = tmp_path / "bin"
    data_root = tmp_path / "data"
    backup_share = tmp_path / "backup"
    env_file = deploy / ".env"
    (scripts / "lib").mkdir(parents=True)
    secrets.mkdir()
    fake_bin.mkdir()
    shutil.copy2(SCRIPTS / "validate-config.sh", scripts)
    shutil.copy2(SCRIPTS / "validate-teams-workflow.sh", scripts)
    shutil.copy2(SCRIPTS / "lib/compose.sh", scripts / "lib")
    shutil.copy2(DEPLOY / "compose.yml", deploy)
    for directory in (
        "run",
        "runtime/node-exporter",
        "static",
        "backups",
        "celerybeat",
        "restore-verification/files",
        "alertmanager",
        "prometheus",
        "pushgateway",
        "grafana",
        "loki",
        "pgadmin",
    ):
        (data_root / directory).mkdir(parents=True, exist_ok=True)
    backup_share.mkdir()
    (tmp_path / "cert.pem").write_text("certificate\n")
    (tmp_path / "key.pem").write_text("key\n")
    for name in (
        "django_secret_key",
        "postgres_password",
        "meilisearch_api_key",
        "admin_htpasswd",
        "grafana_admin_password",
        "pgadmin_password",
    ):
        (secrets / f"{name}.txt").write_text(
            "CHANGE_ME\n"
            if placeholder_secret and name == "pgadmin_password"
            else "not-a-placeholder\n"
        )
    (secrets / "teams_workflow_url.txt").write_text("")
    (secrets / "bexio_access_token.txt").write_text(bexio_token)
    env_file.write_text(
        "\n".join(
            (
                f"DATA_ROOT={data_root}",
                f"DEPLOY_GROUP={deploy_group or _deployment_group()}",
                f"BACKUP_SHARE={backup_share}",
                f"TLS_CERT_FILE={tmp_path / 'cert.pem'}",
                f"TLS_KEY_FILE={tmp_path / 'key.pem'}",
                "APP_DOMAIN=forge.example.test",
                "MONITORING_DOMAIN=monitoring.example.test",
                "ADMIN_DOMAIN=db.example.test",
                "ALERT_TEAMS_ENABLED=false",
                "ALERT_SMTP_AUTH_ENABLED=false",
                "ALERT_SMTP_PASSWORD_FILE=/dev/null",
            )
        )
        + "\n"
    )
    for command in ("awk", "cat", "dirname", "sed", "sh", "tr"):
        source = shutil.which(command)
        assert source, f"{command} is required by the test fixture"
        (fake_bin / command).symlink_to(source)
    _write_executable(
        fake_bin / "docker",
        "#!/bin/sh\n"
        'if [ "${1:-}" = info ]; then exit "${DOCKER_INFO_STATUS:-0}"; fi\n'
        "exit 0\n",
    )
    _write_executable(
        fake_bin / "df",
        "#!/bin/sh\nprintf '%s\\n' 'Filesystem 1024-blocks Used Available Capacity Mounted on'\nprintf '%s\\n' '/dev/test 100000000 0 100000000 0% /'\n",  # noqa: E501
    )
    _write_executable(
        fake_bin / "getent",
        "#!/bin/sh\n"
        'if [ "${PREFLIGHT_GROUP_EXISTS:-true}" = true ]; then printf "%s:x:%s:\\n" "$2" "$PREFLIGHT_SHARED_GID"; exit 0; fi\n'  # noqa: E501
        "exit 2\n",
    )
    _write_executable(
        fake_bin / "id",
        '#!/bin/sh\nif [ "${1:-}" = -Gn ]; then printf "%s\\n" "$PREFLIGHT_MEMBER_GROUPS"; exit 0; fi\nexit 64\n',  # noqa: E501
    )
    _write_executable(
        fake_bin / "openssl",
        "#!/bin/sh\n"
        'case " $* " in\n'
        "  *' -checkend '*) exit 0 ;;\n"
        "  *' x509 -pubkey '*) printf '%s\\n' 'PUBKEY' ;;\n"
        "  *' pkey -pubout '*) printf '%s\\n' \"${PREFLIGHT_KEY_PUBKEY:-PUBKEY}\" ;;\n"
        "  *' md5 '*) cat ;;\n"
        "esac\n",
    )
    _write_executable(
        fake_bin / "stat",
        "#!/bin/sh\n"
        "format=$2\npath=$3\nuid=1000\ngid=1000\nmode=750\n"
        'case "$path" in\n'
        '  "$DATA_ROOT/run") gid=$PREFLIGHT_SHARED_GID; mode=$PREFLIGHT_RUN_MODE ;;\n'
        '  "$DATA_ROOT/runtime") gid=$PREFLIGHT_SHARED_GID; mode=$PREFLIGHT_RUNTIME_MODE ;;\n'  # noqa: E501
        '  "$DATA_ROOT/runtime/node-exporter") gid=$PREFLIGHT_SHARED_GID; mode=$PREFLIGHT_NODE_EXPORTER_MODE ;;\n'  # noqa: E501
        '  "$ENV_FILE") gid=$PREFLIGHT_SHARED_GID; mode=$PREFLIGHT_ENV_MODE ;;\n'
        "  */secrets/*.txt) gid=$PREFLIGHT_SHARED_GID; mode=$PREFLIGHT_SECRET_MODE ;;\n"
        '  "$DATA_ROOT/alertmanager"|"$DATA_ROOT/prometheus"|"$DATA_ROOT/pushgateway") uid=65534; gid=65534 ;;\n'  # noqa: E501
        '  "$DATA_ROOT/grafana") uid=$PREFLIGHT_GRAFANA_UID; gid=0 ;;\n'
        '  "$DATA_ROOT/loki") uid=10001; gid=10001 ;;\n'
        '  "$DATA_ROOT/pgadmin") uid=5050; gid=5050 ;;\n'
        "esac\n"
        'case "$format" in\n'
        '  \'%u %g %a\') printf \'%s %s %s\\n\' "$uid" "$gid" "$mode" ;;\n'
        "  '%g %a') printf '%s %s\\n' \"$gid\" \"$mode\" ;;\n"
        "  *) exit 64 ;;\n"
        "esac\n",
    )
    if include_flock:
        _write_executable(fake_bin / "flock", "#!/bin/sh\nexit 0\n")
    configured_group = deploy_group or _deployment_group()
    environment = {
        "PATH": str(fake_bin),
        "ENV_FILE": str(env_file),
        "PREFLIGHT_GROUP_EXISTS": str(group_exists).lower(),
        "PREFLIGHT_SHARED_GID": shared_gid,
        "PREFLIGHT_MEMBER_GROUPS": member_groups or configured_group,
        "PREFLIGHT_RUN_MODE": run_mode,
        "PREFLIGHT_RUNTIME_MODE": runtime_mode,
        "PREFLIGHT_NODE_EXPORTER_MODE": node_exporter_mode,
        "PREFLIGHT_ENV_MODE": env_mode,
        "PREFLIGHT_SECRET_MODE": secret_mode,
        "PREFLIGHT_KEY_PUBKEY": "OTHER" if key_mismatch else "PUBKEY",
        "PREFLIGHT_GRAFANA_UID": grafana_uid,
        "DOCKER_INFO_STATUS": str(docker_info_status),
    }
    return subprocess.run(
        ["/bin/sh", str(scripts / "validate-config.sh")],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )


def test_preflight_accepts_a_complete_configuration_and_warns_about_empty_bexio_token(
    tmp_path: Path,
) -> None:
    result = _run_preflight(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "preflight ok"
    assert "preflight warning: bexio_access_token.txt is empty" in result.stderr


def test_preflight_is_silent_about_a_configured_bexio_token(tmp_path: Path) -> None:
    result = _run_preflight(tmp_path, bexio_token="real-token\n")
    assert result.returncode == 0, result.stderr
    assert "preflight warning" not in result.stderr
    assert "real-token" not in result.stderr


@pytest.mark.parametrize(
    ("kwargs", "expected_error"),
    (
        (
            {"deploy_group": "not-the-current-group", "member_groups": "operators"},
            "current user is not a member",
        ),
        ({"include_flock": False}, "flock is required"),
        ({"group_exists": False}, "DEPLOY_GROUP does not exist"),
        ({"shared_gid": "not-a-gid"}, "DEPLOY_GROUP has no numeric GID"),
        ({"docker_info_status": 1}, "cannot access the Docker daemon"),
        ({"run_mode": "770"}, "RUN_DIRECTORY must have mode 2770"),
        ({"runtime_mode": "770"}, "RUNTIME_DIRECTORY must have mode 2770"),
        ({"node_exporter_mode": "2770"}, "NODE_EXPORTER_TEXTFILE must have mode 2775"),
        ({"env_mode": "600"}, "DEPLOY_ENV_FILE must be group-readable"),
        ({"env_mode": "644"}, "DEPLOY_ENV_FILE must not grant any world permissions"),
        ({"secret_mode": "600"}, "must be group-readable"),
        ({"secret_mode": "644"}, "must not grant any world permissions"),
        ({"key_mismatch": True}, "TLS certificate and key do not match"),
        ({"placeholder_secret": True}, "secret file contains a placeholder"),
        (
            {"grafana_uid": "1000"},
            "GRAFANA_DATA is not writable by Grafana container UID:GID 472:0",
        ),
    ),
)
def test_preflight_rejects_unsafe_configuration_without_leaking_secrets(
    tmp_path: Path, kwargs: dict[str, object], expected_error: str
) -> None:
    result = _run_preflight(tmp_path, **kwargs)  # type: ignore[arg-type]
    assert result.returncode != 0
    assert expected_error in result.stderr
    assert "not-a-placeholder" not in result.stderr


def test_preflight_keeps_stateful_services_off_host_ports() -> None:
    text = (SCRIPTS / "validate-config.sh").read_text()
    assert "(postgres|pgbouncer|redis|meilisearch|restore-postgres):$" in text
    assert "stateful services publish host ports" in text
    for name in (
        "ALERTMANAGER_DATA",
        "PROMETHEUS_DATA",
        "PUSHGATEWAY_DATA",
        "GRAFANA_DATA",
        "LOKI_DATA",
        "PGADMIN_DATA",
    ):
        assert name in text


# --- deploy.sh --------------------------------------------------------------------


def _run_deploy(
    tmp_path: Path, *, build_status: int = 0, search_index_status: int = 0
) -> tuple[subprocess.CompletedProcess[str], list[str], list[str]]:
    deploy = tmp_path / "deploy"
    scripts = deploy / "scripts"
    (scripts / "lib").mkdir(parents=True)
    shutil.copy2(SCRIPTS / "deploy.sh", scripts)
    shutil.copy2(SCRIPTS / "lib/compose.sh", scripts / "lib")
    shutil.copy2(OPERATION_LOCK_HELPER, scripts / "lib")
    _write_executable(scripts / "validate-config.sh", "#!/bin/sh\nexit 0\n")
    _write_executable(
        scripts / "maintenance.sh",
        "#!/bin/sh\n"
        'printf "maintenance %s\\n" "$1" >> "$MAINTENANCE_LOG"\n'
        'case "$1" in start) echo deploy-token ;; finish-command) echo true ;; esac\n'
        "exit 0\n",
    )
    data_root = tmp_path / "data"
    data_root.mkdir()
    (deploy / ".env").write_text(
        f"DATA_ROOT={data_root}\nDEPLOY_GROUP={_deployment_group()}\nPOSTGRES_USER=forge\nPOSTGRES_DB=forge\nAPP_DOMAIN=forge.example.test\nSOURCE_REVISION=rev-1\n"
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "docker",
        "#!/bin/sh\nset -eu\n"
        'if [ "${1:-}" = compose ] && [ "${2:-}" = version ]; then exit 0; fi\n'
        'printf \'%s\\n\' "$*" >> "$COMPOSE_LOG"\n'
        'case " $* " in\n'
        "  *' build '*) exit \"$BUILD_STATUS\" ;;\n"
        "  *' --profile deployment run --rm --no-deps search-index '*) exit \"$SEARCH_INDEX_STATUS\" ;;\n"  # noqa: E501
        "  *' exec -T nginx curl '*) printf '%s\\n' '{\"data\":{\"__typename\":\"Query\"}}' ;;\n"  # noqa: E501
        "esac\n",
    )
    _write_executable(fake_bin / "getent", '#!/bin/sh\nprintf "%s:x:4242:\\n" "$2"\n')
    _write_executable(fake_bin / "flock", "#!/bin/sh\nexit 0\n")
    compose_log = tmp_path / "compose.log"
    maintenance_log = tmp_path / "maintenance.log"
    result = subprocess.run(
        [str(scripts / "deploy.sh")],
        env={
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "COMPOSE_LOG": str(compose_log),
            "MAINTENANCE_LOG": str(maintenance_log),
            "BUILD_STATUS": str(build_status),
            "SEARCH_INDEX_STATUS": str(search_index_status),
            "HEALTHCHECK_ATTEMPTS": "1",
            "HEALTHCHECK_DELAY_SECONDS": "0",
            "POSTGRES_READY_ATTEMPTS": "1",
            "POSTGRES_READY_DELAY_SECONDS": "0",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    calls = compose_log.read_text().splitlines() if compose_log.exists() else []
    maintenance_calls = (
        maintenance_log.read_text().splitlines() if maintenance_log.exists() else []
    )
    return result, calls, maintenance_calls


@linux_only
def test_deploy_runs_backup_migrations_reindex_then_scales_two_web_replicas(
    tmp_path: Path,
) -> None:
    result, calls, maintenance_calls = _run_deploy(tmp_path)
    assert result.returncode == 0, result.stderr
    backup = calls.index("compose --profile backup run --rm backup")
    migrate = calls.index("compose run --rm django-migrate")
    rebuild = calls.index(
        "compose --profile deployment run --rm --no-deps search-index"
    )
    startup = next(
        index
        for index, call in enumerate(calls)
        if call.startswith("compose up -d --remove-orphans")
    )
    assert backup < migrate < rebuild < startup
    assert (
        calls[startup]
        == "compose up -d --remove-orphans --scale web=2 --scale celery-worker=1"
    )
    assert "compose build" in calls
    assert any(
        "django.core.cache import cache; cache.clear()" in call for call in calls
    )
    assert maintenance_calls == [
        "maintenance start",
        "maintenance finish-command",
        "maintenance publish-deploy",
        "maintenance finish",
    ]
    assert not (tmp_path / "data/run/operations.lock.meta").exists()


@linux_only
def test_deploy_failure_before_maintenance_reports_its_phase(tmp_path: Path) -> None:
    result, _calls, maintenance_calls = _run_deploy(tmp_path, build_status=19)
    assert result.returncode == 19
    assert (
        "deployment failed before this attempt enabled or resumed maintenance mode"
        in result.stderr
    )
    assert maintenance_calls == []


@linux_only
def test_failed_search_index_rebuild_aborts_deploy_in_maintenance(
    tmp_path: Path,
) -> None:
    result, calls, maintenance_calls = _run_deploy(tmp_path, search_index_status=17)
    assert result.returncode == 17
    assert "deployment failed; maintenance mode remains enabled" in result.stderr
    assert not any(call.startswith("compose up -d --remove-orphans") for call in calls)
    assert maintenance_calls == ["maintenance start", "maintenance finish-command"]


def test_deploy_can_skip_backup_only_for_pre_migration_retries() -> None:
    text = (SCRIPTS / "deploy.sh").read_text()
    assert 'if [ "${SKIP_BACKUP:-false}" = "true" ]; then' in text
    assert (
        text.index("run_backup")
        < text.index("run_migrations")
        < text.index("rebuild_search_indexes")
        < text.index("start_services")
    )
    assert 'git -C "$DEPLOY_DIR" rev-parse --short HEAD' in text


# --- backup / restore continuity metrics ---


def _run_continuity_finalizer(
    tmp_path: Path, script_name: str, *, status: int, curl_fails: bool = False
) -> tuple[subprocess.CompletedProcess[str], dict[str, float], list[str]]:
    source = (DEPLOY / f"backup/{script_name}").read_text()
    marker = (
        "apply_daily_retention() {" if script_name == "backup.sh" else "backup_dir="
    )
    harness = tmp_path / f"{script_name}.finalizer.sh"
    harness.write_text(source.split(marker, maxsplit=1)[0] + f"exit {status}\n")
    harness.chmod(0o755)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "date",
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *%Y%m%dT%H%M%SZ*) echo 20260101T000000Z ;;\n"
        '  *) if [ ! -e "$DATE_STATE" ]; then touch "$DATE_STATE"; echo 100; else echo 160; fi ;;\n'  # noqa: E501
        "esac\n",
    )
    _write_executable(
        fake_bin / "curl",
        '#!/bin/sh\ncat >"$METRIC_CAPTURE"\nprintf \'%s\\n\' "$*" >>"$CURL_ARGS_CAPTURE"\ntest "$CURL_FAILS" != true\n',  # noqa: E501
    )
    metric_capture = tmp_path / "metrics"
    curl_args_capture = tmp_path / "curl-args"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "DATE_STATE": str(tmp_path / "date-state"),
        "METRIC_CAPTURE": str(metric_capture),
        "CURL_ARGS_CAPTURE": str(curl_args_capture),
        "CURL_FAILS": "true" if curl_fails else "false",
        "PUSHGATEWAY_URL": "http://pushgateway:9091",
        "BACKUP_ROOT": str(tmp_path / "backups"),
        "BACKUP_SHARE": str(tmp_path / "share"),
    }
    result = subprocess.run(
        [str(harness)], env=env, text=True, capture_output=True, check=False, timeout=8
    )
    metric_lines = (
        metric_capture.read_text().splitlines() if metric_capture.exists() else []
    )
    metrics = {
        name: float(value)
        for name, value in (line.split(maxsplit=1) for line in metric_lines)
    }
    curl_args = (
        curl_args_capture.read_text().splitlines() if curl_args_capture.exists() else []
    )
    return result, metrics, curl_args


@pytest.mark.parametrize(
    ("script_name", "prefix", "job"),
    [
        ("backup.sh", "backup", "forge_backup"),
        ("restore-verify.sh", "restore_verification", "forge_restore_verification"),
    ],
)
@pytest.mark.parametrize("status", [0, 3])
def test_continuity_finalizer_reports_attempt_metrics_to_forge_jobs(
    tmp_path: Path, script_name: str, prefix: str, job: str, status: int
) -> None:
    result, metrics, curl_args = _run_continuity_finalizer(
        tmp_path, script_name, status=status
    )
    assert result.returncode == status
    assert metrics == {
        f"{prefix}_last_attempt_timestamp_seconds": 160.0,
        f"{prefix}_last_attempt_success": 1.0 if status == 0 else 0.0,
        f"{prefix}_last_duration_seconds": 60.0,
    }
    assert curl_args == [
        f"--fail --silent --show-error --connect-timeout 2 --max-time 5 --data-binary @- http://pushgateway:9091/metrics/job/{job}"  # noqa: E501
    ]


def test_continuity_curl_failure_never_changes_primary_status(tmp_path: Path) -> None:
    result, _metrics, _args = _run_continuity_finalizer(
        tmp_path, "backup.sh", status=0, curl_fails=True
    )
    assert result.returncode == 0
    assert "backup metric push failed" in result.stderr


def test_backup_verifies_dump_before_retention_and_only_dumps_the_database() -> None:
    text = (DEPLOY / "backup/backup.sh").read_text()
    assert "pg_restore --list" in text
    assert text.index("pg_restore --list") < text.index("apply_retention")
    assert "sha256sum database.dump manifest.txt >SHA256SUMS" in text
    assert "files.tar" not in text and "templates.tar" not in text
    assert "rsync --archive --partial" in text
    assert set(re.findall(r"\b(backup_[a-z_]+(?:seconds|success|bytes))\b", text)) == {
        "backup_last_attempt_timestamp_seconds",
        "backup_last_attempt_success",
        "backup_last_duration_seconds",
        "backup_last_success_timestamp_seconds",
        "backup_size_bytes",
        "backup_transfer_last_failure_timestamp_seconds",
        "backup_transfer_last_success_timestamp_seconds",
    }


def test_restore_verify_checks_sums_restores_and_runs_django_checks() -> None:
    text = (DEPLOY / "backup/restore-verify.sh").read_text()
    assert "sha256sum -c SHA256SUMS" in text
    assert "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" in text
    assert "pg_restore" in text and "--no-owner" in text
    assert "python manage.py check\npython manage.py showmigrations --plan\n" in text
    assert "--settings=" not in text
    assert "tar " not in text


def test_restore_postgres_requires_confirmation_and_prints_usage(
    tmp_path: Path,
) -> None:
    env = {
        **os.environ,
        "ENV_FILE": str(tmp_path / "none.env"),
        "DATA_ROOT": str(tmp_path),
        "BACKUP_SHARE": str(tmp_path),
        "POSTGRES_DB": "forge",
        "POSTGRES_USER": "forge",
        "DEPLOY_GROUP": _deployment_group(),
    }
    refused = subprocess.run(
        [str(SCRIPTS / "restore-postgres.sh"), str(tmp_path)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert refused.returncode != 0
    assert "restore requires CONFIRM_RESTORE_POSTGRES=true" in refused.stderr
    usage = subprocess.run(
        [str(SCRIPTS / "restore-postgres.sh"), "--help"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert usage.returncode == 0
    assert "CONFIRM_RESTORE_POSTGRES=true" in usage.stderr


# --- ops helpers ---


def _service_sets(script: str) -> list[set[str]]:
    text = (SCRIPTS / script).read_text().replace("\\\n", " ")
    return [
        set(match.split())
        for match in re.findall(r"up -d[^\n]*?--no-build\s+([^\n]+)", text)
    ]


def test_start_helpers_use_exact_forge_service_sets_without_one_shots() -> None:
    ops = _service_sets("start-ops.sh")
    assert ops[0] == {
        "prometheus",
        "alertmanager",
        "grafana",
        "loki",
        "alloy",
        "blackbox-exporter",
    }
    assert ops[1] == {
        "prometheus",
        "alertmanager",
        "grafana",
        "loki",
        "alloy",
        "node-exporter",
        "pgbouncer-exporter",
        "blackbox-exporter",
        "postgres-exporter",
        "redis-exporter",
        "celery-exporter",
        "nginx-exporter",
        "pushgateway",
        "pgadmin",
    }
    everything = _service_sets("start-all.sh")
    assert everything[1] == {"postgres", "pgbouncer", "redis", "meilisearch"}
    assert everything[2] == ops[1] | {"web", "celery-worker", "celery-beat", "nginx"}
    for script in ("start-ops.sh", "start-all.sh"):
        text = (SCRIPTS / script).read_text()
        assert text.startswith("#!/bin/sh\nset -eu\n")
        for one_shot in ("search-index", "backup", "restore-verify", "django-migrate"):
            assert one_shot not in text
        assert "render-observability-config.sh" in text
        assert "validate-observability-config.sh" in text
        assert "--force-recreate --no-deps --no-build" in text


def test_native_observability_validator_runs_exact_checks_in_order() -> None:
    text = (SCRIPTS / "validate-observability-config.sh").read_text()
    order = [
        "promtool",
        "amtool",
        "loki -verify-config",
        "alloy validate",
        "blackbox-exporter --config.file",
    ]
    positions = [text.index(item) for item in order]
    assert positions == sorted(positions)
    assert "--profile observability run --rm --no-deps" in text


def test_alert_notification_test_requires_confirmation_and_uses_forge_names(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [str(SCRIPTS / "send-test-alert.sh")],
        env={**os.environ, "ENV_FILE": str(tmp_path / "none")},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "CONFIRM_ALERT_NOTIFICATION_TEST=true" in result.stderr
    text = (SCRIPTS / "send-test-alert.sh").read_text()
    assert text.count('"alertname":"ForgeNotificationTest"') == 2
    assert "/run/secrets" not in text and "secrets/" not in text
