"""Symbol extraction for repository ingestion.

Extracts function, method, and class definitions from source code using
language-appropriate parsers.  Symbol information is stored in
``RetrievedChunk.symbol`` so the retrieval layer can surface relevant
declarations.

Supported languages
-----------------
- Python 3.8+: uses ``ast`` from the standard library (no external deps).
- TypeScript/JavaScript: conservative regex-based heuristic (no parser
  dependency).  Only extracts top-level ``function``/``class`` declarations
  and method names within classes.  Arrow functions and nested functions
  are deliberately not extracted to avoid fragile heuristics.

Symbol kind values (stored in ``RetrievedChunk.symbol``):
``"function"``, ``"method"``, ``"class"``, ``"constructor"``.

The ``symbol`` field format: ``"simple_name"`` for top-level declarations,
``"ClassName.method_name"`` for methods, ``"ClassName"`` for classes.

Limitations
-----------
- Python: full AST parsing, but does not resolve overloading, decorators
  beyond ``@staticmethod``/``@classmethod``, or name mangling.
- TypeScript/JavaScript: regex-based, cannot parse complex type annotations,
  generic types, or arrow functions safely.  Only extracts what can be
  identified without a full parser.
"""
from __future__ import annotations

import ast
import re

from app.schemas.code_understanding import ProgrammingLanguage


# ---------------------------------------------------------------------------
# Python symbol extraction (using ``ast``)
# ---------------------------------------------------------------------------

def _extract_python_symbols(content: str) -> list[dict]:
    """Extract function/class definitions from Python source via ``ast``.

    Returns a list of dicts with keys: ``name``, ``kind``, ``line_start``,
    ``line_end``.  ``kind`` is one of ``"function"``, ``"method"``,
    ``"class"``, ``"constructor"``.
    """
    symbols: list[dict] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return symbols

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            is_async = isinstance(node, ast.AsyncFunctionDef)
            kind = "async function" if is_async else "function"

            # Determine if it's a constructor
            is_constructor = node.name == "__init__"

            # Use the qualified name if there's a class context
            # (ast.Walk doesn't track nesting directly, so we approximate)
            qualified = node.name

            # For methods inside classes, we can't easily disambiguate here
            # without tracking nesting; we just record the name.
            # The retrieval layer can append context via file_path + line.

            symbols.append(
                {
                    "name": node.name,
                    "kind": kind,
                    "line_start": node.lineno,
                    "line_end": node.end_lineno,
                    "is_constructor": is_constructor,
                    "qualified": qualified,
                    "async": is_async,
                }
            )

        elif isinstance(node, ast.ClassDef):
            kind = "class"
            qualified = node.name

            # Extract method definitions within the class
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    method_kind = "async function" if isinstance(item, ast.AsyncFunctionDef) else "method"
                    symbols.append(
                        {
                            "name": item.name,
                            "kind": method_kind,
                            "line_start": item.lineno,
                            "line_end": item.end_lineno,
                            "is_constructor": item.name == "__init__",
                            "qualified": f"{qualified}.{item.name}",
                            "async": isinstance(item, ast.AsyncFunctionDef),
                        }
                    )

                elif isinstance(item, ast.AsyncFunctionDef):
                    symbols.append(
                        {
                            "name": item.name,
                            "kind": "async function",
                            "line_start": item.lineno,
                            "line_end": item.end_lineno,
                            "is_constructor": item.name == "__init__",
                            "qualified": f"{qualified}.{item.name}",
                            "async": True,
                        }
                    )

    return symbols


# ---------------------------------------------------------------------------
# TypeScript/JavaScript symbol extraction (conservative regex heuristic)
# ---------------------------------------------------------------------------

# Regex patterns for matching common JS/TS constructs without a full parser.
# These are intentionally conservative — they match the most common patterns
# and deliberately avoid matching constructs that would require full
# language understanding (arrow functions, destructured parameters, etc.).

# Match: "function foo() { ... }" or "async function foo() { ... }"
_FUNCTION_PATTERN = re.compile(
    r"^\s*(?:async\s+)?function\s+([A-Za-z_$][0-9A-Za-z_$]*)\s*\(",
    re.MULTILINE,
)

# Match: "class foo { ... }"
_CLASS_PATTERN = re.compile(
    r"^\s*class\s+([A-Za-z_$][0-9A-Za-z_$]*)\s*(?:extends\s+[A-Za-z_$][0-9A-Za-z_$]*)?\s*\{",
    re.MULTILINE,
)

# Match: method inside a class — "  foo() { ... }" or "  async foo() { ... }"
# This is matched after we've identified a class block.
_METHOD_PATTERN = re.compile(
    r"^\s+(?:async\s+)?function\s+([A-Za-z_$][0-9A-Za-z_$]*)\s*\(",
    re.MULTILINE,
)

# Match: exported function/class — "export function foo()" or "export class foo"
_EXPORT_FUNCTION_PATTERN = re.compile(
    r"^\s*export\s+(?:async\s+)?function\s+([A-Za-z_$][0-9A-Za-z_$]*)\s*\(",
    re.MULTILINE,
)
_EXPORT_CLASS_PATTERN = re.compile(
    r"^\s*export\s+class\s+([A-Za-z_$][0-9A-Za-z_$]*)\s*\{",
    re.MULTILINE,
)


def _extract_js_symbols(content: str, language: ProgrammingLanguage) -> list[dict]:
    """Extract symbol information from TypeScript/JavaScript source.

    Uses regex patterns since no parser dependency is available.  Results
    are conservative — only top-level declarations and class methods are
    extracted; arrow functions and nested functions are omitted.

    Parameters
    ----------
    content:
        Source code text.
    language:
        ``ProgrammingLanguage.TYPESCRIPT`` or ``ProgrammingLanguage.JAVASCRIPT``.

    Returns
    -------
    list[dict]
        Each dict has keys: ``name``, ``kind``, ``line_start``, ``line_end``,
        ``is_exported``.  ``kind`` is one of ``"function"``, ``"method"``,
        ``"class"``.
    """
    symbols: list[dict] = []
    lines = content.splitlines()

    # Track whether we are inside a class block (simple heuristic: count
    # open/close braces at the top level).
    in_class = False
    class_name = ""

    # Collect all matches first, then post-process to associate methods
    # with their enclosing class.
    all_matches: list[dict] = []

    # First pass: find top-level functions, classes, and exports
    for i, line in enumerate(lines, start=1):
        # Export function
        m = _EXPORT_FUNCTION_PATTERN.match(line)
        if m:
            all_matches.append(
                {
                    "name": m.group(1),
                    "kind": "function",
                    "line_start": i,
                    "line_end": i,
                    "is_exported": True,
                    "async": False,
                    "class_context": "",
                }
            )
            continue

        # Export class
        m = _EXPORT_CLASS_PATTERN.match(line)
        if m:
            class_name = m.group(1)
            all_matches.append(
                {
                    "name": class_name,
                    "kind": "class",
                    "line_start": i,
                    "line_end": i,
                    "is_exported": True,
                    "async": False,
                    "class_context": class_name,
                }
            )
            in_class = True
            continue

        # Top-level function (non-exported)
        m = _FUNCTION_PATTERN.match(line)
        if m:
            all_matches.append(
                {
                    "name": m.group(1),
                    "kind": "function",
                    "line_start": i,
                    "line_end": i,
                    "is_exported": False,
                    "async": False,
                    "class_context": "",
                }
            )
            continue

        # Top-level class (non-exported)
        m = _CLASS_PATTERN.match(line)
        if m:
            class_name = m.group(1)
            all_matches.append(
                {
                    "name": class_name,
                    "kind": "class",
                    "line_start": i,
                    "line_end": i,
                    "is_exported": False,
                    "async": False,
                    "class_context": class_name,
                }
            )
            in_class = True
            continue

        # Method inside a class (detected by indentation + function keyword)
        if in_class:
            m = _METHOD_PATTERN.match(line)
            if m:
                all_matches.append(
                    {
                        "name": m.group(1),
                        "kind": "method",
                        "line_start": i,
                        "line_end": i,
                        "is_exported": False,
                        "async": False,
                        "class_context": class_name,
                    }
                )
                continue

    # Second pass: if we have class contexts, we need to refine method
    # line_end to include the method body.  For simplicity, we keep line_start
    # and line_end as the line where the method declaration appears.  The
    # retrieval layer already has line_start/line_end from the chunking pipeline.

    return all_matches


# ---------------------------------------------------------------------------
# Integration into chunk generation
# ---------------------------------------------------------------------------

def _symbol_from_python(symbols: list[dict], content: str) -> list[str]:
    """Convert Python extraction result into ``RetrievedChunk.symbol`` values.

    Rules:
    - Constructor ``__init__`` → symbol is the class name (set by caller).
    - Async function → prepend "async " to the name.
    - Regular function → symbol is the function name.
    - Class → symbol is the class name.
    - Duplicate names are deduped; only the first occurrence is kept.
    """
    seen: set[str] = set()
    result: list[str] = []

    for s in symbols:
        name = s["name"]
        if name in seen:
            continue
        seen.add(name)

        if s["is_constructor"]:
            # Constructor symbol will be set by the caller (class name)
            continue

        if s["async"]:
            sym = f"async {name}"
        else:
            sym = name

        # Only add if the symbol actually appears in the content
        if name in content:
            result.append(sym)

    return result


def _symbol_from_js(symbols: list[dict], content: str, language: ProgrammingLanguage) -> list[str]:
    """Convert JS/TS extraction result into ``RetrievedChunk.symbol`` values.

    Rules:
    - Exported symbols get an "exported:" prefix in the symbol field.
    - Method symbols include the class context as ``"ClassName.method"``.
    - Top-level functions/classes use the simple name.
    - Duplicate names are deduped.
    """
    seen: set[str] = set()
    result: list[str] = []

    for s in symbols:
        name = s["name"]
        if name in seen:
            continue
        seen.add(name)

        # Determine kind display string
        kind = s["kind"]
        if kind == "method" and s.get("class_context"):
            sym = f"{s['class_context']}.{name}"
        elif kind == "exported function":
            sym = f"exported: {name}"
        elif kind == "exported class":
            sym = f"exported: {name}"
        elif kind == "function":
            sym = f"{( 'async ' if s.get('async') else '' )}{name}"
        elif kind == "class":
            sym = name
        else:
            sym = name

        # Only add if the symbol actually appears in the content
        if name in content:
            result.append(sym)

    return result


# ---------------------------------------------------------------------------
# Main entry point: extract symbols from content for a given language
# ---------------------------------------------------------------------------

def extract_symbols(
    content: str,
    language: ProgrammingLanguage,
) -> list[str]:
    """Extract symbol names from *content* for the given *language*.

    Returns a list of symbol strings suitable for populating
    ``RetrievedChunk.symbol``.  The list may contain duplicates if the
    extraction finds multiple definitions with the same name in different
    contexts; callers should deduplicate as needed.

    Parameters
    ----------
    content:
        Source code text to analyze.
    language:
        ``ProgrammingLanguage`` value for the source file.

    Returns
    -------
    list[str]
        Symbol strings, e.g. ``["login", "AuthService", "async login"]``.
    """
    if language == ProgrammingLanguage.PYTHON:
        py_symbols = _extract_python_symbols(content)
        return _symbol_from_python(py_symbols, content)

    # TypeScript / JavaScript
    js_symbols = _extract_js_symbols(content, language)
    return _symbol_from_js(js_symbols, content, language)

