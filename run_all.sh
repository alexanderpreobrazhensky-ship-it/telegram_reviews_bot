#!/usr/bin/env bash
set -euo pipefail

python main.py &
reviews_pid=$!

python bots/client_bot/main.py &
client_pid=$!

terminate() {
  kill "${reviews_pid}" "${client_pid}" 2>/dev/null || true
}

trap terminate SIGINT SIGTERM

wait -n "${reviews_pid}" "${client_pid}"
status=$?

terminate
wait || true

exit "${status}"
