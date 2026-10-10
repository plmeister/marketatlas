#!/usr/bin/env python3
"""Compare last N paper run results against backtest on same window."""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

tag = sys.argv[1] if len(sys.argv)>1 else 'paper-test-v1-causal'
log_dir = Path.home() / '.local/share/marketatlas/paper-logs' / tag
results = log_dir / 'results.jsonl'
if not results.exists():
    print('no results')
    sys.exit(0)
# read last
lines = results.read_text().strip().splitlines()
if not lines: sys.exit(0)
last = json.loads(lines[-1])
print(json.dumps(last))
