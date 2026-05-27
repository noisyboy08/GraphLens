"""Graph snapshot diffing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GraphDiff:
    """Simple graph diff summary."""

    added_nodes: int
    removed_nodes: int
    added_edges: int
    removed_edges: int


def compare(before: dict, after: dict) -> GraphDiff:
    """Compare two visualization-style graph snapshots."""

    before_nodes = {n["id"] for n in before.get("nodes", [])}
    after_nodes = {n["id"] for n in after.get("nodes", [])}
    before_edges = {(e["source"], e["target"], e.get("type")) for e in before.get("links", [])}
    after_edges = {(e["source"], e["target"], e.get("type")) for e in after.get("links", [])}
    return GraphDiff(
        added_nodes=len(after_nodes - before_nodes),
        removed_nodes=len(before_nodes - after_nodes),
        added_edges=len(after_edges - before_edges),
        removed_edges=len(before_edges - after_edges),
    )
