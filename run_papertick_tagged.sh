#!/bin/bash
export PATH="$HOME/.local/bin:$PATH"
TAG="${1:-paper-test-v1-causal-2}"
BASE="${HOME}/.local/share/marketatlas/paper-runs"
REPO_DIR="${BASE}/${TAG}-tick"
SHARED_DATA="${HOME}/src/marketatlas/data/study"
LOG_DIR="${HOME}/.local/share/marketatlas/paper-logs/${TAG}"
mkdir -p "${BASE}" "${LOG_DIR}" "${HOME}/.local/share/marketatlas/data"

# 1. Refresh the shared study data to the latest available bar (--force so the
#    snapshot never freezes; see study/fetch_history.py). Non-fatal: if the
#    feed is down the tick still runs against whatever data is present.
cd /home/scott/src/marketatlas
{
  echo "=== $(date -Is) fetch_history --force ==="
  /home/scott/.local/bin/poetry run python study/fetch_history.py --force
} >> "${LOG_DIR}/fetch.log" 2>&1

# 2. Check out the pinned tag into an isolated run dir and tick.
if [ ! -d "${REPO_DIR}/.git" ]; then
  git clone git@github.com:plmeister/marketatlas.git "${REPO_DIR}"
fi
cd "${REPO_DIR}"
git fetch --all --tags --force
git checkout --detach "refs/tags/${TAG}"
mkdir -p data study
ln -sfn "${SHARED_DATA}" data/study
cd /home/scott/src/marketatlas
PAPER_TAG="${TAG}" /home/scott/.local/bin/poetry run python "${REPO_DIR}/paper_tick.py"
