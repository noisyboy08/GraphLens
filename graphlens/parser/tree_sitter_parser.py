"""Tree-sitter backed source parser."""

from __future__ import annotations

import ast
import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .languages import extract_ipynb_code, get_language_config, load_tree_sitter_language

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Symbol:
    """A parsed code symbol."""

    name: str
    line_start: int
    line_end: int
    docstring: str = ""


@dataclass(frozen=True)
class ImportRef:
    """A parsed import statement."""

    name: str
    source: str
    line: int


@dataclass(frozen=True)
class CallRef:
    """A function call relation."""

    caller: str
    callee: str
    line: int


@dataclass(frozen=True)
class ParseResult:
    """Structured parse result for one file."""

    path: str
    language: str
    sha256: str
    functions: list[Symbol] = field(default_factory=list)
    classes: list[Symbol] = field(default_factory=list)
    imports: list[ImportRef] = field(default_factory=list)
    calls: list[CallRef] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class TreeSitterParser:
    """Parse source files into structural symbols and references."""

    def parse_file(self, path: str | Path) -> ParseResult | None:
        """Parse a file, gracefully skipping unsupported or unreadable input."""

        path = Path(path)
        config = get_language_config(path)
        if config is None:
            return None
        content = extract_ipynb_code(path) if path.suffix == ".ipynb" else self._read_text(path)
        if content is None or self._looks_binary(content):
            return None
        sha = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
        if config.name == "python":
            return self._parse_python(path, config.name, content, sha)
        return self._parse_with_tree_sitter(path, config.name, content, sha)

    def parse_text(self, path: str, content: str, language: str = "python") -> ParseResult:
        """Parse in-memory source text."""

        sha = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
        if language == "python":
            return self._parse_python(Path(path), language, content, sha)
        return self._parse_generic(Path(path), language, content, sha)

    def _parse_python(self, path: Path, language: str, content: str, sha: str) -> ParseResult:
        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            return ParseResult(str(path), language, sha, errors=[str(exc)])
        visitor = _PythonVisitor(content)
        visitor.visit(tree)
        return ParseResult(
            path=str(path),
            language=language,
            sha256=sha,
            functions=visitor.functions,
            classes=visitor.classes,
            imports=visitor.imports,
            calls=visitor.calls,
        )

    def _parse_with_tree_sitter(self, path: Path, language: str, content: str, sha: str) -> ParseResult:
        config = get_language_config(path)
        ts_language = load_tree_sitter_language(config) if config else None
        if ts_language is None:
            return self._parse_generic(path, language, content, sha)
        try:
            from tree_sitter import Language, Parser

            parser = Parser()
            lang = ts_language if isinstance(ts_language, Language) else Language(ts_language)
            _set_language(parser, lang)
            tree = parser.parse(content.encode("utf-8", errors="replace"))
            return self._parse_tree(path, language, content, sha, tree.root_node)
        except Exception as exc:
            LOGGER.warning("Tree-sitter parse failed for %s: %s", path, exc)
            result = self._parse_generic(path, language, content, sha)
            result.errors.append(str(exc))
            return result

    def _parse_tree(self, path: Path, language: str, content: str, sha: str, root: Any) -> ParseResult:
        funcs: list[Symbol] = []
        classes: list[Symbol] = []
        imports: list[ImportRef] = []
        calls: list[CallRef] = []
        exports: list[str] = []
        stack: list[str] = ["<module>"]
        for node in _walk(root):
            kind = node.type
            text = _node_text(content, node)
            line = node.start_point[0] + 1
            if kind in _FUNCTION_TYPES:
                name = _identifier_name(content, node) or _name_from_text(text)
                funcs.append(Symbol(name, line, node.end_point[0] + 1, _leading_comment(content, line)))
                stack.append(name)
            elif kind in _CLASS_TYPES:
                name = _identifier_name(content, node) or _name_from_text(text)
                classes.append(Symbol(name, line, node.end_point[0] + 1, _leading_comment(content, line)))
            elif "import" in kind:
                imports.append(ImportRef(_import_name(text), _import_source(text), line))
            elif kind == "call_expression":
                calls.append(CallRef(stack[-1], _call_name(text), line))
            elif "export" in kind:
                exports.append(_export_name(text))
        return ParseResult(str(path), language, sha, funcs, classes, imports, calls, exports)

    def _parse_generic(self, path: Path, language: str, content: str, sha: str) -> ParseResult:
        funcs = [Symbol(m.group(1), content[: m.start()].count("\n") + 1, content[: m.end()].count("\n") + 1) for m in _GENERIC_FUNCTION_RE.finditer(content)]
        classes = [Symbol(m.group(1), content[: m.start()].count("\n") + 1, content[: m.end()].count("\n") + 1) for m in _GENERIC_CLASS_RE.finditer(content)]
        imports = [ImportRef(_import_name(m.group(0)), _import_source(m.group(0)), content[: m.start()].count("\n") + 1) for m in _GENERIC_IMPORT_RE.finditer(content)]
        exports = [m.group(1) for m in re.finditer(r"\bexport\s+(?:default\s+)?(?:class|function|const|let|var)?\s*([A-Za-z_$][\w$]*)", content)]
        calls = [CallRef("<module>", m.group(1), content[: m.start()].count("\n") + 1) for m in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*\(", content)]
        return ParseResult(str(path), language, sha, funcs, classes, imports, calls, exports)

    def _read_text(self, path: Path) -> str | None:
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return path.read_text(encoding=enc)
            except UnicodeError:
                continue
            except OSError as exc:
                LOGGER.warning("Could not read %s: %s", path, exc)
                return None
        LOGGER.warning("Could not decode %s", path)
        return None

    def _looks_binary(self, content: str) -> bool:
        return "\x00" in content[:4096]


class _PythonVisitor(ast.NodeVisitor):
    def __init__(self, content: str) -> None:
        self.content = content
        self.functions: list[Symbol] = []
        self.classes: list[Symbol] = []
        self.imports: list[ImportRef] = []
        self.calls: list[CallRef] = []
        self.scope: list[str] = ["<module>"]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(Symbol(node.name, node.lineno, node.end_lineno or node.lineno, ast.get_docstring(node) or ""))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(ImportRef(alias.asname or alias.name, alias.name, node.lineno))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        source = "." * node.level + (node.module or "")
        for alias in node.names:
            self.imports.append(ImportRef(alias.asname or alias.name, source, node.lineno))

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append(CallRef(self.scope[-1], _python_call_name(node.func), node.lineno))
        self.generic_visit(node)

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.functions.append(Symbol(node.name, node.lineno, node.end_lineno or node.lineno, ast.get_docstring(node) or ""))
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()


def _set_language(parser: Any, language: Any) -> None:
    if hasattr(parser, "set_language"):
        parser.set_language(language)
    else:
        parser.language = language


def _walk(node: Any) -> Iterable[Any]:
    yield node
    for child in getattr(node, "children", []):
        yield from _walk(child)


def _node_text(content: str, node: Any) -> str:
    return content.encode("utf-8", errors="replace")[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _identifier_name(content: str, node: Any) -> str:
    for child in getattr(node, "children", []):
        if child.type in {"identifier", "property_identifier", "type_identifier"}:
            return _node_text(content, child)
    return ""


def _name_from_text(text: str) -> str:
    match = re.search(r"(?:def|function|class|fn)\s+([A-Za-z_$][\w$]*)", text)
    return match.group(1) if match else "<anonymous>"


def _leading_comment(content: str, line: int) -> str:
    lines = content.splitlines()
    comments: list[str] = []
    for idx in range(line - 2, max(-1, line - 8), -1):
        stripped = lines[idx].strip() if idx < len(lines) else ""
        if stripped.startswith(("#", "//")):
            comments.append(stripped.lstrip("#/ "))
        elif stripped:
            break
    return "\n".join(reversed(comments))


def _python_call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return "<unknown>"


def _import_name(text: str) -> str:
    match = re.search(r"import\s+(?:type\s+)?(?:\{?\s*)?([@\w$./*-]+)", text)
    return match.group(1) if match else text[:80]


def _import_source(text: str) -> str:
    match = re.search(r"from\s+['\"]?([^'\";\n]+)", text)
    return match.group(1).strip() if match else _import_name(text)


def _call_name(text: str) -> str:
    match = re.match(r"\s*([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)", text)
    return match.group(1).split(".")[-1] if match else "<unknown>"


def _export_name(text: str) -> str:
    match = re.search(r"\b(?:class|function|const|let|var)\s+([A-Za-z_$][\w$]*)", text)
    return match.group(1) if match else text[:80]


_FUNCTION_TYPES = {"function_definition", "function_declaration", "method_definition", "method_declaration", "function_item"}
_CLASS_TYPES = {"class_definition", "class_declaration", "struct_item", "interface_declaration"}
_GENERIC_FUNCTION_RE = re.compile(r"\b(?:def|function|fn|func)\s+([A-Za-z_$][\w$]*)", re.MULTILINE)
_GENERIC_CLASS_RE = re.compile(r"\b(?:class|struct|interface)\s+([A-Za-z_$][\w$]*)", re.MULTILINE)
_GENERIC_IMPORT_RE = re.compile(r"^\s*(?:import|from|require\(|use\s+).*$", re.MULTILINE)
