#!/usr/bin/env bash
set -euo pipefail

RUN_CLIENT_BOT=${RUN_CLIENT_BOT:-1}
RUN_REVIEWS_BOT=${RUN_REVIEWS_BOT:-0}

pids=()

if [[ "${RUN_REVIEWS_BOT}" == "1" ]]; then
  echo "Starting reviews_bot..."
  python main.py &
  pids+=("$!")
fi

if [[ "${RUN_CLIENT_BOT}" == "1" ]]; then
  echo "Starting client_bot..."
  python bots/client_bot/main.py &
  pids+=("$!")
fi

if [[ ${#pids[@]} -eq 0 ]]; then
  echo "Nothing to run. Set RUN_CLIENT_BOT=1 or RUN_REVIEWS_BOT=1."
  exit 1
fi

terminate() {
  for pid in "${pids[@]}"; do
    kill "${pid}" 2>/dev/null || true
  done
}

trap terminate SIGINT SIGTERM

wait -n "${pids[@]}"
status=$?

terminate
wait || true

exit "${status}"
