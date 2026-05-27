"""Filesystem watcher for incremental graph updates."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from graphlens.analysis.communities import CommunityDetector
from graphlens.graph.builder import GraphBuilder
from graphlens.parser.tree_sitter_parser import TreeSitterParser

LOGGER = logging.getLogger(__name__)


class GraphLensEventHandler(FileSystemEventHandler):
    """Debounced watchdog event handler."""

    def __init__(self, builder: GraphBuilder, delay: float = 0.5) -> None:
        self.builder = builder
        self.delay = delay
        self.timers: dict[str, threading.Timer] = {}

    def on_modified(self, event: FileSystemEvent) -> None:
        self._schedule(event)

    def on_created(self, event: FileSystemEvent) -> None:
        self._schedule(event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            LOGGER.info("Deleted file: %s", event.src_path)

    def _schedule(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = event.src_path
        old = self.timers.get(path)
        if old:
            old.cancel()
        timer = threading.Timer(self.delay, self._update, args=(path,))
        self.timers[path] = timer
        timer.start()

    def _update(self, path: str) -> None:
        result = TreeSitterParser().parse_file(path)
        if result is None:
            return
        self.builder.store_result(result)
        CommunityDetector(self.builder.storage).detect(self.builder.to_networkx())
        LOGGER.info("Updated graph: %s (+%s nodes)", path, len(result.functions) + len(result.classes))


def watch(repo_path: str | Path = ".") -> None:
    """Run the background watcher until interrupted."""

    builder = GraphBuilder(repo_path)
    observer = Observer()
    observer.schedule(GraphLensEventHandler(builder), str(repo_path), recursive=True)
    observer.start()
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
