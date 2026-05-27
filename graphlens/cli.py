"""GraphLens command line interface."""

from __future__ import annotations

import json
import logging
import shutil
import gc
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

import click

from graphlens.analysis.communities import CommunityDetector
from graphlens.analysis.risk import health_score
from graphlens.benchmark import format_benchmark, run_benchmark
from graphlens.doctor import doctor_json, format_doctor, run_doctor
from graphlens.graph.builder import GraphBuilder
from graphlens.graph.diff import compare
from graphlens.graph.snapshot import export_snapshot
from graphlens.graph.tokens import TokenCounter
from graphlens.viz.server import serve as serve_viz

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn
except ImportError:  # pragma: no cover - exercised only in minimal envs
    class Console:
        def print(self, value: object) -> None:
            print(value)

    class Progress:
        def __init__(self, *_: object) -> None:
            pass

        def __enter__(self) -> "Progress":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def add_task(self, *_: object, **__: object) -> None:
            return None

    def SpinnerColumn() -> object:
        return object()

    def TextColumn(_: str) -> object:
        return object()


console = Console()


def setup_logging() -> None:
    """Configure rotating file logs."""

    log_dir = Path(".graphlens")
    log_dir.mkdir(exist_ok=True)
    handler = RotatingFileHandler(log_dir / "graphlens.log", maxBytes=10_000_000, backupCount=3)
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(name)s %(message)s")


def release_graphlens_handles() -> None:
    """Close GraphLens log handlers before deleting local state."""

    target = str(Path(".graphlens").resolve())
    for logger_name in ["", "graphlens.mcp"]:
        logger = logging.getLogger(logger_name)
        for handler in list(logger.handlers):
            filename = getattr(handler, "baseFilename", "")
            if filename and str(Path(filename).resolve()).startswith(target):
                logger.removeHandler(handler)
                handler.close()


def repo_root_from_config(default: str = ".") -> str:
    """Return the repo root recorded by the last build."""

    config = Path(".graphlens/config.json")
    if not config.exists():
        return default
    try:
        return str(json.loads(config.read_text(encoding="utf-8")).get("repo_root") or default)
    except (OSError, json.JSONDecodeError):
        return default


@click.group()
def main() -> None:
    """GraphLens code graph MCP server."""

    setup_logging()


@main.command()
def install() -> None:
    """Configure local AI tools to use GraphLens MCP."""

    config = {"mcpServers": {"graphlens": {"command": "graphlens", "args": ["serve"]}}}
    for folder, label in [(".claude", "Claude Code"), (".cursor", "Cursor")]:
        target = Path(folder) / "mcp.json"
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(config, indent=2), encoding="utf-8")
        console.print(f"Configured {label}: {target}")


@main.command()
@click.argument("repo", default=".")
def build(repo: str) -> None:
    """Parse a repository and build the graph."""

    builder = GraphBuilder(repo)
    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}")) as progress:
            progress.add_task("Building graph...", total=None)
            report = builder.build()
        CommunityDetector(builder.storage).detect(builder.to_networkx())
        console.print(f"Parsed {report.parsed}, skipped {report.skipped}, errors {report.errors}")
    finally:
        builder.storage.close()


@main.command()
@click.argument("repo", default=".")
def rebuild(repo: str) -> None:
    """Clean local graph data and build from scratch."""

    graph_dir = Path(".graphlens")
    release_graphlens_handles()
    gc.collect()
    if graph_dir.exists():
        shutil.rmtree(graph_dir)
    build.callback(repo)  # type: ignore[attr-defined]


@main.command()
def serve() -> None:
    """Start stdio MCP server."""

    from graphlens.mcp.server import main as serve_mcp

    serve_mcp()


@main.command()
@click.argument("repo", default=".")
def watch(repo: str) -> None:
    """Watch repository for incremental updates."""

    from graphlens.watch.watcher import watch as watch_repo

    watch_repo(repo)


@main.command()
def stats() -> None:
    """Print graph statistics and token estimate."""

    repo_root = repo_root_from_config(".")
    builder = GraphBuilder(repo_root)
    try:
        summary = builder.storage.summary()
        graph = builder.to_networkx()
        files = [row["path"] for row in builder.storage.rows("SELECT path FROM files WHERE path NOT LIKE '<external>/%'")]
        total_tokens = TokenCounter().count_files(repo_root, files)
        focused_tokens = TokenCounter().count_files(repo_root, files[: min(len(files), 20)])
        saved = max(0, total_tokens - focused_tokens)
        console.print({**summary, "health_score": health_score(graph), "total_tokens": total_tokens, "token_efficiency_estimate": f"{saved} saved"})
    finally:
        builder.storage.close()


@main.command()
@click.argument("repo", default=".")
@click.option("--json", "as_json", is_flag=True, help="Print machine-readable JSON.")
@click.option("--json-output", "as_json", is_flag=True, help="Print machine-readable JSON.")
def doctor(repo: str, as_json: bool) -> None:
    """Check whether GraphLens is installed and healthy."""

    report = run_doctor(repo)
    console.print(doctor_json(report) if as_json else format_doctor(report))


@main.command()
@click.argument("repo", default=".")
@click.option("--context-files", default=20, show_default=True, help="Files used for selected-context estimate.")
@click.option("--json", "as_json", is_flag=True, help="Print machine-readable JSON.")
@click.option("--json-output", "as_json", is_flag=True, help="Print machine-readable JSON.")
def benchmark(repo: str, context_files: int, as_json: bool) -> None:
    """Measure parse speed and token savings."""

    result = run_benchmark(repo, context_files)
    console.print(json.dumps(result.to_dict(), indent=2) if as_json else format_benchmark(result))


@main.command()
@click.option("--open-browser/--no-open-browser", default=True)
def viz(open_browser: bool) -> None:
    """Start local graph visualization."""

    url = "http://127.0.0.1:7341"
    console.print(f"Serving visualization at {url}")
    if open_browser:
        webbrowser.open(url)
    serve_viz(7341)


@main.command()
@click.option("--out", default=".graphlens/snapshot.json", show_default=True)
def snapshot(out: str) -> None:
    """Export graph snapshot JSON."""

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    payload = export_snapshot(out=out)
    console.print(f"Wrote {out} with {len(payload['nodes'])} nodes and {len(payload['links'])} edges")


@main.command()
@click.option("--yes", is_flag=True, help="Skip confirmation.")
def clean(yes: bool) -> None:
    """Remove local GraphLens database and logs."""

    target = Path(".graphlens")
    release_graphlens_handles()
    gc.collect()
    if not target.exists():
        console.print("No .graphlens directory to clean")
        return
    if not yes and not click.confirm("Remove .graphlens local graph data?"):
        console.print("Clean cancelled")
        return
    shutil.rmtree(target)
    console.print("Removed .graphlens")


@main.command()
@click.option("--before", required=True)
@click.option("--after", required=True)
def diff(before: str, after: str) -> None:
    """Compare graph snapshot files."""

    before_data = json.loads(Path(before).read_text(encoding="utf-8"))
    after_data = json.loads(Path(after).read_text(encoding="utf-8"))
    console.print(compare(before_data, after_data).__dict__)
