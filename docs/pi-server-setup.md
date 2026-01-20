# Pi Server Setup

## Hardware
- Raspberry Pi 5 8GB
- 32GB SD card (flashed with Pi OS Lite 64-bit)
- 1TB NVMe SSD (flashed with Pi OS Lite 64-bit)
- NVMe base/HAT

## Pre-configured
- SSH enabled
- User: kevin
- Hostname: piserver
- SSH key: authorized

## First Boot (from SD card)

1. Attach NVMe to the base, connect to Pi
2. Insert SD card
3. Connect ethernet + power
4. Wait ~60 seconds for first boot
5. SSH in:
   ```bash
   ssh kevin@piserver.local
   ```

## System Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Update firmware for NVMe boot
sudo rpi-eeprom-update -a
sudo reboot
```

## Switch to NVMe Boot

```bash
# After reboot, set NVMe as primary boot
sudo raspi-config
# Navigate: Advanced Options → Boot Order → NVMe/USB

# Shutdown, remove SD card, power back on
sudo shutdown now
```

## Services to Install

- [ ] Tailscale (VPN/remote access)
- [ ] Claude Code (Pi manager)
- [ ] Icecast (radio station)
- [ ] Music Minion (streaming)
- [ ] Home automation (TBD)
- [ ] Wake-on-LAN script for desktop

## Wake-on-LAN Setup

Install on Pi:
```bash
sudo apt install wakeonlan
```

Create script to wake desktop:
```bash
# Replace XX:XX:XX:XX:XX:XX with desktop's MAC address
wakeonlan XX:XX:XX:XX:XX:XX
```

## Network

- Pi IP: 192.168.88.15 (set static lease on router to keep this)
- Pi: DHCP (consider setting static lease on router)
- Desktop: Enable WoL in BIOS + network adapter settings
