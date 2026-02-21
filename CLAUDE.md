# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is firemd

firemd is a CLI tool that converts URLs to clean Markdown using a locally running [Firecrawl](https://github.com/mendableai/firecrawl) instance via Docker Compose. It supports single URL scraping, website crawling, batch scraping from URL files, proxy configuration, automatic server lifecycle management, smart resume via JSONL manifests, and retry logic with exponential backoff.

## Commands

```bash
# Install dependencies (uses uv)
uv pip install -e ".[dev]"

# Run all tests
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/test_retry.py -v

# Run a single test class or method
uv run pytest tests/test_retry.py::TestIsPermanentError -v
uv run pytest tests/test_retry.py::TestIsPermanentError::test_429_is_retryable -v

# Lint
uv run ruff check src/

# Lint with auto-fix
uv run ruff check src/ --fix
```

## Architecture

All source code is in `src/firemd/` using a `src`-layout with hatchling as the build backend. Entry point: `firemd.cli:main`.

### Module responsibilities

- **cli.py** — Typer CLI with commands: `scrape` (default command, also triggered by passing a URL/file directly), `crawl` (website crawling with link following), `proxy` (configure proxy URL), and `server` (subcommands: install, up, stop, down, status, logs, doctor). The `main()` function auto-inserts `scrape` when the first arg isn't a known subcommand or flag.
- **firecrawl.py** — `FirecrawlClient` HTTP client (context manager) for the Firecrawl v1 API. Handles single scrape (`POST /v1/scrape`), batch scrape (`POST /v1/batch/scrape` + polling), and sequential scraping with per-URL retry. Contains `with_retry()` generic retry helper, `is_permanent_error()` and `is_success()` classifiers, and data classes `ScrapeResult` and `BatchJob`.
- **server.py** — `ServerManager` wraps Docker Compose operations for the Firecrawl stack. Key method: `ensure()` starts the server if needed and returns whether the caller should stop it later. Stores Firecrawl in `~/.local/share/firemd/firecrawl/` (via platformdirs).
- **outputs.py** — Filename generation (`make_filename`) using `{index_}{host}_{path_slug}__{sha1_hash}.md` scheme, and `write_markdown()` with optional YAML front matter.
- **manifest.py** — JSONL manifest for tracking scrape progress (`manifest.jsonl`) and permanent errors (`errors.jsonl`). Enables resume: on re-run, URLs with `status: "ok"` and 2xx `http_status` are skipped.
- **config.py** — Constants (API URL defaults, health endpoint, repo URL), platformdirs-based path helpers, and proxy configuration (parse/load/save/clear proxy URL from `~/.config/firemd/.env`).
- **util.py** — `is_url()` detection, `parse_url_file()` for reading URL lists, `get_output_dir()` logic.

### Key data flow

1. CLI parses input (URL or file) → determines output dir
2. `ServerManager.ensure()` starts Firecrawl Docker stack if needed
3. `FirecrawlClient` scrapes URLs (sequential with retry or batch mode)
4. `ScrapeResult` → `write_markdown()` saves .md file + `save_manifest_entry()` appends to manifest
5. Failed URLs get end-of-run retry; permanent failures go to `errors.jsonl`
6. Server is stopped/downed based on lifecycle policy

## Code style

- Ruff with rules E, F, I, W at 100 char line length, targeting Python 3.10+
- Tests use pytest with class-based grouping (e.g., `TestMakeFilename`, `TestIsPermanentError`)
- Dataclasses for data models (`ScrapeResult`, `BatchJob`, `ManifestEntry`, `ServerStatus`)
- Rich for CLI output (console, progress bars, tables)
