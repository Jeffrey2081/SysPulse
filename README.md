# ⚡ SysPulse — Real-Time PC Hardware Monitor & Mobile Remote

<div align="center">

![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-cyan.svg)
![Android](https://img.shields.io/badge/Android-APK%20%2F%20PWA-green.svg)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows-blueviolet.svg)

**Monitor your PC's CPU, RAM, Disk usage, Free & Total storage, and pending updates in real time from your phone on the same Wi-Fi network.**

*Featuring a modern tabbed mobile frontend, 60fps glowing Canvas telemetry graphs, cross-distro setup scripts, terminal QR code pairing, and remote 1-tap system updates.*

</div>

---

## 📸 Screenshots & Highlights

- **5-Tab Mobile Architecture**:
  1. **Dashboard**: Live radial gauges for CPU %, RAM %, and Storage %; real-time dual activity sparklines; storage allocation bar; specs badge.
  2. **Detailed Graphs**: High-performance Canvas Bezier curves with neon gradient fills, per-core micro-bars (Core 0 to N), RAM history, and Network bandwidth (Upload/Download KB/s).
  3. **Storage & Disks**: Physical storage deduplication (accurately handles Btrfs subvolumes and multi-mount disks without double-counting) and per-partition meters.
  4. **Updates & Remote Control**: Automatic package manager detection (`pacman`, `checkupdates`, `yay`, `apt`, `dnf`, `winget`), pending package version diffs, remote 1-tap "Update PC Now" trigger, live streaming update terminal, and PC power controls (Lock, Reboot, Shutdown).
  5. **Settings & Pairing**: Instant PIN pairing, in-app camera QR code scanner, telemetry frequency slider (0.5s–5.0s), temperature units (°C/°F), and APK download.

---

## 🚀 Quick Start Guide

### 🐧 Linux (Arch, Omarchy, Debian, Ubuntu, Fedora, openSUSE)

SysPulse includes a universal setup script that automatically detects your Linux distribution, prepares an isolated Python environment, enables a persistent `systemd` user service, and displays your pairing QR code:

```bash
git clone https://github.com/YOUR_USERNAME/SysPulse.git
cd SysPulse
./scripts/install.sh
```

- **Auto-starts on Boot**: The installer creates a `systemd --user` service that automatically runs in the background.
- **Zero Root Required**: Runs in user space without requiring root passwords.
- **Service Management**:
  ```bash
  systemctl --user status syspulse
  systemctl --user restart syspulse
  systemctl --user stop syspulse
  ```

#### Optional: Passwordless Remote Updates
To allow SysPulse to upgrade packages from your phone without entering a sudo password on your PC:
- **Arch / Omarchy**:
  ```bash
  echo "$USER ALL=(ALL) NOPASSWD: /usr/bin/pacman -Syu --noconfirm" | sudo tee /etc/sudoers.d/syspulse-updater
  ```
- **Debian / Ubuntu**:
  ```bash
  echo "$USER ALL=(ALL) NOPASSWD: /usr/bin/apt-get update, /usr/bin/apt-get upgrade -y" | sudo tee /etc/sudoers.d/syspulse-updater
  ```
- **Fedora**:
  ```bash
  echo "$USER ALL=(ALL) NOPASSWD: /usr/bin/dnf upgrade -y" | sudo tee /etc/sudoers.d/syspulse-updater
  ```

---

### 🪟 Windows (10 / 11)

Run the included PowerShell installer (or double-click `scripts\install.bat`):

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
.\scripts\install.ps1
```

- Detects Windows version, installs Python via `winget` if missing.
- Sets up virtual environment and installs dependencies.
- Configures silent startup in the Windows Startup folder.
- Displays the terminal ASCII pairing QR code.

---

## 📲 Pairing Your Phone

When the agent starts, it prints a terminal banner with an ASCII QR code:

```text
================================================================
      ⚡ SYSPULSE - PC HARDWARE MONITOR & REMOTE CONTROL ⚡
================================================================
 PC Name:       jeff-PC
 Local IP:      192.168.1.21
 Port:          53317
 Pairing PIN:   284621
 Pairing URL:   http://192.168.1.21:53317/?token=...&host=jeff-PC
----------------------------------------------------------------
 SCAN THIS QR CODE WITH YOUR PHONE CAMERA OR SYSPULSE APP:
----------------------------------------------------------------
  [ HIGH-CONTRAST ASCII QR CODE DISPLAYED HERE ]
----------------------------------------------------------------
```

### 3 Ways to Connect:
1. **Camera QR Scan**: Point your phone camera at the terminal QR code. It opens SysPulse in your phone browser, pre-authenticated.
2. **Mobile Browser (PWA)**: Navigate to `http://<PC-LOCAL-IP>:53317` on your phone browser (e.g. `http://192.168.1.21:53317`) and enter the 6-digit PIN. Tap **"Add to Home Screen"** to install it as a standalone app.
3. **Native Android APK**: Install `syspulse.apk` and scan or enter your PIN.

---

## 📦 Building the Android APK (.apk)

SysPulse includes a standalone Android project in `android/` and an automated zero-bloat compilation script:

```bash
./scripts/build_apk.sh
```

- Uses Android SDK command-line tools (`aapt2`, `d8`, `zipalign`, `apksigner`).
- Targets modern Android with `targetSdkVersion 34` (fully compatible with Android 14, 15, 16, and 17).
- Produces a signed, lightweight `syspulse.apk` (~140 KB) at `android/dist/syspulse.apk`.
- Hosted directly by your PC at `http://<PC-LOCAL-IP>:53317/download/syspulse.apk`.

---

## 🏗️ Architecture

```text
 ┌────────────────────────────────────────────────────────┐
 │                      YOUR PHONE                        │
 │  ┌──────────────────────────────────────────────────┐  │
 │  │        SysPulse Mobile App (APK or PWA)          │  │
 │  │  [Dashboard] [Graphs] [Storage] [Updates] [Set]  │  │
 │  └────────────────────────┬─────────────────────────┘  │
 └───────────────────────────┼────────────────────────────┘
                             │ Local Wi-Fi (WebSocket + REST)
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │                     YOUR PC (AGENT)                    │
 │  ┌──────────────────────────────────────────────────┐  │
 │  │            FastAPI + asyncio + psutil            │  │
 │  │       Telemetry • WebSockets • Updates Worker    │  │
 │  └────────────────────────┬─────────────────────────┘  │
 │                           │                            │
 │  ┌────────────────────────┴─────────────────────────┐  │
 │  │ Package Managers: pacman / checkupdates / yay    │  │
 │  │                   apt / dnf / winget             │  │
 │  └──────────────────────────────────────────────────┘  │
 └────────────────────────────────────────────────────────┘
```

---

## 🔌 API Reference

### REST Endpoints
- `GET /api/info` - Hostname, OS platform, auth requirement.
- `GET /api/pair?pin=<PIN>` - Validates PIN and returns authentication token.
- `GET /api/metrics` - Complete snapshot of CPU, RAM, Disk, Storage, Network, and Top Processes.
- `GET /api/updates?force=<bool>` - Fetches pending updates list and count.
- `POST /api/updates/apply` - Triggers background system upgrade (optional `sudo_password`).
- `GET /api/updates/status` - Live execution state (`idle`, `running`, `success`, `error`) and console logs.
- `POST /api/power` - Remote power trigger (`lock`, `reboot`, `shutdown`).
- `GET /api/qr` - Generated pairing QR image.
- `GET /download/syspulse.apk` - Direct APK binary download.

### WebSocket Stream
- `WS /ws?token=<TOKEN>&pin=<PIN>` - High-frequency live telemetry push every 1000ms (client-configurable interval).

---

## 📄 License

MIT License. Free to use, modify, and distribute.
