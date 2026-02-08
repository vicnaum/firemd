#!/usr/bin/env bash
# Ensure firemd is installed and ready to use.
# Exit codes: 0 = ready, 1 = missing prerequisites, 2 = install failed
set -euo pipefail

check_docker() {
  if ! command -v docker &>/dev/null; then
    echo "ERROR: Docker not found. Install Docker Desktop or OrbStack first."
    echo "  macOS: brew install --cask orbstack   OR   https://www.docker.com/products/docker-desktop/"
    echo "  Linux: https://docs.docker.com/engine/install/"
    return 1
  fi
  if ! docker info &>/dev/null 2>&1; then
    echo "ERROR: Docker daemon not running. Start Docker Desktop or OrbStack."
    return 1
  fi
  return 0
}

check_uv() {
  if command -v uv &>/dev/null; then
    return 0
  fi
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Source the env so uv is available in this session
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  if ! command -v uv &>/dev/null; then
    echo "ERROR: uv installation failed."
    return 1
  fi
}

check_firemd() {
  if command -v firemd &>/dev/null; then
    echo "firemd is already installed: $(firemd --version 2>/dev/null || echo 'version unknown')"
    return 0
  fi
  echo "Installing firemd globally via uv..."
  uv tool install git+https://github.com/vicnaum/firemd 2>&1
  uv tool update-shell 2>/dev/null || true
  # Add uv tools to PATH for this session
  export PATH="$HOME/.local/bin:$HOME/.local/share/uv/tools/bin:$PATH"
  if ! command -v firemd &>/dev/null; then
    echo "ERROR: firemd installation failed."
    return 1
  fi
  echo "firemd installed successfully."
}

check_firecrawl_server() {
  # Check if Firecrawl server is installed (one-time setup)
  local status_output
  status_output=$(firemd server status 2>&1) || true
  if echo "$status_output" | grep -q "Installed.*✗"; then
    echo "Firecrawl server not installed. Running one-time setup..."
    firemd server install
  fi
}

main() {
  echo "=== Ensuring firemd is ready ==="

  check_docker || exit 1
  check_uv || exit 1
  check_firemd || exit 2
  check_firecrawl_server || exit 2

  echo "=== firemd is ready ==="
}

main "$@"
