"""Graph traversal queries."""

from __future__ import annotations

from collections import Counter, deque
from pathlib import Path

from .storage import GraphStorage


class GraphTraversal:
    """Query dependency context from SQLite graph rows."""

    def __init__(self, storage: GraphStorage | None = None) -> None:
        self.storage = storage or GraphStorage()

    def get_context_for_file(self, path: str, depth: int = 2, token_budget: int = 50000) -> list[str]:
        """Return relevant file paths within BFS depth sorted by score."""

        file_row = self.storage.get_file_by_path(self._norm(path))
        if file_row is None:
            return []
        start = [row["id"] for row in self.storage.get_nodes_by_file(file_row["id"])]
        seen = set(start)
        queue = deque((node, 0) for node in start)
        scores: Counter[str] = Counter()
        while queue:
            node, dist = queue.popleft()
            if dist >= depth:
                continue
            for edge in self.storage.get_edges_by_node(node):
                nxt = edge["target_node_id"] if edge["source_node_id"] == node else edge["source_node_id"]
                if nxt in seen:
                    continue
                seen.add(nxt)
                row = self._node_file(nxt)
                if row:
                    scores[row["path"]] += max(1, depth - dist)
                queue.append((nxt, dist + 1))
        max_files = max(1, token_budget // 1500)
        return [p for p, _ in scores.most_common(max_files) if not p.startswith("<external>")]

    def get_callers(self, function_name: str) -> list[dict[str, object]]:
        """Return all functions that call a function."""

        return self._call_query(function_name, incoming=True)

    def get_callees(self, function_name: str) -> list[dict[str, object]]:
        """Return all functions called by a function."""

        return self._call_query(function_name, incoming=False)

    def get_imports_of(self, file_path: str) -> list[str]:
        """Return files imported by a file."""

        return self._dependency_query(file_path, outgoing=True)

    def get_dependents(self, file_path: str) -> list[str]:
        """Return files importing a file."""

        return self._dependency_query(file_path, outgoing=False)

    def _call_query(self, function_name: str, incoming: bool) -> list[dict[str, object]]:
        side = "tgt" if incoming else "src"
        other = "src" if incoming else "tgt"
        rows = self.storage.rows(
            f"""
            SELECT {other}.name, {other}.line_start, files.path
            FROM edges
            JOIN nodes src ON src.id = edges.source_node_id
            JOIN nodes tgt ON tgt.id = edges.target_node_id
            JOIN files ON files.id = {other}.file_id
            WHERE edges.edge_type='calls' AND {side}.name=?
            """,
            (function_name,),
        )
        return [{"name": r["name"], "file_path": r["path"], "line": r["line_start"]} for r in rows]

    def _dependency_query(self, file_path: str, outgoing: bool) -> list[str]:
        file_row = self.storage.get_file_by_path(self._norm(file_path))
        if not file_row:
            return []
        nodes = [row["id"] for row in self.storage.get_nodes_by_file(file_row["id"])]
        paths: set[str] = set()
        for node in nodes:
            for edge in self.storage.get_edges_by_node(node):
                if edge["edge_type"] != "imports":
                    continue
                include = edge["source_node_id"] == node if outgoing else edge["target_node_id"] == node
                if include:
                    other = edge["target_node_id"] if outgoing else edge["source_node_id"]
                    row = self._node_file(other)
                    if row and row["path"] != file_row["path"]:
                        paths.add(row["path"])
        return sorted(paths)

    def _node_file(self, node_id: int):
        rows = self.storage.rows(
            "SELECT files.path FROM nodes JOIN files ON files.id=nodes.file_id WHERE nodes.id=?",
            (node_id,),
        )
        return rows[0] if rows else None

    def _norm(self, path: str) -> str:
        return str(Path(path)).replace("\\", "/")
