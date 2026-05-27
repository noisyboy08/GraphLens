# GraphLens

GraphLens is a local MCP server that parses a codebase into a structural graph, stores it in SQLite, and serves focused context to AI coding assistants such as Claude Code, Cursor, and Codex.

The core idea is simple: instead of sending an entire repository to an assistant, GraphLens answers questions like "what files matter for this file?", "what calls this function?", and "what is affected by this change?" from a prebuilt dependency graph. That gives assistants smaller, more relevant context windows and helps reduce token usage.

## What It Builds

GraphLens turns source files into a graph:

- Files become module nodes.
- Functions and classes become symbol nodes.
- Imports become dependency edges.
- Function calls become call edges.
- Communities group related areas of the codebase.
- Hubs, bridges, and bottlenecks identify architectural risk.

The graph is stored locally in `.graphlens/graph.db` using SQLite with WAL mode. No cloud service is required.

## Features

- MCP stdio server named `graphlens`
- Tree-sitter based parser with graceful fallbacks
- Python AST parser for precise Python extraction
- Incremental repository builds using SHA-256 change detection
- SQLite graph storage with transactional writes
- NetworkX graph loading for analysis
- Blast radius analysis for changed files
- Community detection with Leiden support and Louvain fallback
- Hub, bridge, and bottleneck detection
- File watcher for incremental updates
- Click CLI
- Offline-capable force-directed visualization
- Local logs in `.graphlens/`

## Supported Inputs

GraphLens maps source files by extension and attempts to load the matching tree-sitter grammar package.

Implemented language detection includes:

- Python
- JavaScript
- TypeScript
- TSX
- Go
- Rust
- Java
- Ruby
- PHP
- C
- C++
- Kotlin
- Swift
- Scala
- Vue
- Svelte
- Lua
- Zig
- Julia
- R
- Nix
- PowerShell
- Perl
- C#
- Solidity
- Jupyter notebooks (`.ipynb`, code cells only)

If a grammar is unavailable, GraphLens logs the issue and uses a generic structural parser where possible instead of crashing.

## Installation

Use Python 3.11 or newer.

```bash
pip install -e ".[dev]"
```

For runtime-only usage:

```bash
pip install -e .
```

GraphLens depends on optional parser grammar packages. Some less common tree-sitter grammar packages may not exist under the exact package names used by the registry. In that case, GraphLens skips or generically parses those files and continues.

## Quick Start

Build a graph for the current repository:

```bash
graphlens build .
```

Print graph statistics:

```bash
graphlens stats
```

Start the MCP server:

```bash
graphlens serve
```

Start the visualization:

```bash
graphlens viz
```

Check whether GraphLens is healthy:

```bash
graphlens doctor
```

Benchmark parse speed and token savings:

```bash
graphlens benchmark .
```

Watch for file changes:

```bash
graphlens watch .
```

Export a graph snapshot:

```bash
graphlens snapshot --out .graphlens/snapshot.json
```

Rebuild from a clean local graph:

```bash
graphlens rebuild .
```

Remove local GraphLens state:

```bash
graphlens clean --yes
```

## Verify Everything Works

Run the full test suite:

```bash
pytest -q
```

Expected result for the current project:

```text
18 passed
```

Smoke test the main CLI flow:

```bash
graphlens rebuild tests/fixtures/sample_python
graphlens snapshot --out .graphlens/test-snapshot.json
graphlens diff --before .graphlens/test-snapshot.json --after .graphlens/test-snapshot.json
graphlens stats
```

Expected behavior:

- `rebuild` parses the fixture project from scratch.
- `snapshot` writes a graph JSON file.
- `diff` reports zero changes when comparing the snapshot to itself.
- `stats` prints file, function, edge, community, health, and token information.

Start the local visualization:

```bash
graphlens viz --no-open-browser
```

Then open:

```text
http://127.0.0.1:7341
```

The visualization is offline-capable and should load graph data from `/api/graph`.

## How To See GraphLens Working

This section walks through GraphLens in simple steps.

### 1. Install The Project

Run this in the project folder:

```bash
pip install -e ".[dev]"
```

This installs GraphLens and the test tools.

### 2. Build The Graph

```bash
graphlens build .
```

This scans your code files, parses functions, classes, imports, and calls, then saves the graph here:

```text
.graphlens/graph.db
```

### 3. Check Stats

```bash
graphlens stats
```

You should see information like:

```text
total_files
total_functions
total_edges
communities
health_score
total_tokens
```

This confirms GraphLens created the code graph.

### 4. Export A Snapshot

```bash
graphlens snapshot --out .graphlens/snapshot.json
```

This creates a JSON version of the graph.

You can inspect it here:

```text
.graphlens/snapshot.json
```

The snapshot contains:

- `nodes`: files, functions, and classes
- `links`: imports and calls

### 5. Open The Graph UI

```bash
graphlens viz
```

Then open:

```text
http://127.0.0.1:7341
```

In the UI:

- circles are files, functions, and classes
- lines are relationships
- colors are communities
- bigger nodes are more connected
- search highlights code symbols
- node type filters can show files, functions, or classes
- edge type filters can show imports or calls
- external dependency nodes can be hidden
- fit-to-screen recenters the visible graph
- clicking a node shows details

### 6. Test Blast Radius

GraphLens can show what files may be affected by a change.

Example:

```bash
python -c "from graphlens.analysis.blast_radius import analyze; print(analyze(['graphlens/cli.py']).to_markdown())"
```

This shows files that may need review if `graphlens/cli.py` changes.

### 7. Start The MCP Server

```bash
graphlens serve
```

This starts GraphLens as an MCP server.

AI coding tools can then ask questions like:

- What files are relevant to this file?
- What calls this function?
- What files are affected by this change?
- What dependencies does this file have?

### 8. Auto Configure AI Tools

```bash
graphlens install
```

This creates:

```text
.claude/mcp.json
.cursor/mcp.json
```

These files tell Claude Code or Cursor how to start GraphLens.

### 9. Watch For Live Changes

```bash
graphlens watch .
```

Now when you edit and save files, GraphLens updates only the changed file instead of rebuilding everything.

### 10. Verify With Tests

```bash
pytest -q
```

Expected result:

```text
18 passed
```

That means parser, graph storage, traversal, blast radius, snapshots, and MCP service logic are working.

### Simple Mental Model

```text
Your codebase
   ↓
Parser reads files
   ↓
Graph builder creates nodes and edges
   ↓
SQLite stores the graph
   ↓
Traversal and analysis answer questions
   ↓
MCP server gives focused context to AI assistants
```

In simple words: instead of an AI reading your whole project, GraphLens helps it read only the files that matter.

## CLI Reference

### `graphlens install`

Creates MCP config files for supported local AI tools:

- `.claude/mcp.json`
- `.cursor/mcp.json`

The generated config points each tool at:

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

### `graphlens build [REPO]`

Parses a repository and writes the graph to `.graphlens/graph.db`.

The builder skips:

- `node_modules`
- `.git`
- `__pycache__`
- `dist`
- `build`
- `.venv`
- `venv`
- `*.min.js`

It uses SHA-256 hashes to skip unchanged files on later builds.

### `graphlens rebuild [REPO]`

Removes `.graphlens/` and then runs a fresh build.

### `graphlens serve`

Runs GraphLens as a stdio MCP server. This is the command AI coding tools should invoke.

### `graphlens watch [REPO]`

Runs a watchdog-based file watcher. On save or create, GraphLens reparses only the changed file, updates SQLite, refreshes the in-memory graph, and reruns community detection.

### `graphlens stats`

Prints summary information such as:

- total files
- total functions
- total edges
- communities
- graph health score
- token efficiency estimate

### `graphlens doctor`

Runs a health check for the local GraphLens setup.

It checks:

- Python version
- important dependencies
- repository path
- `.graphlens/` state directory
- SQLite graph database
- graph contents
- MCP config files
- visualization frontend files

For automation:

```bash
graphlens doctor --json
```

### `graphlens benchmark [REPO]`

Measures parse speed and token savings without replacing the main graph database.

Example:

```bash
graphlens benchmark .
```

It reports:

- files scanned
- files parsed
- time taken
- files per second
- total tokens
- selected context tokens
- token savings
- token reduction ratio

For automation:

```bash
graphlens benchmark . --json
```

### `graphlens viz`

Starts the visualization server on:

```text
http://127.0.0.1:7341
```

The frontend loads graph data from:

```text
/api/graph
```

The visualization is self-contained and does not require a CDN.

### `graphlens snapshot --out SNAPSHOT`

Exports the current graph as JSON:

```bash
graphlens snapshot --out .graphlens/current.json
```

Snapshot files use the same `nodes` and `links` shape as the visualization API.

### `graphlens clean --yes`

Removes `.graphlens/`, including the SQLite database, snapshots, and logs.

### `graphlens diff --before SNAPSHOT --after SNAPSHOT`

Compares two graph snapshot JSON files and reports added and removed nodes and edges.

## MCP Tools

GraphLens exposes six MCP tools.

### `get_relevant_files`

Input:

```json
{
  "file_path": "src/app.py",
  "depth": 2,
  "token_budget": 50000
}
```

Output:

```json
{
  "files": ["src/service.py", "src/models.py"],
  "reason": "BFS dependency context within depth 2",
  "tokens_saved": 12000
}
```

This performs breadth-first graph traversal from all nodes in the requested file and returns nearby files sorted by relevance.

### `get_blast_radius`

Input:

```json
{
  "changed_files": ["src/service.py"]
}
```

Output includes:

- affected files
- related tests
- markdown summary
- risk level

Blast radius follows direct dependents and transitive dependents up to depth 3.

### `get_function_context`

Input:

```json
{
  "function_name": "process_order",
  "file_path": "src/orders.py"
}
```

Output includes:

- callers
- callees
- file path
- line number

### `get_file_dependencies`

Input:

```json
{
  "file_path": "src/orders.py"
}
```

Output includes:

- files imported by this file
- files importing this file
- community label

### `search_codebase`

Input:

```json
{
  "query": "OrderService",
  "limit": 10
}
```

Searches node names and docstrings.

### `get_graph_summary`

Input:

```json
{}
```

Output includes:

- total files
- total functions
- total edges
- communities
- hubs
- health score

## Architecture

```text
graphlens/
  parser/       Language detection and source parsing
  graph/        SQLite storage, graph build, traversal, diff
  analysis/     Blast radius, communities, hubs, health scoring
  mcp/          MCP stdio server
  watch/        Incremental filesystem watcher
  viz/          Local graph visualization server
frontend/       Local graph UI
tests/          Fixtures and unit tests
```

## Parser Pipeline

The parser flow is:

1. Detect language from file extension.
2. Read source as UTF-8 with fallback encodings.
3. Skip binary-looking files.
4. Extract code cells for `.ipynb`.
5. Compute SHA-256 content hash.
6. Parse with the best available parser:
   - Python uses `ast`.
   - Other languages try tree-sitter.
   - If tree-sitter fails, use a generic regex parser.
7. Return a `ParseResult` dataclass.

`ParseResult` contains:

- path
- language
- sha256
- functions
- classes
- imports
- calls
- exports
- errors

Parser errors are recorded in the result and logged, but they do not stop repository builds.

## Storage Model

GraphLens stores data in SQLite.

### `files`

Tracks each parsed file.

```sql
CREATE TABLE files (
  id INTEGER PRIMARY KEY,
  path TEXT UNIQUE,
  sha256 TEXT,
  language TEXT,
  last_parsed TIMESTAMP
);
```

### `nodes`

Stores modules, functions, and classes.

```sql
CREATE TABLE nodes (
  id INTEGER PRIMARY KEY,
  file_id INTEGER,
  node_type TEXT,
  name TEXT,
  line_start INTEGER,
  line_end INTEGER,
  docstring TEXT,
  FOREIGN KEY (file_id) REFERENCES files(id)
);
```

### `edges`

Stores graph relationships.

```sql
CREATE TABLE edges (
  id INTEGER PRIMARY KEY,
  source_node_id INTEGER,
  target_node_id INTEGER,
  edge_type TEXT,
  FOREIGN KEY (source_node_id) REFERENCES nodes(id),
  FOREIGN KEY (target_node_id) REFERENCES nodes(id)
);
```

Supported edge types:

- `calls`
- `imports`
- `inherits`
- `uses`

The current implementation actively writes `calls` and `imports`.

### `communities`

Stores detected community assignments.

```sql
CREATE TABLE communities (
  id INTEGER PRIMARY KEY,
  node_id INTEGER,
  community_id INTEGER,
  label TEXT,
  FOREIGN KEY (node_id) REFERENCES nodes(id)
);
```

## Graph Builder

The graph builder recursively walks a repository, filters unsupported paths, and parses files in parallel with `ThreadPoolExecutor`.

For each file:

1. Compute SHA-256.
2. Check if the stored hash changed.
3. Skip unchanged files.
4. Parse changed files.
5. Upsert the file row.
6. Delete old nodes for that file.
7. Insert module, class, and function nodes.
8. Insert import and call edges.

After build, the SQLite graph can be loaded into NetworkX for analysis. Import edges are resolved to repository files when possible, including relative TypeScript imports like `./util` and Python imports like `from utils import helper`.

## Traversal

Traversal queries are optimized for context selection.

`get_context_for_file(path, depth=2, token_budget=50000)` starts from all nodes in a file and performs BFS over touching edges. It scores nearby files by distance and limits the result by an approximate token budget.

Additional traversal helpers:

- `get_callers(function_name)`
- `get_callees(function_name)`
- `get_imports_of(file_path)`
- `get_dependents(file_path)`

## Blast Radius

Blast radius analysis answers: "If this file changes, what else should be reviewed?"

For each changed file it finds:

- direct dependents
- transitive dependents up to depth 3
- related tests matching `test_*`, `*_test`, or `*_spec`
- top recommended review files
- impact scores from `0.0` to `1.0`

The result can be formatted as markdown for AI consumption.

## Community Detection

GraphLens prefers Leiden community detection through:

- `leidenalg`
- `python-igraph`

If Leiden is unavailable, it falls back to NetworkX Louvain communities.

Community labels are generated from the most common path prefix in each group.

## Hub And Risk Analysis

GraphLens identifies architectural hotspots:

- Hubs: top central nodes by PageRank and degree.
- Bridges: edges whose removal disconnects the graph.
- Bottlenecks: nodes with high betweenness centrality.
- Health score: simple graph quality estimate based on density and isolated nodes.

These are useful for detecting files that may be risky to change or important to review.

## Visualization

The local visualization shows:

- files and functions as nodes
- dependencies as edges
- node color by community
- node size by degree
- search highlighting
- community filter
- click-to-inspect node details
- hover tooltip
- zoom and pan

Run it with:

```bash
graphlens viz
```

It is implemented with local browser APIs, so it works without internet access.

## Logging

Logs are written under `.graphlens/`.

- `.graphlens/graphlens.log`
- `.graphlens/mcp.log`

Logs rotate at 10 MB with backup files.

## Testing

Run:

```bash
pytest -q
```

The test suite covers:

- Python parsing
- TypeScript parsing fallback
- import extraction
- function call extraction
- SHA-256 change detection
- node insertion
- edge insertion
- BFS traversal
- graph building
- blast radius analysis
- related test detection
- impact scoring
- local import resolution
- snapshot export
- graph diffing
- MCP service validation
- MCP summary, search, and token-aware context tools
- doctor checks
- benchmark metrics

Current verified status:

```text
18 tests passing
CLI smoke flow passing
Offline visualization implemented
MCP service methods covered by tests
Doctor and benchmark commands implemented
```

## Development Notes

The implementation is intentionally local-first:

- No cloud database
- No background network service required
- SQLite is the source of truth
- NetworkX is used for in-memory analysis
- MCP runs over stdio

For best results, build the graph before connecting an AI assistant:

```bash
graphlens build .
graphlens install
```

Then configure your assistant to launch:

```bash
graphlens serve
```

See [docs/mcp-setup.md](docs/mcp-setup.md) for assistant-specific setup examples.
See [docs/examples.md](docs/examples.md) for example MCP workflows and prompts.

## Project Readiness

GraphLens includes:

- [LICENSE](LICENSE)
- [CHANGELOG.md](CHANGELOG.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- GitHub Actions CI in `.github/workflows/ci.yml`
- MCP setup docs in [docs/mcp-setup.md](docs/mcp-setup.md)
- MCP usage examples in [docs/examples.md](docs/examples.md)

## Current Limitations

- Cross-language symbol resolution is heuristic.
- Import-to-file resolution handles common local imports but may create external placeholder nodes for packages or dynamic imports.
- Python parsing is precise through `ast`; other languages depend on installed tree-sitter grammars or generic fallback parsing.
- `inherits` and `uses` edge types are reserved in the schema but not fully populated yet.
- Token counting uses `tiktoken` when installed and falls back to a deterministic local tokenizer.

## Roadmap

- More precise per-language query patterns
- Better import resolution by package/module root
- Assistant-specific token profiles
- Richer graph diff output with changed-node metadata
- test-aware blast radius ranking
- persistent daemon mode for watcher and MCP sharing
- More MCP client examples for additional editors
