---
name: firemd
description: "Download websites and web pages as clean Markdown files using the firemd CLI tool (powered by a local Firecrawl instance via Docker). Use when the user wants to: (1) Download a webpage or website as Markdown, (2) Scrape one or more URLs and save as .md files, (3) Batch download a list of URLs to Markdown, (4) Convert web content to Markdown for research, RAG, or archival, (5) Save web documentation locally as Markdown. Triggers on requests involving downloading sites, scraping URLs to Markdown, converting webpages to .md, fetching web content as text, or any mention of firemd."
---

# firemd — Download Websites as Markdown

Convert URLs to clean Markdown files using a locally running Firecrawl instance. Handles single URLs, batch URL lists, automatic server lifecycle, resume, and retry logic.

## Prerequisites

firemd requires **Docker** (Docker Desktop or OrbStack) running on the machine. Run the setup script before first use:

```bash
bash SKILL_DIR/scripts/ensure_firemd.sh
```

This installs `uv` (if needed), `firemd` (globally via `uv tool install`), and runs the one-time Firecrawl server setup. Only needed once per machine — skip if `firemd --version` already works.

## Scraping a Single URL

```bash
firemd https://example.com
```

Output: `example.com__<hash>.md` in the current directory.

To specify an output directory:

```bash
firemd https://example.com --out ./docs/
```

To include YAML front matter (url, title, scraped_at, status_code):

```bash
firemd https://example.com --front-matter
```

## Batch Scraping from a URL List

Create a text file with one URL per line (`#` comments and blank lines are ignored):

```text
# Documentation pages
https://docs.example.com/intro
https://docs.example.com/guide
https://docs.example.com/api
```

Then scrape all of them:

```bash
firemd urls.txt --out ./scraped/
```

Key behaviors:
- Output goes to a directory named after the file stem (e.g., `urls/`) unless `--out` is specified
- Creates `manifest.jsonl` tracking each URL's status — re-runs automatically skip successful URLs
- Use `--overwrite` (`-f`) to force re-scrape
- Files are named `{index}_{host}_{path_slug}__{hash}.md` for batch mode

## Useful Options

| Flag | Effect |
|------|--------|
| `--out DIR` / `-o DIR` | Set output directory |
| `--front-matter` | Add YAML metadata header to each file |
| `--overwrite` / `-f` | Re-scrape even if already in manifest |
| `--verbose` / `-v` | Show detailed progress and retry info |
| `--delay N` | Max random delay between requests (default: 1.0s) |
| `--max-retries N` | Retry attempts for transient errors (default: 5) |
| `--server auto\|never\|always` | Server startup policy (default: auto) |
| `--lifecycle stop\|down\|keep` | What to do with server after scrape (default: stop) |

## Server Management

firemd auto-starts/stops the Firecrawl Docker stack by default. For manual control:

```bash
firemd server status     # Check if server is installed and running
firemd server up         # Start (keep warm for multiple scrapes)
firemd server stop       # Stop containers (fast restart later)
firemd server down       # Remove containers entirely
firemd server doctor     # Run diagnostics if something is wrong
```

To keep the server running across multiple scrape commands:

```bash
firemd https://example.com --server always
```

## Error Handling

- **Permanent errors** (403, 404, etc.) are logged to `errors.jsonl` and not retried
- **Transient errors** (429, 5xx, network errors) are retried with exponential backoff
- After the main pass, all retryable failures get a second attempt with a 30s cooldown
- Re-running the same batch command automatically resumes from where it left off

## Typical Workflow

```bash
# 1. Ensure firemd is installed (first time only)
bash SKILL_DIR/scripts/ensure_firemd.sh

# 2. Single page
firemd https://docs.example.com/page --out ./research/

# 3. Batch: create URL list, then scrape
cat > urls.txt << 'EOF'
https://docs.example.com/intro
https://docs.example.com/guide
https://docs.example.com/reference
EOF
firemd urls.txt --out ./research/ --front-matter --verbose

# 4. Check results
ls ./research/
cat ./research/manifest.jsonl  # See status of each URL
```
