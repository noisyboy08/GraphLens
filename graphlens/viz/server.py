"""Local visualization server."""

from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from graphlens.graph.snapshot import export_snapshot


class VizHandler(SimpleHTTPRequestHandler):
    """Serve frontend files and graph JSON."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(Path(__file__).parents[2] / "frontend"), **kwargs)

    def end_headers(self) -> None:
        """Add cache disable headers to prevent stale local files."""
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self) -> None:
        """Handle API and static requests."""

        if self.path == "/api/graph":
            self._graph()
            return
        super().do_GET()

    def _graph(self) -> None:
        import json

        body = json.dumps(export_snapshot()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(port: int = 7341) -> None:
    """Start visualization server."""

    ThreadingHTTPServer(("127.0.0.1", port), VizHandler).serve_forever()
