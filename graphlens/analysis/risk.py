"""Graph health scoring."""

from __future__ import annotations

import networkx as nx


def health_score(graph: nx.DiGraph) -> float:
    """Estimate graph health from density and connectivity."""

    if graph.number_of_nodes() == 0:
        return 1.0
    density_penalty = min(0.5, nx.density(graph))
    isolate_penalty = len(list(nx.isolates(graph))) / max(1, graph.number_of_nodes()) * 0.3
    return round(max(0.0, 1.0 - density_penalty - isolate_penalty), 3)
