# GraphLens MCP Examples

These examples show the kinds of questions an AI assistant can answer through GraphLens after you run:

```bash
graphlens build .
graphlens serve
```

## Find Relevant Files

Prompt:

```text
Use GraphLens to get relevant files for graphlens/cli.py with depth 2.
```

MCP tool:

```json
{
  "tool": "get_relevant_files",
  "input": {
    "file_path": "graphlens/cli.py",
    "depth": 2,
    "token_budget": 50000
  }
}
```

## Analyze Blast Radius

Prompt:

```text
Use GraphLens to analyze the blast radius for graphlens/parser/tree_sitter_parser.py.
```

MCP tool:

```json
{
  "tool": "get_blast_radius",
  "input": {
    "changed_files": ["graphlens/parser/tree_sitter_parser.py"]
  }
}
```

## Find Function Context

Prompt:

```text
Use GraphLens to find callers and callees for the build function.
```

MCP tool:

```json
{
  "tool": "get_function_context",
  "input": {
    "function_name": "build",
    "file_path": "graphlens/graph/builder.py"
  }
}
```

## Inspect File Dependencies

Prompt:

```text
Use GraphLens to explain dependencies for graphlens/mcp/server.py.
```

MCP tool:

```json
{
  "tool": "get_file_dependencies",
  "input": {
    "file_path": "graphlens/mcp/server.py"
  }
}
```
