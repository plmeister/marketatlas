#!/bin/bash
export PATH="$HOME/.local/bin:$PATH"
exec bash -lc 'set -euo pipefail
TAG="paper-test-v1"
BASE="$HOME/.local/share/marketatlas/paper-runs"
REPO_DIR="$BASE/$TAG"
SHARED_DATA="$HOME/src/marketatlas/data/study"
LOG_DIR="$HOME/.local/share/marketatlas/paper-logs/$TAG"
mkdir -p "$BASE" "$LOG_DIR" "$HOME/.local/share/marketatlas/data"
if [ ! -d "$REPO_DIR" ]; then git clone https://github.com/plmeister/marketatlas.git "$REPO_DIR"; fi
cd "$REPO_DIR"
git fetch --all --tags --force
git checkout --detach "refs/tags/$TAG"
mkdir -p data study
ln -sfn "$SHARED_DATA" data/study
cp -f "$HOME/src/marketatlas/run_paper_cached_persist.py" "$REPO_DIR/run_paper_cached.py"
cp -f "$HOME/src/marketatlas/refresh_cache_persist.py" "$REPO_DIR/refresh_cache.py"
cp -f "$HOME/src/marketatlas/study/execution_causal.py" "$REPO_DIR/study/execution_causal.py" 2>/dev/null || true
cd "$HOME/src/marketatlas"
$HOME/.local/bin/poetry run python "$REPO_DIR/run_paper_cached.py" >> "$LOG_DIR/results.jsonl" 2>&1
'
