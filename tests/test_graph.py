from pathlib import Path

from graphlens.graph.builder import GraphBuilder
from graphlens.graph.diff import compare
from graphlens.graph.snapshot import export_snapshot
from graphlens.graph.storage import GraphStorage
from graphlens.graph.traversal import GraphTraversal


def test_node_and_edge_insertion(tmp_path: Path) -> None:
    storage = GraphStorage(tmp_path / "graph.db")
    file_id = storage.upsert_file("a.py", "sha", "python")
    a = storage.upsert_node(file_id, "function", "a", 1, 2)
    b = storage.upsert_node(file_id, "function", "b", 3, 4)
    edge = storage.upsert_edge(a, b, "calls")
    assert edge > 0
    assert len(storage.get_edges_by_node(a)) == 1


def test_bfs_traversal_depth(tmp_path: Path) -> None:
    builder = GraphBuilder("tests/fixtures/sample_python", tmp_path / "graph.db")
    builder.build()
    traversal = GraphTraversal(builder.storage)
    context = traversal.get_context_for_file("app.py", depth=2)
    assert isinstance(context, list)


def test_builder_creates_graph(tmp_path: Path) -> None:
    builder = GraphBuilder("tests/fixtures/sample_python", tmp_path / "graph.db")
    report = builder.build()
    graph = builder.to_networkx()
    assert report.parsed >= 3
    assert graph.number_of_nodes() > 0


def test_import_resolution_links_local_files(tmp_path: Path) -> None:
    builder = GraphBuilder("tests/fixtures/sample_python", tmp_path / "graph.db")
    builder.build()
    traversal = GraphTraversal(builder.storage)
    assert "utils.py" in traversal.get_imports_of("app.py")
    assert "app.py" in traversal.get_dependents("utils.py")


def test_snapshot_and_diff(tmp_path: Path) -> None:
    builder = GraphBuilder("tests/fixtures/sample_python", tmp_path / "graph.db")
    builder.build()
    before = {"nodes": [], "links": []}
    after = export_snapshot(builder.storage, tmp_path / "snapshot.json")
    diff = compare(before, after)
    assert diff.added_nodes > 0
    assert (tmp_path / "snapshot.json").exists()
