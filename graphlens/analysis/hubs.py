"""Hub, bridge, and bottleneck detection."""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx


@dataclass(frozen=True)
class HubNode:
    """Important high-connectivity node."""

    name: str
    file: str
    in_degree: int
    out_degree: int
    pagerank_score: float
    risk_level: str


@dataclass(frozen=True)
class BridgeEdge:
    """Critical graph bridge edge."""

    source: str
    target: str
    criticality_score: float


def detect_hubs(graph: nx.DiGraph) -> list[HubNode]:
    """Detect top central nodes using PageRank and degree centrality."""

    if not graph.nodes:
        return []
    pr = nx.pagerank(graph)
    count = max(1, int(len(graph.nodes) * 0.05))
    ranked = sorted(graph.nodes, key=lambda n: pr.get(n, 0) + graph.degree(n), reverse=True)[:count]
    return [_hub(graph, node, pr[node]) for node in ranked]


def detect_bridges(graph: nx.DiGraph) -> list[BridgeEdge]:
    """Detect edges whose removal disconnects the undirected graph."""

    undirected = graph.to_undirected()
    bridges = list(nx.bridges(undirected)) if undirected.number_of_nodes() else []
    return [BridgeEdge(_name(graph, u), _name(graph, v), 1.0) for u, v in bridges]


def detect_bottlenecks(graph: nx.DiGraph) -> list[str]:
    """Return high betweenness centrality chokepoints."""

    if not graph.nodes:
        return []
    centrality = nx.betweenness_centrality(graph)
    values = sorted(centrality.values(), reverse=True)
    threshold = values[max(0, int(len(values) * 0.05) - 1)] if values else 0
    return [_name(graph, n) for n, score in centrality.items() if score >= threshold and score > 0]


def _hub(graph: nx.DiGraph, node: int, pagerank: float) -> HubNode:
    degree = graph.degree(node)
    risk = "high" if degree > 20 else "medium" if degree > 8 else "low"
    return HubNode(_name(graph, node), graph.nodes[node].get("file", ""), graph.in_degree(node), graph.out_degree(node), pagerank, risk)


def _name(graph: nx.Graph, node: int) -> str:
    data = graph.nodes[node]
    return f"{data.get('file', '')}:{data.get('name', node)}"
