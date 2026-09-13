from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path

from dashboard_specs import DASHBOARDS
from dashboardlib import Dashboard, dashboard_json

SCRIPT_DIR = Path(__file__).resolve().parent
DASHBOARD_ROOT = SCRIPT_DIR.parent / "dashboards"
FOLDER_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
UID_COMPONENT = re.compile(r"forge-[A-Za-z0-9][A-Za-z0-9_-]*")


class UnsafeDashboardPath(ValueError):
    pass


def _component(value: str, *, name: str, pattern: re.Pattern[str]) -> str:
    if not pattern.fullmatch(value):
        raise ValueError(f"Invalid dashboard {name}: {value!r}")
    return value


def _output_path(root: Path, *, folder: str, uid: str) -> Path:
    folder = _component(folder, name="folder", pattern=FOLDER_COMPONENT)
    uid = _component(uid, name="uid", pattern=UID_COMPONENT)
    path = root / folder / f"{uid}.json"
    root_resolved = root.resolve()
    if not path.resolve().is_relative_to(root_resolved):
        raise ValueError(f"Dashboard output is outside dashboard root: {path}")
    current = root
    for component in path.relative_to(root).parts:
        current /= component
        if current.is_symlink():
            raise UnsafeDashboardPath(
                f"Dashboard output contains symlinked path component: {current}"
            )
    return path


def rendered(
    *,
    dashboard_root: Path | None = None,
    dashboards: Iterable[Dashboard] | None = None,
) -> dict[Path, str]:
    root = DASHBOARD_ROOT if dashboard_root is None else dashboard_root
    specs = DASHBOARDS if dashboards is None else dashboards
    result: dict[Path, str] = {}
    seen_uids: set[str] = set()
    normalized_paths: set[str] = set()
    for spec in specs:
        if spec.uid in seen_uids:
            raise ValueError(f"Duplicate dashboard UID: {spec.uid}")
        seen_uids.add(spec.uid)
        path = _output_path(root, folder=spec.folder, uid=spec.uid)
        normalized_path = (
            path.resolve().relative_to(root.resolve()).as_posix().casefold()
        )
        if normalized_path in normalized_paths:
            raise ValueError(f"Duplicate normalized dashboard path: {path}")
        normalized_paths.add(normalized_path)
        result[path] = (
            json.dumps(
                dashboard_json(spec),
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    return result


def _owned(path: Path) -> bool:
    return path.name.startswith("forge-") and path.suffix == ".json"


def _write_content(root: Path, path: Path, content: str) -> None:
    folder, filename = path.relative_to(root).parts
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = os.open(root, directory_flags)
    try:
        try:
            os.mkdir(folder, dir_fd=root_fd)
        except FileExistsError:
            pass
        folder_fd = os.open(folder, directory_flags, dir_fd=root_fd)
        try:
            file_fd = os.open(
                filename,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
                0o644,
                dir_fd=folder_fd,
            )
            with os.fdopen(file_fd, "w", encoding="utf-8") as output:
                output.write(content)
        finally:
            os.close(folder_fd)
    finally:
        os.close(root_fd)


def run(
    *,
    check: bool,
    dashboard_root: Path | None = None,
    dashboards: Iterable[Dashboard] | None = None,
) -> int:
    root = DASHBOARD_ROOT if dashboard_root is None else dashboard_root
    try:
        expected = rendered(dashboard_root=root, dashboards=dashboards)
    except UnsafeDashboardPath as error:
        print(error)
        return 1
    existing = set(root.rglob("*.json"))
    unexpected = existing - set(expected)
    unexpected_owned = {path for path in unexpected if _owned(path)}
    unexpected_nonowned = unexpected - unexpected_owned

    if check:
        stale = [
            path
            for path, content in expected.items()
            if not path.exists() or path.read_text(encoding="utf-8") != content
        ]
        for path in sorted(set(stale) | unexpected):
            print(path.relative_to(root))
        return 1 if stale or unexpected else 0

    for path in sorted(unexpected_owned):
        path.unlink()
    for path, content in expected.items():
        try:
            _write_content(root, path, content)
        except OSError as error:
            print(f"Refusing unsafe dashboard write: {path}: {error}")
            return 1
    for path in sorted(unexpected_nonowned):
        print(path.relative_to(root))
    return 1 if unexpected_nonowned else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    return run(check=args.check)


if __name__ == "__main__":
    sys.exit(main())
