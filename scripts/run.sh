#!/usr/bin/env bash
set -euo pipefail
PY=python
command -v python >/dev/null 2>&1 || PY=python3
$PY -m venv .venv
source .venv/bin/activate
$PY -m pip install --upgrade pip
$PY -m pip install -r requirements.txt
$PY -m playwright install --with-deps
$PY scrape.py --dynamic auto
