#!/bin/bash
# Jalankan pengukuran dengan model sungguhan.
# Kunci dibaca dari .env proyek (mode 600, tidak masuk git).
set -euo pipefail
cd /opt/data/nota-ekstrak
set -a
# shellcheck disable=SC1091
source .env
set +a
export RIVER_BASE_URL="${RIVER_BASE_URL:-https://api.river.ai/v1}"
export NOTA_DATA_DIR=/opt/data/nota-ekstrak/data
export PYTHONPATH=/opt/data/nota-ekstrak
exec /opt/data/.venv-nota/bin/python -m eval.score "$@"
