#!/bin/bash
set -e

SCRIPT_DIR="$(dirname "$0")"

echo "=== Restarting PC server ==="
systemctl --user restart voice-agent
sleep 2
systemctl --user status voice-agent --no-pager | head -5

echo ""
echo "=== Deploying to Pi ==="
"$SCRIPT_DIR/deploy-to-pi.sh"
