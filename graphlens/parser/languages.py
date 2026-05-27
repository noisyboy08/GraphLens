"""Language detection and tree-sitter grammar loading."""

from __future__ import annotations

import importlib
import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class LanguageConfig:
    """Configuration for a source language."""

    name: str
    extensions: tuple[str, ...]
    package: str | None
    grammar_name: str | None = None


LANGUAGES: tuple[LanguageConfig, ...] = (
    LanguageConfig("python", (".py", ".pyw", ".ipynb"), "tree_sitter_python"),
    LanguageConfig("javascript", (".js", ".jsx", ".mjs", ".cjs"), "tree_sitter_javascript"),
    LanguageConfig("typescript", (".ts",), "tree_sitter_typescript", "typescript"),
    LanguageConfig("tsx", (".tsx",), "tree_sitter_typescript", "tsx"),
    LanguageConfig("go", (".go",), "tree_sitter_go"),
    LanguageConfig("rust", (".rs",), "tree_sitter_rust"),
    LanguageConfig("java", (".java",), "tree_sitter_java"),
    LanguageConfig("ruby", (".rb",), "tree_sitter_ruby"),
    LanguageConfig("php", (".php",), "tree_sitter_php", "php"),
    LanguageConfig("c", (".c", ".h"), "tree_sitter_c"),
    LanguageConfig("cpp", (".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx"), "tree_sitter_cpp"),
    LanguageConfig("kotlin", (".kt", ".kts"), "tree_sitter_kotlin"),
    LanguageConfig("swift", (".swift",), "tree_sitter_swift"),
    LanguageConfig("scala", (".scala", ".sc"), "tree_sitter_scala"),
    LanguageConfig("vue", (".vue",), "tree_sitter_vue"),
    LanguageConfig("svelte", (".svelte",), "tree_sitter_svelte"),
    LanguageConfig("lua", (".lua",), "tree_sitter_lua"),
    LanguageConfig("zig", (".zig",), "tree_sitter_zig"),
    LanguageConfig("julia", (".jl",), "tree_sitter_julia"),
    LanguageConfig("r", (".r", ".R"), "tree_sitter_r"),
    LanguageConfig("nix", (".nix",), "tree_sitter_nix"),
    LanguageConfig("powershell", (".ps1", ".psm1", ".psd1"), "tree_sitter_powershell"),
    LanguageConfig("perl", (".pl", ".pm"), "tree_sitter_perl"),
    LanguageConfig("csharp", (".cs",), "tree_sitter_c_sharp"),
    LanguageConfig("solidity", (".sol",), "tree_sitter_solidity"),
)

EXTENSION_MAP = {ext: cfg for cfg in LANGUAGES for ext in cfg.extensions}


def get_language_config(path: str | Path) -> LanguageConfig | None:
    """Return language config for a path extension."""

    suffix = Path(path).suffix
    return EXTENSION_MAP.get(suffix) or EXTENSION_MAP.get(suffix.lower())


def load_tree_sitter_language(config: LanguageConfig) -> Any | None:
    """Load a tree-sitter Language object, installing grammar if possible."""

    if not config.package:
        return None
    module = _import_or_install(config.package)
    if module is None:
        return None
    candidates = _language_function_names(config)
    for name in candidates:
        fn = getattr(module, name, None)
        if callable(fn):
            try:
                return fn()
            except Exception as exc:  # pragma: no cover - grammar API variance
                LOGGER.debug("Failed language loader %s.%s: %s", config.package, name, exc)
    return None


def extract_ipynb_code(path: str | Path) -> str:
    """Extract code cells from a Jupyter notebook."""

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        LOGGER.warning("Could not read notebook %s: %s", path, exc)
        return ""
    chunks: list[str] = []
    for cell in data.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        chunks.append("".join(source) if isinstance(source, list) else str(source))
    return "\n\n".join(chunks)


def _import_or_install(package: str) -> Any | None:
    try:
        return importlib.import_module(package)
    except ImportError:
        LOGGER.info("Attempting to install missing grammar package %s", package)
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", package.replace("_", "-")],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return importlib.import_module(package)
    except Exception as exc:  # pragma: no cover - depends on network/env
        LOGGER.warning("Could not install grammar %s: %s", package, exc)
        return None


def _language_function_names(config: LanguageConfig) -> tuple[str, ...]:
    base = config.grammar_name or config.name
    return (f"language_{base}", base, "language")
