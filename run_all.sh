#!/usr/bin/env bash
set -euo pipefail

echo "Starting unified server (reviews_bot + client_bot WebApp + polling)..."
exec python main.py
