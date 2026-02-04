#!/bin/bash
set -e

echo "Building frontend..."
cd "$(dirname "$0")/../chat-ui"
npm run build
cd ..

echo "Syncing to Pi..."
rsync -avz --delete \
  --include='src/' \
  --include='src/voice_agent/' \
  --include='src/voice_agent/__init__.py' \
  --include='src/voice_agent/proxy.py' \
  --exclude='src/voice_agent/*.py' \
  --include='chat-ui/' \
  --include='chat-ui/dist/' \
  --include='chat-ui/dist/**' \
  --exclude='chat-ui/*' \
  --include='Dockerfile.proxy' \
  --include='docker-compose.proxy.yml' \
  --exclude='*' \
  ./ piserver:~/voice-agent/

echo "Building and starting container on Pi..."
ssh piserver "cd ~/voice-agent && docker compose -f docker-compose.proxy.yml up -d --build"

echo ""
echo "Deployed! Access at: https://chat.piserver:8443"
echo ""
echo "NOTE: Conversations are synced via Syncthing, not this script."
echo "      PC: ~/coding/voice-agent/conversations/"
echo "      Pi: ~/voice-agent/conversations/ (or CONVERSATIONS_DIR)"
echo ""
echo "Useful commands:"
echo "  View logs:    ssh piserver 'cd ~/voice-agent && docker compose -f docker-compose.proxy.yml logs -f'"
echo "  Restart:      ssh piserver 'cd ~/voice-agent && docker compose -f docker-compose.proxy.yml restart'"
echo "  Stop:         ssh piserver 'cd ~/voice-agent && docker compose -f docker-compose.proxy.yml down'"
