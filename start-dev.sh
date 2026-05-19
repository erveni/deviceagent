#!/usr/bin/env bash
# Start the device-agent consumer pointed at the deployed DEV RabbitMQ broker.
#
# Heads-up before running:
#  1. The dev broker may hold stale/test messages from teammates.
#     Check before draining:  curl -u admin:<pw> http://18.210.14.130:15672/api/queues
#  2. The 10 phones must be adb-connected (`adb devices`) and socksdroid available.
#  3. Use ./halt.sh (or pkill + force-stop socksdroid) to stop cleanly.

set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -f .env.dev ]]; then
  echo "ERROR: .env.dev not found in $(pwd)" >&2
  exit 1
fi

# Load broker config
set -a
# shellcheck source=.env.dev
source .env.dev
set +a

# Required on macOS framework Python so urllib finds a CA bundle
export SSL_CERT_FILE="$(python3 -c 'import certifi; print(certifi.where())')"

LOG_FILE="${LOG_FILE:-/tmp/consumer_dev_$(date +%Y%m%d_%H%M%S).log}"

echo "Starting solace_consumer.py against dev broker $RABBITMQ_HOST:$RABBITMQ_PORT"
echo "Log: $LOG_FILE"

nohup python3 solace_consumer.py > "$LOG_FILE" 2>&1 &
echo "PID: $!"
echo "Tail the log:  tail -f $LOG_FILE"
