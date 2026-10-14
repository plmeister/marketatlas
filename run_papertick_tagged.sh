#!/bin/bash
export PATH="$HOME/.local/bin:$PATH"
TAG="${1:-paper-test-v1-causal-2}"
BASE="${HOME}/.local/share/marketatlas/paper-runs"
REPO_DIR="${BASE}/${TAG}-tick"
SHARED_DATA="${HOME}/src/marketatlas/data/study"
LOG_DIR="${HOME}/.local/share/marketatlas/paper-logs/${TAG}"
mkdir -p "${BASE}" "${LOG_DIR}" "${HOME}/.local/share/marketatlas/data"
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
