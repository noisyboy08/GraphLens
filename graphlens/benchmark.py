"""Benchmark GraphLens repository parsing and token reduction."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from graphlens.graph.builder import GraphBuilder
from graphlens.graph.tokens import TokenCounter


@dataclass(frozen=True)
class BenchmarkResult:
    """Benchmark result."""

    files_scanned: int
    files_parsed: int
    files_skipped: int
    errors: int
    seconds: float
    files_per_second: float
    total_tokens: int
    selected_context_tokens: int
    token_savings: int
    token_reduction_ratio: float

    def to_dict(self) -> dict[str, float | int]:
        """Return JSON-serializable result."""

        return self.__dict__.copy()


def run_benchmark(repo_path: str | Path = ".", context_files: int = 20) -> BenchmarkResult:
    """Run a clean parse benchmark without replacing the main graph database."""

    repo = Path(repo_path).resolve()
    bench_dir = Path(".graphlens/benchmark")
    db_path = bench_dir / "graph.db"
    if bench_dir.exists():
        shutil.rmtree(bench_dir)
    builder = GraphBuilder(repo, db_path)
    files = builder._source_files()
    started = time.perf_counter()
    report = builder.build()
    seconds = max(0.000001, time.perf_counter() - started)
    rel_files = [str(path.resolve().relative_to(repo)).replace("\\", "/") for path in files]
    counter = TokenCounter()
    total_tokens = counter.count_files(repo, rel_files)
    selected_tokens = counter.count_files(repo, rel_files[:context_files])
    builder.storage.close()
    shutil.rmtree(bench_dir, ignore_errors=True)
    savings = max(0, total_tokens - selected_tokens)
    ratio = round(total_tokens / max(1, selected_tokens), 2) if selected_tokens else float(total_tokens > 0)
    return BenchmarkResult(
        files_scanned=len(files),
        files_parsed=report.parsed,
        files_skipped=report.skipped,
        errors=report.errors,
        seconds=round(seconds, 4),
        files_per_second=round(len(files) / seconds, 2),
        total_tokens=total_tokens,
        selected_context_tokens=selected_tokens,
        token_savings=savings,
        token_reduction_ratio=ratio,
    )


def format_benchmark(result: BenchmarkResult) -> str:
    """Return readable benchmark output."""

    return "\n".join(
        [
            "GraphLens benchmark",
            f"Files scanned: {result.files_scanned}",
            f"Files parsed: {result.files_parsed}",
            f"Files skipped: {result.files_skipped}",
            f"Errors: {result.errors}",
            f"Seconds: {result.seconds}",
            f"Files/sec: {result.files_per_second}",
            f"Total tokens: {result.total_tokens}",
            f"Selected context tokens: {result.selected_context_tokens}",
            f"Token savings: {result.token_savings}",
            f"Token reduction ratio: {result.token_reduction_ratio}x",
        ]
    )
