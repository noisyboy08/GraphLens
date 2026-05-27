from pathlib import Path

from graphlens.parser.tree_sitter_parser import TreeSitterParser


def test_python_file_parsing() -> None:
    result = TreeSitterParser().parse_file(Path("tests/fixtures/sample_python/app.py"))
    assert result is not None
    assert {fn.name for fn in result.functions} >= {"run", "main"}
    assert {cls.name for cls in result.classes} == {"Service"}
    assert any(imp.source == "utils" for imp in result.imports)


def test_js_ts_file_parsing() -> None:
    result = TreeSitterParser().parse_file(Path("tests/fixtures/sample_typescript/index.ts"))
    assert result is not None
    assert "main" in {fn.name for fn in result.functions}
    assert "main" in result.exports


def test_function_call_extraction() -> None:
    result = TreeSitterParser().parse_file(Path("tests/fixtures/sample_python/app.py"))
    assert result is not None
    assert "helper" in {call.callee for call in result.calls}


def test_sha256_change_detection() -> None:
    a = TreeSitterParser().parse_text("a.py", "def a():\n    pass\n")
    b = TreeSitterParser().parse_text("a.py", "def a():\n    return 1\n")
    assert a.sha256 != b.sha256
