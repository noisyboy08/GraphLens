"""Graph snapshot export."""

from __future__ import annotations

import json
from pathlib import Path

from .storage import GraphStorage


def export_snapshot(storage: GraphStorage | None = None, out: str | Path | None = None) -> dict:
    """Export graph data in visualization-compatible JSON format."""

    owns_storage = storage is None
    storage = storage or GraphStorage()
    nodes = storage.rows(
        """
        SELECT nodes.id, nodes.name, nodes.node_type, nodes.line_start,
               nodes.line_end, files.path, files.language,
               COALESCE(communities.community_id, 0) AS community,
               COALESCE(communities.label, '') AS community_label
        FROM nodes
        JOIN files ON files.id=nodes.file_id
        LEFT JOIN communities ON communities.node_id=nodes.id
        """
    )
    payload = {
        "nodes": [dict(row) for row in nodes],
        "links": [
            {"id": edge["id"], "source": edge["source_node_id"], "target": edge["target_node_id"], "type": edge["edge_type"]}
            for edge in storage.get_all_edges()
        ],
    }
    if out is not None:
        Path(out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if owns_storage:
        storage.close()
    return payload
