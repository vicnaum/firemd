# firemd

**Local Firecrawl → Markdown CLI**

Convert URLs to clean Markdown using a locally running [Firecrawl](https://github.com/mendableai/firecrawl) instance via Docker Compose.

## Features

- **Single URL scraping**: `firemd https://example.com`
- **Batch scraping** from URL files with progress tracking
- **Auto server lifecycle**: starts Firecrawl on-demand, stops after scraping
- **Smart resume**: skips already-processed URLs by default
- **YAML front matter** option for metadata
- **Collision-resistant filenames** with stable hashes
- **Manifest tracking** in JSONL format

## Requirements

- **A running Docker environment** (required):
  - **Docker Desktop**: `https://www.docker.com/products/docker-desktop/`
  - **OrbStack (macOS)**: `https://orbstack.dev/`
- **Git** (for initial Firecrawl setup)
- **Python 3.10+** (handled automatically by `uv`)

## Installation

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install firemd globally
uv tool install git+https://github.com/vicnaum/firemd
uv tool update-shell  # If PATH needs updating
```

For local development:

```bash
git clone https://github.com/vicnaum/firemd
cd firemd
uv tool install . --force
```

## Quick Start

### 0) Make sure Docker is running

Firecrawl runs as a Docker Compose stack. `firemd` can’t start containers unless a Docker engine is running (Docker Desktop / OrbStack / etc).

Quick check:

```bash
docker info
```

### 1) One-time setup (install Firecrawl locally)

```bash
# Install Firecrawl locally (clones repo, configures Docker)
firemd server install
```

### 2) Scraping URLs

```bash
# Scrape a single URL
firemd https://example.com

# Scrape with YAML front matter
firemd https://example.com --front-matter

# Scrape to a specific directory
firemd https://example.com --out ./scraped/

# Scrape multiple URLs from a file (skips already processed by default)
firemd urls.txt

# Force re-scrape all URLs (overwrite existing)
firemd urls.txt --overwrite
```

### URL File Format

Create a text file with one URL per line:

```text
# Comments start with #
https://example.com/page1
https://example.com/page2
https://example.org/docs

# Blank lines are ignored
```

## Optional: server management (advanced)

You usually don’t need these — `firemd` will start Firecrawl on-demand and stop it after scraping by default.

```bash
firemd server up         # Start the server (e.g. keep it warm)
firemd server stop       # Stop (containers remain for fast restart)
firemd server down       # Stop and remove containers
firemd server status     # Check server status
firemd server logs -f    # Follow logs
firemd server doctor     # Run diagnostics
```

### Server lifecycle policies

By default, `firemd` auto-starts the server if needed and stops it after scraping. Control this with flags:

```bash
# Don't auto-start (require running server)
firemd https://example.com --server never

# Keep server running after scrape
firemd https://example.com --server always

# Remove containers after scrape (slower next start)
firemd https://example.com --lifecycle down
```

## Output

### Filename Format

Files are named with a collision-resistant scheme:

```
{host}_{path_slug}__{hash10}.md
```

For batch scraping with index:

```
{index}_{host}_{path_slug}__{hash10}.md
```

Examples:
- `example.com__a1b2c3d4e5.md`
- `0001_docs.python.org_tutorial__f6g7h8i9j0.md`

### Manifest

Batch scraping creates `manifest.jsonl` to track progress:

```json
{"url":"https://example.com","file":"example.com__abc123.md","status":"ok","ts":"2024-01-01T12:00:00","title":"Example"}
{"url":"https://error.example","file":"","status":"error","ts":"2024-01-01T12:00:01","error":"Connection timeout"}
```

By default, `firemd` skips URLs with `status: "ok"` entries. Use `--overwrite` to re-scrape.

### Front Matter

With `--front-matter`, files include YAML metadata:

```markdown
---
url: https://example.com/page
title: "Page Title"
scraped_at: 2024-01-01T12:00:00+00:00
status_code: 200
---

# Page content starts here...
```

## CLI Reference

```
firemd [OPTIONS] <INPUT>
firemd server <COMMAND>

Arguments:
  INPUT              URL or path to file containing URLs

Options:
  --version  -V      Show version
  --help             Show help
  --out      -o      Output directory
  --front-matter     Add YAML front matter
  --verbose  -v      Verbose output
  --api              API URL (default: http://127.0.0.1:3002)
  --overwrite -f     Re-scrape URLs even if already processed
  --server           Server policy: auto|never|always
  --lifecycle        After scrape: stop|down|keep

Server Commands:
  firemd server install   Install Firecrawl locally
  firemd server up        Start the server
  firemd server stop      Stop the server
  firemd server down      Stop and remove containers
  firemd server status    Show server status
  firemd server logs      Show server logs
  firemd server doctor    Run diagnostics
```

## Troubleshooting

### "Docker not found" or "Docker daemon not running"

Install Docker or OrbStack and ensure it's running:

```bash
# Check Docker status
docker info

# On macOS with OrbStack
orb start
```

### "Server not reachable"

1. Check if Firecrawl is installed: `firemd server status`
2. Start the server: `firemd server up`
3. Check logs: `firemd server logs`

### "Port 3002 in use"

Another service is using port 3002. Stop it or configure a different port:

```bash
# Check what's using the port
lsof -i :3002

# Use a different port (requires editing .env)
```

### Build Fails

If `firemd server up` fails during build:

1. Ensure you have enough disk space
2. Try rebuilding: `firemd server up --build`
3. Check Docker logs for specific errors

## Development

```bash
# Clone the repo
git clone https://github.com/vicnaum/firemd
cd firemd

# Install in development mode
uv pip install -e ".[dev]"

# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check src/
```

## Architecture

```
firemd/
├── src/firemd/
│   ├── cli.py        # Typer CLI commands
│   ├── config.py     # Paths and defaults
│   ├── server.py     # ServerManager (Docker Compose)
│   ├── firecrawl.py  # FirecrawlClient (HTTP API)
│   ├── outputs.py    # Filename generation, file writing
│   ├── manifest.py   # JSONL manifest handling
│   └── util.py       # URL detection, file parsing
└── tests/
```

## License

MIT
