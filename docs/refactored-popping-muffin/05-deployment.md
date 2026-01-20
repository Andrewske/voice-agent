# Deployment

## Files to Modify/Create
- `chat-ui/package.json` (modify - add build script)
- `chat-ui/vite.config.ts` (modify - build config)
- `src/voice_agent/main.py` (modify - static file serving)
- `docker-compose.yml` (new - on Pi)
- `Dockerfile` (new - on Pi)
- Caddyfile on Pi (modify)

## Implementation Details

### 1. Frontend Build Configuration
In `chat-ui/package.json`, ensure build outputs to correct location:

```json
{
  "scripts": {
    "build": "tsc && vite build",
    "preview": "vite preview"
  }
}
```

In `chat-ui/vite.config.ts`:
```typescript
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000'
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true
  }
})
```

Build command:
```bash
cd chat-ui && npm run build
```

### 2. FastAPI Static File Serving
In `main.py`, add static file mounting after all `/api/*` routes:

```python
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

CHAT_UI_DIR = Path(__file__).parent.parent.parent / "chat-ui" / "dist"

# Mount static assets (must come after API routes)
if CHAT_UI_DIR.exists():
    app.mount("/assets", StaticFiles(directory=CHAT_UI_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    async def serve_spa(path: str = ""):
        """Serve SPA for all non-API routes."""
        return FileResponse(CHAT_UI_DIR / "index.html")
```

Note: All API routes use `/api/` prefix, so no conflict with the catch-all.

### 3. Docker Compose Setup on Pi
Create `~/voice-agent/docker-compose.yml` on the Pi:

```yaml
version: '3.8'

services:
  voice-agent:
    build: .
    restart: unless-stopped
    network_mode: host  # Binds to localhost:8001
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - ./conversations:/app/conversations
      - ./context:/app/context
      - ~/.claude:/root/.claude:ro  # For conversation history access
```

Create `~/voice-agent/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml .
COPY src/ src/
COPY chat-ui/dist/ chat-ui/dist/
COPY voice-agent-config.yaml .
COPY voice-mode.md .

# Install dependencies
RUN uv sync --frozen

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "src.voice_agent.main:app", "--host", "127.0.0.1", "--port", "8001"]
```

### 4. Caddy Configuration
Add to `/etc/caddy/Caddyfile` on the Pi:

```
https://chat.piserver:8443 {
    tls internal
    reverse_proxy localhost:8001
}
```

Reload Caddy:
```bash
sudo systemctl reload caddy
```

### 5. DNS Configuration
Add to client `/etc/hosts` (or use dnsmasq on Pi):

```
100.71.83.95  chat.piserver
```

Or if using dnsmasq on Pi:
```bash
echo "address=/chat.piserver/100.71.83.95" | sudo tee -a /etc/dnsmasq.d/piserver.conf
sudo systemctl restart dnsmasq
```

### 6. Bang Shortcut (Optional)
Add to `~/bang-redirect/app.py` on Pi:

```python
'chat': 'https://chat.piserver:8443/',
```

Then restart: `sudo systemctl restart bang-redirect`

### 7. Build & Deploy Script
Create `scripts/deploy-to-pi.sh`:

```bash
#!/bin/bash
set -e

# Build frontend locally
cd chat-ui
npm run build
cd ..

# Sync to Pi
rsync -avz --delete \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude 'conversations' \
  --exclude 'context' \
  ./ pi:~/voice-agent/

# Rebuild and restart on Pi
ssh pi "cd ~/voice-agent && docker compose up -d --build"

echo "Deployed to https://chat.piserver:8443"
```

## Acceptance Criteria
- [ ] `npm run build` produces `chat-ui/dist/` with all assets
- [ ] Docker container builds and runs on Pi
- [ ] FastAPI serves index.html at root, API at `/api/*`
- [ ] Caddy proxies `chat.piserver:8443` to FastAPI
- [ ] HTTPS works (Caddy internal TLS)
- [ ] Accessible only via Tailscale network
- [ ] Full flow works on Pixel 9
- [ ] `!chat` bang shortcut works

## Dependencies
- Tasks 01-04 complete (full working app locally)
- SSH access to Raspberry Pi
- Docker and Docker Compose on Pi
- Caddy already installed and running on Pi

## Testing

### Local Verification
```bash
cd chat-ui && npm run build
cd .. && uv run uvicorn src.voice_agent.main:app --port 8000
# Open http://localhost:8000
```

### Remote Verification
1. Run `./scripts/deploy-to-pi.sh`
2. On phone (connected to Tailscale):
   - Open `https://chat.piserver:8443` or type `!chat`
   - Verify HTTPS (lock icon)
   - Send test message
   - Verify response streams correctly

### Integration Test
1. Voice chat on phone (existing flow)
2. Open `https://chat.piserver:8443` on same phone
3. Verify voice conversation context is visible
4. Send chat message
5. Verify it appears in conversation log with `[chat]` marker

## Quick Reference

| Action | Command |
|--------|---------|
| Deploy | `./scripts/deploy-to-pi.sh` |
| Logs | `ssh pi "cd ~/voice-agent && docker compose logs -f"` |
| Restart | `ssh pi "cd ~/voice-agent && docker compose restart"` |
| Stop | `ssh pi "cd ~/voice-agent && docker compose down"` |
| Access | `https://chat.piserver:8443` or `!chat` |
