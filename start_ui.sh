#!/usr/bin/env bash
# Launch the DE Health sector exporter UI.
# Creates a lightweight .venv (reusing system packages) on first run.
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/streamlit ]; then
  echo "Setting up .venv (reusing system packages)…"
  python3 -m venv --system-site-packages .venv
  .venv/bin/python -m pip install --quiet -r requirements.txt
fi

exec .venv/bin/streamlit run app.py