#!/bin/bash
set -euo pipefail
cd /home/scott/src/marketatlas
poetry run python refresh_cache_persist.py >> ~/.local/share/marketatlas/data/refresh_cache.log 2>&1
