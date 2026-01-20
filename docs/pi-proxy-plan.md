# Pi Proxy Server Plan

## Overview

Add a lightweight proxy server that runs on the Pi 5, handling Wake-on-LAN for the desktop when voice requests come in from Tasker.

## Why Suspend (S3) Over Shutdown

| State | Wake time | Power | Models loaded? | Hardware wear |
|-------|-----------|-------|----------------|---------------|
| Always-on | 0s | 100W+ | Yes | High (thermal, fans) |
| Suspend (S3) | 2-5s | 5-10W | **Yes (in RAM)** | Low |
| Hibernate (S4) | 15-25s | 0W | No | Medium (SSD writes) |
| Shutdown (S5) | 30-60s | 0W | No | Medium (thermal cycling) |

**Suspend is ideal because:**
- GPU enters low-power state, fans stop (reduces wear)
- Models stay loaded in RAM (instant readiness)
- No SSD write wear from hibernation
- Fewer thermal cycles than full shutdown/boot
- 2-5 second wake time vs 30-60s

## Architecture

```
Phone (Tasker)
    │
    │ POST /voice (audio)
    ▼
Pi 5 (always-on proxy)
    │
    ├─► Check desktop /health
    │       │
    │       ├─► Online? Forward immediately
    │       │
    │       └─► Offline? Send WOL, poll until ready
    │
    ▼
Desktop (voice-agent server)
    │
    └─► Whisper + Claude + Kokoro
            │
            ▼
        Audio response back through chain
```

## Pi Proxy Server

### Dependencies

- `fastapi` + `uvicorn`
- `wakeonlan` (pip package)
- `httpx` (async HTTP client)

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Pi's own health check |
| `POST /voice` | Main endpoint - receives audio, wakes desktop if needed, forwards request |

### Core Logic

```python
# Pseudocode for /voice endpoint

async def process_voice(audio: bytes):
    # 1. Quick check if desktop is already awake
    if await check_desktop_health(timeout=0.5):
        return await forward_to_desktop(audio)

    # 2. Desktop is sleeping - wake it
    send_wol(DESKTOP_MAC)

    # 3. Poll until ready (or timeout)
    for _ in range(30):  # 60 seconds max
        await asyncio.sleep(2)
        if await check_desktop_health(timeout=1):
            return await forward_to_desktop(audio)

    # 4. Failed to wake
    raise HTTPException(503, "Desktop failed to wake")
```

### Configuration (env vars)

| Variable | Description | Example |
|----------|-------------|---------|
| `DESKTOP_MAC` | Desktop's MAC address for WOL | `AA:BB:CC:DD:EE:FF` |
| `DESKTOP_URL` | Desktop voice-agent URL | `http://192.168.1.100:8000` |
| `WOL_TIMEOUT` | Max seconds to wait for wake | `60` |
| `WOL_POLL_INTERVAL` | Seconds between health checks | `2` |

## Desktop Setup

### 1. Enable Wake-on-LAN

**BIOS:**
- Enter BIOS setup
- Find power management / wake settings
- Enable "Wake on LAN" or "Wake on PCI-E"

**Linux (persist across reboots, works for both shutdown AND suspend):**

Create `/etc/systemd/system/wol.service`:
```ini
[Unit]
Description=Enable Wake-on-LAN
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/sbin/ethtool -s eth0 wol g

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable wol.service
sudo systemctl start wol.service
```

### 2. Auto-start voice-agent on boot

Create `/etc/systemd/system/voice-agent.service`:
```ini
[Unit]
Description=Voice Agent Server
After=network.target

[Service]
Type=simple
User=kevin
WorkingDirectory=/home/kevin/coding/voice-agent
ExecStart=/home/kevin/.local/bin/uv run uvicorn voice_agent.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable voice-agent.service
```

### 3. Auto-suspend after idle

Suspend desktop after N minutes of no voice requests.

**Option A: Simple file-based approach**
```bash
# In voice-agent, touch file on each request
touch /tmp/voice-agent-active

# Cron job (every 5 min) suspends if file older than 30 min
*/5 * * * * find /tmp/voice-agent-active -mmin +30 -exec systemctl suspend \;
```

**Option B: Systemd idle timer**
```bash
# Suspend after 30 min of no user activity
sudo systemctl enable suspend-then-hibernate.target
```

**Option C: In-app background task**
- Track last request timestamp
- Async task checks every minute, calls `systemctl suspend` if idle > threshold
- Most control, can add exceptions (e.g., don't suspend during certain hours)

## File Structure

```
pi-proxy/
├── pyproject.toml
├── .env
└── src/
    └── pi_proxy/
        ├── __init__.py
        └── main.py      # FastAPI app (~60 lines)
```

## Testing Checklist

- [ ] WOL wakes desktop from suspend: `systemctl suspend` then `wakeonlan AA:BB:CC:DD:EE:FF`
- [ ] WOL wakes desktop from shutdown (backup): `shutdown now` then `wakeonlan ...`
- [ ] Models still loaded after wake from suspend (check logs - no "Loading model" messages)
- [ ] Desktop voice-agent starts automatically on boot
- [ ] Pi proxy detects desktop already awake (no unnecessary WOL delay)
- [ ] Pi proxy wakes suspended desktop successfully
- [ ] Auto-suspend triggers after idle timeout
- [ ] Tasker receives audio response through full chain
- [ ] Full round-trip latency acceptable (target: <20s including Claude API)

## Future Considerations

1. **Model preloading on cold boot** - If desktop fully shuts down (power loss, etc.), models need 10-30s to load. Suspend avoids this, but health check handles it as fallback.

2. **Multiple desktops** - Could add fallback to second machine if primary fails to wake.

3. **Sleep scheduling** - Don't auto-sleep during certain hours, or have different timeouts day/night.

4. **Metrics** - Track wake times, success rates, latency breakdown.
