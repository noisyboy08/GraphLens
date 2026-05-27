"""GraphLens MCP server."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, TypeVar

from graphlens.analysis.blast_radius import BlastRadiusAnalyzer
from graphlens.analysis.communities import CommunityDetector
from graphlens.analysis.hubs import detect_hubs
from graphlens.analysis.risk import health_score
from graphlens.graph.builder import GraphBuilder
from graphlens.graph.storage import GraphStorage
from graphlens.graph.tokens import TokenCounter
from graphlens.graph.traversal import GraphTraversal

LOG_DIR = Path(".graphlens")
LOG_DIR.mkdir(exist_ok=True)
LOGGER = logging.getLogger("graphlens.mcp")
handler = RotatingFileHandler(LOG_DIR / "mcp.log", maxBytes=10_000_000, backupCount=3)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)
F = TypeVar("F", bound=Callable[..., dict[str, Any]])


class GraphLensToolError(ValueError):
    """User-facing MCP tool error."""


class GraphLensService:
    """Implementation backing MCP tools."""

    def __init__(self, repo_path: str | Path | None = None, db_path: str | Path = ".graphlens/graph.db") -> None:
        self.repo_path = Path(repo_path) if repo_path is not None else _repo_root_from_config()
        self.storage = GraphStorage(db_path)
        self.traversal = GraphTraversal(self.storage)
        self.tokens = TokenCounter()

    def get_relevant_files(self, file_path: str, depth: int = 2, token_budget: int = 50000) -> dict[str, Any]:
        if depth < 0 or token_budget < 1:
            raise GraphLensToolError("depth must be >= 0 and token_budget must be > 0")
        files = self.traversal.get_context_for_file(file_path, depth, token_budget)
        all_files = [row["path"] for row in self.storage.rows("SELECT path FROM files WHERE path NOT LIKE '<external>/%'")]
        selected_tokens = self.tokens.count_files(self.repo_path, files)
        all_tokens = self.tokens.count_files(self.repo_path, all_files)
        saved = max(0, all_tokens - selected_tokens)
        return {"files": files, "reason": f"BFS dependency context within depth {depth}", "tokens_saved": saved}

    def get_blast_radius(self, changed_files: list[str]) -> dict[str, Any]:
        if not changed_files:
            raise GraphLensToolError("changed_files must contain at least one path")
        result = BlastRadiusAnalyzer(self.traversal).analyze(changed_files)
        affected = [a.__dict__ for a in [*result.directly_affected, *result.transitively_affected]]
        risk = "high" if result.total_affected_count > 20 else "medium" if result.total_affected_count > 5 else "low"
        return {"affected_files": affected, "tests": result.related_tests, "summary": result.to_markdown(), "risk_level": risk}

    def get_function_context(self, function_name: str, file_path: str = "") -> dict[str, Any]:
        if not function_name:
            raise GraphLensToolError("function_name is required")
        rows = self.storage.rows(
            """
            SELECT nodes.line_start, files.path FROM nodes
            JOIN files ON files.id=nodes.file_id
            WHERE nodes.name=? AND (?='' OR files.path=?)
            LIMIT 1
            """,
            (function_name, file_path, file_path),
        )
        row = rows[0] if rows else None
        return {
            "callers": self.traversal.get_callers(function_name),
            "callees": self.traversal.get_callees(function_name),
            "file_path": row["path"] if row else file_path,
            "line": row["line_start"] if row else 0,
        }

    def get_file_dependencies(self, file_path: str) -> dict[str, Any]:
        if not file_path:
            raise GraphLensToolError("file_path is required")
        community = CommunityDetector(self.storage).get_community_for_file(file_path)
        return {
            "imports": self.traversal.get_imports_of(file_path),
            "imported_by": self.traversal.get_dependents(file_path),
            "community": community["label"] if community else "",
        }

    def search_codebase(self, query: str, limit: int = 10) -> dict[str, Any]:
        if not query:
            raise GraphLensToolError("query is required")
        if limit < 1:
            raise GraphLensToolError("limit must be >= 1")
        rows = self.storage.search_nodes(query, limit)
        return {"results": [dict(r) for r in rows]}

    def get_graph_summary(self) -> dict[str, Any]:
        summary = self.storage.summary()
        graph = GraphBuilder().to_networkx()
        return {**summary, "hubs": [h.__dict__ for h in detect_hubs(graph)], "health_score": health_score(graph)}


def safe_tool(name: str, fn: F) -> F:
    """Wrap MCP tool logic with logging and consistent errors."""

    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        LOGGER.info("%s args=%s kwargs=%s", name, args, kwargs)
        try:
            return fn(*args, **kwargs)
        except GraphLensToolError:
            LOGGER.warning("%s validation failed", name, exc_info=True)
            raise
        except Exception as exc:
            LOGGER.exception("%s failed", name)
            raise GraphLensToolError(f"{name} failed: {exc}") from exc

    return wrapped  # type: ignore[return-value]


def create_server() -> Any:
    """Create the official MCP stdio server."""

    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover - dependency optional in tests
        raise RuntimeError("mcp package is required to run the server") from exc
    mcp = FastMCP("graphlens")
    service = GraphLensService()

    @mcp.tool()
    def get_relevant_files(file_path: str, depth: int = 2, token_budget: int = 50000) -> dict[str, Any]:
        return safe_tool("get_relevant_files", service.get_relevant_files)(file_path, depth, token_budget)

    @mcp.tool()
    def get_blast_radius(changed_files: list[str]) -> dict[str, Any]:
        return safe_tool("get_blast_radius", service.get_blast_radius)(changed_files)

    @mcp.tool()
    def get_function_context(function_name: str, file_path: str = "") -> dict[str, Any]:
        return safe_tool("get_function_context", service.get_function_context)(function_name, file_path)

    @mcp.tool()
    def get_file_dependencies(file_path: str) -> dict[str, Any]:
        return safe_tool("get_file_dependencies", service.get_file_dependencies)(file_path)

    @mcp.tool()
    def search_codebase(query: str, limit: int = 10) -> dict[str, Any]:
        return safe_tool("search_codebase", service.search_codebase)(query, limit)

    @mcp.tool()
    def get_graph_summary() -> dict[str, Any]:
        return safe_tool("get_graph_summary", service.get_graph_summary)()

    return mcp


def main() -> None:
    """Run GraphLens as a stdio MCP server."""

    create_server().run()


def _repo_root_from_config() -> Path:
    config = Path(".graphlens/config.json")
    if not config.exists():
        return Path(".")
    try:
        return Path(json.loads(config.read_text(encoding="utf-8")).get("repo_root") or ".")
    except (OSError, json.JSONDecodeError):
        return Path(".")
