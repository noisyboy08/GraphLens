"""SQLite storage for GraphLens."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class GraphStorage:
    """SQLite graph repository with transactional writes."""

    def __init__(self, db_path: str | Path = ".graphlens/graph.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def close(self) -> None:
        """Close the SQLite connection."""

        self.conn.close()

    def upsert_file(self, path: str, sha256: str, language: str) -> int:
        """Insert or update a file row and return its id."""

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO files(path, sha256, language, last_parsed)
                VALUES(?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(path) DO UPDATE SET
                  sha256=excluded.sha256,
                  language=excluded.language,
                  last_parsed=CURRENT_TIMESTAMP
                """,
                (path, sha256, language),
            )
        return int(self.conn.execute("SELECT id FROM files WHERE path=?", (path,)).fetchone()["id"])

    def upsert_node(self, file_id: int, type: str, name: str, line_start: int, line_end: int, docstring: str = "") -> int:
        """Insert a node and return its id."""

        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO nodes(file_id,node_type,name,line_start,line_end,docstring) VALUES(?,?,?,?,?,?)",
                (file_id, type, name, line_start, line_end, docstring),
            )
        return int(cur.lastrowid)

    def upsert_edge(self, source_id: int, target_id: int, edge_type: str) -> int:
        """Insert an edge and return its id."""

        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO edges(source_node_id,target_node_id,edge_type) VALUES(?,?,?)",
                (source_id, target_id, edge_type),
            )
        return int(cur.lastrowid)

    def get_file_by_path(self, path: str) -> sqlite3.Row | None:
        """Return a file row by path."""

        return self.conn.execute("SELECT * FROM files WHERE path=?", (path,)).fetchone()

    def get_nodes_by_file(self, file_id: int) -> list[sqlite3.Row]:
        """Return all nodes belonging to a file."""

        return list(self.conn.execute("SELECT * FROM nodes WHERE file_id=?", (file_id,)))

    def get_edges_by_node(self, node_id: int) -> list[sqlite3.Row]:
        """Return edges touching a node."""

        return list(
            self.conn.execute(
                "SELECT * FROM edges WHERE source_node_id=? OR target_node_id=?",
                (node_id, node_id),
            )
        )

    def get_all_edges(self) -> list[sqlite3.Row]:
        """Return every edge."""

        return list(self.conn.execute("SELECT * FROM edges"))

    def delete_file_nodes(self, file_id: int) -> None:
        """Delete nodes and their edges for a file."""

        node_ids = [row["id"] for row in self.get_nodes_by_file(file_id)]
        if not node_ids:
            return
        marks = ",".join("?" for _ in node_ids)
        with self.conn:
            self.conn.execute(f"DELETE FROM edges WHERE source_node_id IN ({marks}) OR target_node_id IN ({marks})", node_ids * 2)
            self.conn.execute(f"DELETE FROM communities WHERE node_id IN ({marks})", node_ids)
            self.conn.execute(f"DELETE FROM nodes WHERE id IN ({marks})", node_ids)

    def file_needs_update(self, path: str, sha256: str) -> bool:
        """Return true when a path is missing or hash changed."""

        row = self.get_file_by_path(path)
        return row is None or row["sha256"] != sha256

    def search_nodes(self, query: str, limit: int = 10) -> list[sqlite3.Row]:
        """Search symbol names and docstrings."""

        like = f"%{query}%"
        return list(
            self.conn.execute(
                """
                SELECT nodes.*, files.path FROM nodes
                JOIN files ON files.id = nodes.file_id
                WHERE nodes.name LIKE ? OR nodes.docstring LIKE ?
                LIMIT ?
                """,
                (like, like, limit),
            )
        )

    def summary(self) -> dict[str, int]:
        """Return aggregate counts."""

        q = self.conn.execute
        return {
            "total_files": q("SELECT COUNT(*) AS c FROM files").fetchone()["c"],
            "total_functions": q("SELECT COUNT(*) AS c FROM nodes WHERE node_type='function'").fetchone()["c"],
            "total_edges": q("SELECT COUNT(*) AS c FROM edges").fetchone()["c"],
            "communities": q("SELECT COUNT(DISTINCT community_id) AS c FROM communities").fetchone()["c"],
        }

    def rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        """Run a read-only query and return rows."""

        return list(self.conn.execute(sql, params))

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS files (
              id INTEGER PRIMARY KEY,
              path TEXT UNIQUE,
              sha256 TEXT,
              language TEXT,
              last_parsed TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS nodes (
              id INTEGER PRIMARY KEY,
              file_id INTEGER,
              node_type TEXT,
              name TEXT,
              line_start INTEGER,
              line_end INTEGER,
              docstring TEXT,
              FOREIGN KEY (file_id) REFERENCES files(id)
            );
            CREATE TABLE IF NOT EXISTS edges (
              id INTEGER PRIMARY KEY,
              source_node_id INTEGER,
              target_node_id INTEGER,
              edge_type TEXT,
              FOREIGN KEY (source_node_id) REFERENCES nodes(id),
              FOREIGN KEY (target_node_id) REFERENCES nodes(id)
            );
            CREATE TABLE IF NOT EXISTS communities (
              id INTEGER PRIMARY KEY,
              node_id INTEGER,
              community_id INTEGER,
              label TEXT,
              FOREIGN KEY (node_id) REFERENCES nodes(id)
            );
            CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file_id);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_node_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_node_id);
            """
        )
