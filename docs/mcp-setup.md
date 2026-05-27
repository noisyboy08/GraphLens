# MCP Setup

GraphLens runs as a stdio MCP server. Build the graph first, then configure your AI assistant to launch `graphlens serve`.

```bash
graphlens build .
graphlens install
```

## Claude Code

`graphlens install` writes:

```text
.claude/mcp.json
```

Manual config:

```json
{
  "mcpServers": {
    "graphlens": {
      "command": "graphlens",
      "args": ["serve"]
    }
  }
}
```

## Cursor

`graphlens install` writes:

```text
.cursor/mcp.json
```

Manual config:

```json
{
  "mcpServers": {
    "graphlens": {
      "command": "graphlens",
      "args": ["serve"]
    }
  }
}
```

## Codex

Use a stdio MCP server entry that invokes:

```bash
graphlens serve
```

GraphLens stores its database and logs in `.graphlens/` relative to the working directory where the assistant launches the server.

## Recommended Workflow

1. Run `graphlens build .` before starting an assistant session.
2. Run `graphlens snapshot --out .graphlens/before.json` before large refactors.
3. Use `graphlens watch .` during active development if you want incremental updates.
4. Run `graphlens clean --yes` when you want to discard local graph state.

## Troubleshooting

If tools return empty results, confirm the graph exists:

```bash
graphlens stats
```

If parser packages are missing, install the project dependencies:

```bash
pip install -e ".[dev]"
```

If the visualization is blank, rebuild the graph:

```bash
graphlens rebuild .
graphlens viz --no-open-browser
```
