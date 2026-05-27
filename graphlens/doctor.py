"""Environment and project health checks."""

from __future__ import annotations

import importlib
import json
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from graphlens.graph.storage import GraphStorage


@dataclass(frozen=True)
class DoctorCheck:
    """One doctor check result."""

    name: str
    status: str
    message: str


@dataclass(frozen=True)
class DoctorReport:
    """Doctor command report."""

    status: str
    checks: list[DoctorCheck]

    def to_dict(self) -> dict[str, object]:
        """Return JSON-serializable report."""

        return {"status": self.status, "checks": [check.__dict__ for check in self.checks]}


def run_doctor(repo_path: str | Path = ".", db_path: str | Path = ".graphlens/graph.db") -> DoctorReport:
    """Run health checks for a GraphLens workspace."""

    repo = Path(repo_path)
    db = Path(db_path)
    checks = [
        _python_check(),
        _dependency_check("click"),
        _dependency_check("networkx"),
        _dependency_check("watchdog"),
        _dependency_check("mcp"),
        _path_check(repo, "repository"),
        _path_check(Path("frontend/index.html"), "visualization frontend"),
        _path_check(Path(".graphlens"), "GraphLens state directory", warn=True),
        _path_check(db, "SQLite graph database", warn=True),
        _graph_check(db),
        _config_check(),
        _mcp_config_check(".claude/mcp.json", "Claude Code MCP config"),
        _mcp_config_check(".cursor/mcp.json", "Cursor MCP config"),
    ]
    status = "fail" if any(c.status == "fail" for c in checks) else "warn" if any(c.status == "warn" for c in checks) else "ok"
    return DoctorReport(status, checks)


def format_doctor(report: DoctorReport) -> str:
    """Return a readable doctor report."""

    lines = [f"GraphLens doctor: {report.status.upper()}"]
    for check in report.checks:
        lines.append(f"[{check.status.upper()}] {check.name}: {check.message}")
    return "\n".join(lines)


def doctor_json(report: DoctorReport) -> str:
    """Return report as pretty JSON."""

    return json.dumps(report.to_dict(), indent=2)


def _python_check() -> DoctorCheck:
    version = sys.version_info
    ok = version >= (3, 11)
    message = f"Python {platform.python_version()}"
    return DoctorCheck("Python version", "ok" if ok else "fail", message)


def _dependency_check(module: str) -> DoctorCheck:
    try:
        importlib.import_module(module)
        return DoctorCheck(f"Dependency {module}", "ok", "installed")
    except ImportError:
        return DoctorCheck(f"Dependency {module}", "warn", "not installed")


def _path_check(path: Path, name: str, warn: bool = False) -> DoctorCheck:
    if path.exists():
        return DoctorCheck(name, "ok", str(path))
    return DoctorCheck(name, "warn" if warn else "fail", f"missing: {path}")


def _graph_check(db: Path) -> DoctorCheck:
    if not db.exists():
        return DoctorCheck("Graph contents", "warn", "run `graphlens build .`")
    storage = GraphStorage(db)
    try:
        summary = storage.summary()
    finally:
        storage.close()
    if summary["total_files"] == 0:
        return DoctorCheck("Graph contents", "warn", "database exists but has no files")
    msg = f"{summary['total_files']} files, {summary['total_functions']} functions, {summary['total_edges']} edges"
    return DoctorCheck("Graph contents", "ok", msg)


def _config_check() -> DoctorCheck:
    config = Path(".graphlens/config.json")
    if not config.exists():
        return DoctorCheck("Repo metadata", "warn", "missing .graphlens/config.json")
    try:
        repo = json.loads(config.read_text(encoding="utf-8")).get("repo_root")
    except (OSError, json.JSONDecodeError):
        return DoctorCheck("Repo metadata", "warn", "invalid config JSON")
    return DoctorCheck("Repo metadata", "ok", f"repo_root={repo}")


def _mcp_config_check(path: str, name: str) -> DoctorCheck:
    target = Path(path)
    if not target.exists():
        return DoctorCheck(name, "warn", "run `graphlens install`")
    return DoctorCheck(name, "ok", str(target))
