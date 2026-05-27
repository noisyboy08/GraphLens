from pathlib import Path

import pytest

from graphlens.graph.builder import GraphBuilder
from graphlens.mcp.server import GraphLensService, GraphLensToolError


def test_mcp_service_summary_and_search(tmp_path: Path) -> None:
    db = tmp_path / "graph.db"
    builder = GraphBuilder("tests/fixtures/sample_python", db)
    builder.build()
    service = GraphLensService("tests/fixtures/sample_python", db)
    summary = service.get_graph_summary()
    results = service.search_codebase("main")
    assert summary["total_files"] >= 3
    assert results["results"]


def test_mcp_service_relevant_files_uses_tokens(tmp_path: Path) -> None:
    db = tmp_path / "graph.db"
    builder = GraphBuilder("tests/fixtures/sample_python", db)
    builder.build()
    service = GraphLensService("tests/fixtures/sample_python", db)
    result = service.get_relevant_files("app.py", depth=2, token_budget=50000)
    assert "files" in result
    assert result["tokens_saved"] >= 0


def test_mcp_service_validation(tmp_path: Path) -> None:
    service = GraphLensService("tests/fixtures/sample_python", tmp_path / "graph.db")
    with pytest.raises(GraphLensToolError):
        service.search_codebase("", 10)
