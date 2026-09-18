#!/usr/bin/env bash
# Launch the DE Health sector exporter UI.
#
# Creates a lightweight .venv (reusing system packages) on first run, and
# rebuilds it automatically when it was built by an unsupported Python.
#
# Python 3.9 or newer is required. macOS ships 3.9.6 as /usr/bin/python3, so a
# plain `python3` is usually fine, but the newest interpreter available wins.
set -e
cd "$(dirname "$0")"

VENV_DIR=".venv"
VENV_PYTHON="$VENV_DIR/bin/python"

# True when the interpreter exists and is Python 3.9+.
supports_app() {
  command -v "$1" >/dev/null 2>&1 || return 1
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1
}

version_of() {
  "$1" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || echo "unknown"
}

# Reuse the existing environment only when its interpreter works and has pip.
venv_ready() {
  supports_app "$VENV_PYTHON" || return 1
  "$VENV_PYTHON" -m pip --version >/dev/null 2>&1
}

if ! venv_ready; then
  if [ -e "$VENV_DIR" ]; then
    echo "Rebuilding $VENV_DIR (it used an unsupported Python or has no pip)..."
    rm -rf "$VENV_DIR"
  fi

  BASE_PYTHON=""
  for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 \
                   /opt/homebrew/bin/python3 /usr/local/bin/python3 python3 python3.9 /usr/bin/python3; do
    if supports_app "$candidate"; then
      BASE_PYTHON="$candidate"
      break
    fi
  done

  if [ -z "$BASE_PYTHON" ]; then
    echo "No Python 3.9+ interpreter found on this machine."
    echo "Install one (for example 'brew install python@3.12' or https://www.python.org/downloads/) and re-run this script."
    exit 1
  fi

  echo "Creating $VENV_DIR with $BASE_PYTHON ($(version_of "$BASE_PYTHON"))..."
  "$BASE_PYTHON" -m venv --system-site-packages "$VENV_DIR"

  if ! "$BASE_PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    echo "Note: Python 3.9 works, but 3.10+ installs the newest pandas/Streamlit."
  fi
fi

if [ ! -x "$VENV_DIR/bin/streamlit" ]; then
  echo "Installing dependencies from requirements.txt..."
  "$VENV_PYTHON" -m pip install --quiet --upgrade pip
  "$VENV_PYTHON" -m pip install --quiet -r requirements.txt
fi

echo "Launching Streamlit with $("$VENV_PYTHON" --version 2>&1 | tr -d '\n')"
exec "$VENV_DIR/bin/streamlit" run app.py "$@"
