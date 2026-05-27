from pathlib import Path

from graphlens.analysis.blast_radius import BlastRadiusAnalyzer
from graphlens.graph.builder import GraphBuilder
from graphlens.graph.traversal import GraphTraversal


def test_single_file_change(tmp_path: Path) -> None:
    builder = GraphBuilder("tests/fixtures/sample_python", tmp_path / "graph.db")
    builder.build()
    result = BlastRadiusAnalyzer(GraphTraversal(builder.storage)).analyze(["utils.py"])
    assert result.changed_files == ["utils.py"]
    assert result.total_affected_count >= 0


def test_test_file_detection(tmp_path: Path) -> None:
    builder = GraphBuilder("tests/fixtures/sample_python", tmp_path / "graph.db")
    builder.build()
    result = BlastRadiusAnalyzer(GraphTraversal(builder.storage)).analyze(["app.py"])
    assert "test_app.py" in result.related_tests


def test_impact_scoring(tmp_path: Path) -> None:
    builder = GraphBuilder("tests/fixtures/sample_python", tmp_path / "graph.db")
    builder.build()
    result = BlastRadiusAnalyzer(GraphTraversal(builder.storage)).analyze(["app.py"])
    assert all(0.0 <= item.impact <= 1.0 for item in result.directly_affected + result.transitively_affected)
