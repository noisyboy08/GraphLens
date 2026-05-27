"""Repository graph builder."""

from __future__ import annotations

import hashlib
import json
import logging
import posixpath
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from graphlens.parser.languages import get_language_config
from graphlens.parser.tree_sitter_parser import ParseResult, TreeSitterParser

from .storage import GraphStorage

LOGGER = logging.getLogger(__name__)
SKIP_DIRS = {"node_modules", ".git", "__pycache__", "dist", "build", ".venv", "venv"}


@dataclass(frozen=True)
class BuildReport:
    """Repository build summary."""

    parsed: int
    skipped: int
    errors: int


class GraphBuilder:
    """Build and persist a structural graph for a repository."""

    def __init__(self, repo_path: str | Path = ".", db_path: str | Path = ".graphlens/graph.db") -> None:
        self.repo_path = Path(repo_path).resolve()
        self.db_path = Path(db_path)
        self.storage = GraphStorage(db_path)
        self._known_sources: set[str] = set()
        self._symbols_by_file: dict[str, dict[str, int]] = {}

    def build(self, max_workers: int = 4) -> BuildReport:
        """Parse changed files and store graph rows."""

        files = list(self._source_files())
        self._known_sources = {self._rel(path) for path in files}
        self._write_metadata()
        parsed = skipped = errors = 0
        parser = TreeSitterParser()
        results: list[ParseResult] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            for path in files:
                sha = self._sha(path)
                rel = self._rel(path)
                if not self.storage.file_needs_update(rel, sha):
                    skipped += 1
                    continue
                futures[pool.submit(parser.parse_file, path)] = path
            for fut in as_completed(futures):
                try:
                    result = fut.result()
                    if result is None:
                        skipped += 1
                        continue
                    results.append(result)
                    parsed += 1
                    errors += int(bool(result.errors))
                except Exception as exc:
                    LOGGER.exception("Failed parsing %s: %s", futures[fut], exc)
                    errors += 1
        for result in results:
            self._store_nodes(result)
        for result in results:
            self._store_edges(result)
        return BuildReport(parsed, skipped, errors)

    def store_result(self, result: ParseResult) -> None:
        """Store one parse result in SQLite."""

        self._store_nodes(result)
        self._store_edges(result)

    def _store_nodes(self, result: ParseResult) -> None:
        """Store module and symbol nodes for one result."""

        rel = self._rel(Path(result.path))
        file_id = self.storage.upsert_file(rel, result.sha256, result.language)
        self.storage.delete_file_nodes(file_id)
        module_id = self.storage.upsert_node(file_id, "module", rel, 1, 1)
        symbol_ids: dict[str, int] = {"<module>": module_id}
        for cls in result.classes:
            symbol_ids[cls.name] = self.storage.upsert_node(file_id, "class", cls.name, cls.line_start, cls.line_end, cls.docstring)
        for fn in result.functions:
            symbol_ids[fn.name] = self.storage.upsert_node(file_id, "function", fn.name, fn.line_start, fn.line_end, fn.docstring)
        self._symbols_by_file[rel] = symbol_ids

    def _store_edges(self, result: ParseResult) -> None:
        """Store import and call edges for one result."""

        rel = self._rel(Path(result.path))
        symbol_ids = self._symbols_by_file.get(rel)
        if symbol_ids is None:
            file_row = self.storage.get_file_by_path(rel)
            if file_row is None:
                return
            symbol_ids = {row["name"]: row["id"] for row in self.storage.get_nodes_by_file(file_row["id"])}
        for imp in result.imports:
            target = self._resolve_import_node(rel, imp.source or imp.name)
            self.storage.upsert_edge(symbol_ids["<module>"], target, "imports")
        for call in result.calls:
            source = symbol_ids.get(call.caller, symbol_ids["<module>"])
            target = symbol_ids.get(call.callee) or self._find_or_stub(call.callee)
            self.storage.upsert_edge(source, target, "calls")

    def to_networkx(self) -> nx.DiGraph:
        """Load the SQLite graph into NetworkX."""

        graph = nx.DiGraph()
        rows = self.storage.rows(
            """
            SELECT nodes.*, files.path FROM nodes
            JOIN files ON files.id = nodes.file_id
            """
        )
        for row in rows:
            graph.add_node(row["id"], name=row["name"], file=row["path"], type=row["node_type"])
        for edge in self.storage.get_all_edges():
            graph.add_edge(edge["source_node_id"], edge["target_node_id"], type=edge["edge_type"])
        return graph

    def _source_files(self) -> list[Path]:
        paths: list[Path] = []
        for path in self.repo_path.rglob("*"):
            if any(part in SKIP_DIRS for part in path.parts) or path.name.endswith(".min.js"):
                continue
            if path.is_file() and get_language_config(path):
                paths.append(path)
        return paths

    def _sha(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _rel(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.repo_path)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

    def _ensure_external_node(self, name: str) -> int:
        ext_path = f"<external>/{name}"
        file_id = self.storage.upsert_file(ext_path, "", "external")
        nodes = self.storage.get_nodes_by_file(file_id)
        return int(nodes[0]["id"]) if nodes else self.storage.upsert_node(file_id, "module", name, 1, 1)

    def _find_or_stub(self, name: str) -> int:
        rows = self.storage.rows("SELECT id FROM nodes WHERE name=? LIMIT 1", (name,))
        return int(rows[0]["id"]) if rows else self._ensure_external_node(name)

    def _resolve_import_node(self, importer: str, source: str) -> int:
        target_path = self._resolve_import_path(importer, source)
        if target_path is None:
            return self._ensure_external_node(source)
        rows = self.storage.rows(
            """
            SELECT nodes.id FROM nodes
            JOIN files ON files.id=nodes.file_id
            WHERE files.path=? AND nodes.node_type='module'
            LIMIT 1
            """,
            (target_path,),
        )
        if rows:
            return int(rows[0]["id"])
        file_id = self.storage.upsert_file(target_path, "", self._language_name(target_path))
        return self.storage.upsert_node(file_id, "module", target_path, 1, 1)

    def _resolve_import_path(self, importer: str, source: str) -> str | None:
        cleaned = source.strip().strip("'\";")
        if not cleaned or cleaned.startswith(("@", "http:", "https:")):
            return None
        candidates = self._candidate_import_paths(importer, cleaned)
        known = self._known_sources or {row["path"] for row in self.storage.rows("SELECT path FROM files")}
        for candidate in candidates:
            if candidate in known:
                return candidate
        return None

    def _candidate_import_paths(self, importer: str, source: str) -> list[str]:
        importer_dir = str(Path(importer).parent).replace("\\", "/")
        if importer_dir == ".":
            importer_dir = ""
        bases: list[str] = []
        if source.startswith("."):
            bases.append(posixpath.normpath(posixpath.join(importer_dir, source)))
        else:
            bases.extend([source.replace(".", "/"), posixpath.normpath(posixpath.join(importer_dir, source))])
        suffixes = ["", ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", "/index.js", "/index.ts", "/__init__.py"]
        out: list[str] = []
        for base in bases:
            rel_base = base.replace("\\", "/").lstrip("./")
            out.extend(f"{rel_base}{suffix}" for suffix in suffixes)
        return [path.replace("\\", "/").lstrip("./") for path in out]

    def _language_name(self, path: str) -> str:
        config = get_language_config(path)
        return config.name if config else "unknown"

    def _write_metadata(self) -> None:
        meta = self.db_path.parent / "config.json"
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(json.dumps({"repo_root": str(self.repo_path)}, indent=2), encoding="utf-8")
