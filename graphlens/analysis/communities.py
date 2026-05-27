"""Community detection."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx

from graphlens.graph.storage import GraphStorage


class CommunityDetector:
    """Detect and persist graph communities."""

    def __init__(self, storage: GraphStorage | None = None) -> None:
        self.storage = storage or GraphStorage()

    def detect(self, graph: nx.DiGraph) -> dict[int, int]:
        """Detect communities, preferring Leiden when available."""

        communities = self._leiden(graph) or self._louvain(graph)
        self._store(communities, graph)
        return communities

    def get_community_for_file(self, path: str) -> dict[str, object] | None:
        """Return community metadata for a file."""

        rows = self.storage.rows(
            """
            SELECT communities.community_id, communities.label
            FROM communities
            JOIN nodes ON nodes.id=communities.node_id
            JOIN files ON files.id=nodes.file_id
            WHERE files.path=? LIMIT 1
            """,
            (path,),
        )
        if not rows:
            return None
        cid = rows[0]["community_id"]
        return {"community_id": cid, "label": rows[0]["label"], "files": self.get_files_in_community(cid)}

    def get_files_in_community(self, community_id: int) -> list[str]:
        """Return all files in a community."""

        rows = self.storage.rows(
            """
            SELECT DISTINCT files.path FROM communities
            JOIN nodes ON nodes.id=communities.node_id
            JOIN files ON files.id=nodes.file_id
            WHERE communities.community_id=?
            """,
            (community_id,),
        )
        return sorted(r["path"] for r in rows)

    def _leiden(self, graph: nx.DiGraph) -> dict[int, int] | None:
        try:
            import igraph as ig
            import leidenalg
        except Exception:
            return None
        nodes = list(graph.nodes())
        idx = {node: i for i, node in enumerate(nodes)}
        edges = [(idx[u], idx[v]) for u, v in graph.to_undirected().edges()]
        part = leidenalg.find_partition(ig.Graph(len(nodes), edges), leidenalg.ModularityVertexPartition)
        return {nodes[i]: cid for cid, members in enumerate(part) for i in members}

    def _louvain(self, graph: nx.DiGraph) -> dict[int, int]:
        undirected = graph.to_undirected()
        sets = nx.community.louvain_communities(undirected, seed=7) if undirected.nodes else []
        return {node: cid for cid, members in enumerate(sets) for node in members}

    def _store(self, communities: dict[int, int], graph: nx.DiGraph) -> None:
        grouped: dict[int, list[int]] = defaultdict(list)
        for node, cid in communities.items():
            grouped[cid].append(node)
        labels = {cid: self._label(nodes, graph) for cid, nodes in grouped.items()}
        with self.storage.conn:
            self.storage.conn.execute("DELETE FROM communities")
            for node, cid in communities.items():
                self.storage.conn.execute(
                    "INSERT INTO communities(node_id, community_id, label) VALUES(?,?,?)",
                    (node, cid, labels[cid]),
                )

    def _label(self, nodes: list[int], graph: nx.DiGraph) -> str:
        prefixes = [Path(str(graph.nodes[n].get("file", ""))).parts[0] for n in nodes if graph.nodes[n].get("file")]
        return Counter(prefixes).most_common(1)[0][0] if prefixes else "root"


def detect(graph: nx.DiGraph) -> dict[int, int]:
    """Convenience community detection function."""

    return CommunityDetector().detect(graph)
