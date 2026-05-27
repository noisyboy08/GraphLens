"""Blast radius analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from graphlens.graph.traversal import GraphTraversal


@dataclass(frozen=True)
class AffectedFile:
    """Affected file with an impact score."""

    path: str
    impact: float
    reason: str


@dataclass(frozen=True)
class BlastRadiusResult:
    """Blast radius response."""

    changed_files: list[str]
    directly_affected: list[AffectedFile]
    transitively_affected: list[AffectedFile]
    related_tests: list[str]
    total_affected_count: int
    recommended_review_files: list[str]

    def to_markdown(self) -> str:
        """Format the analysis for AI consumption."""

        lines = ["# Blast Radius", "", f"Changed: {', '.join(self.changed_files)}"]
        lines.append(f"Total affected files: {self.total_affected_count}")
        lines.append("## Recommended review")
        lines.extend(f"- {path}" for path in self.recommended_review_files)
        if self.related_tests:
            lines.append("## Related tests")
            lines.extend(f"- {path}" for path in self.related_tests)
        return "\n".join(lines)


class BlastRadiusAnalyzer:
    """Compute file impact from dependency relationships."""

    def __init__(self, traversal: GraphTraversal | None = None) -> None:
        self.traversal = traversal or GraphTraversal()

    def analyze(self, changed_files: list[str]) -> BlastRadiusResult:
        """Analyze directly and transitively affected files."""

        changed = [self._norm(path) for path in changed_files]
        direct: dict[str, AffectedFile] = {}
        transitive: dict[str, AffectedFile] = {}
        tests: set[str] = set()
        for path in changed:
            for dep in self.traversal.get_dependents(path):
                direct[dep] = AffectedFile(dep, 1.0, f"imports {path}")
                tests.update(self._related_tests(dep))
                self._walk_transitive(dep, path, transitive)
            tests.update(self._related_tests(path))
        recommended = self._recommend(changed, direct, transitive, tests)
        total = len(set(direct) | set(transitive))
        return BlastRadiusResult(changed, list(direct.values()), list(transitive.values()), sorted(tests), total, recommended)

    def _walk_transitive(self, start: str, changed: str, out: dict[str, AffectedFile]) -> None:
        frontier = [(start, 1)]
        seen = {start}
        while frontier:
            path, depth = frontier.pop(0)
            if depth >= 3:
                continue
            for dep in self.traversal.get_dependents(path):
                if dep in seen:
                    continue
                seen.add(dep)
                impact = max(0.25, 1.0 - depth * 0.25)
                out[dep] = AffectedFile(dep, impact, f"transitively depends on {changed}")
                frontier.append((dep, depth + 1))

    def _related_tests(self, path: str) -> set[str]:
        stem = Path(path).stem.replace("test_", "").replace("_test", "").replace("_spec", "")
        rows = self.traversal.storage.rows("SELECT path FROM files WHERE path LIKE ?", (f"%{stem}%",))
        return {r["path"] for r in rows if self._is_test(r["path"])}

    def _recommend(self, changed: list[str], direct: dict[str, AffectedFile], trans: dict[str, AffectedFile], tests: set[str]) -> list[str]:
        scored = {item.path: item.impact for item in [*direct.values(), *trans.values()]}
        for test in tests:
            scored[test] = max(scored.get(test, 0.0), 0.9)
        for path in changed:
            scored[path] = 1.0
        return [path for path, _ in sorted(scored.items(), key=lambda kv: kv[1], reverse=True)[:15]]

    def _is_test(self, path: str) -> bool:
        name = Path(path).name
        return name.startswith("test_") or "_test" in name or "_spec" in name

    def _norm(self, path: str) -> str:
        return str(Path(path)).replace("\\", "/")


def analyze(changed_files: list[str]) -> BlastRadiusResult:
    """Convenience function for blast radius analysis."""

    return BlastRadiusAnalyzer().analyze(changed_files)
