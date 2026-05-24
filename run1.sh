#!/bin/bash
mkdir -p /tmp/xrp_scanner_data/logs /tmp/xrp_scanner_data/large_scans
export PORT=${PORT:-5000}
export PYTHONUNBUFFERED=1
gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 2 --timeout 300 backend.app:app
