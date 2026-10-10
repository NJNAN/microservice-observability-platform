#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
exec python scripts/manage.py up "$@"
