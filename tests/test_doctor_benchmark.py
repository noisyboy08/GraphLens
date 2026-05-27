from pathlib import Path

from graphlens.benchmark import run_benchmark
from graphlens.doctor import run_doctor
from graphlens.graph.builder import GraphBuilder


def test_doctor_reports_graph_contents(tmp_path: Path) -> None:
    db = tmp_path / "graph.db"
    builder = GraphBuilder("tests/fixtures/sample_python", db)
    builder.build()
    builder.storage.close()
    report = run_doctor("tests/fixtures/sample_python", db)
    names = {check.name for check in report.checks}
    assert "Graph contents" in names
    assert report.status in {"ok", "warn"}


def test_benchmark_runs_on_fixture() -> None:
    result = run_benchmark("tests/fixtures/sample_python", context_files=1)
    assert result.files_scanned >= 3
    assert result.files_parsed >= 3
    assert result.seconds > 0
