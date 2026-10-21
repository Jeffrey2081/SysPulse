#!/usr/bin/env bash
# ==============================================================================
# SysPulse Universal Linux Setup & Installer
# Automatically detects Linux distributions (Arch, Debian, Ubuntu, Fedora, etc.)
# Sets up Python virtual environment, dependencies, and systemd service.
# ==============================================================================

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${CYAN}${BOLD}"
echo "================================================================"
echo "          ⚡ SYSPULSE UNIVERSAL LINUX INSTALLER ⚡             "
echo "================================================================"
echo -e "${NC}"

# 1. Detect Operating System Distribution
DISTRO="unknown"
DISTRO_FAMILY="unknown"

if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO="${NAME:-$ID}"
    case "$ID" in
        arch|omarchy|manjaro|endeavouros)
            DISTRO_FAMILY="arch"
            ;;
        ubuntu|debian|linuxmint|pop)
            DISTRO_FAMILY="debian"
            ;;
        fedora|rhel|centos|rocky|alma)
            DISTRO_FAMILY="fedora"
            ;;
        opensuse*|sles)
            DISTRO_FAMILY="suse"
            ;;
        alpine)
            DISTRO_FAMILY="alpine"
            ;;
        *)
            # Check ID_LIKE fallback
            if [[ "$ID_LIKE" =~ "arch" ]]; then
                DISTRO_FAMILY="arch"
            elif [[ "$ID_LIKE" =~ "debian" ]] || [[ "$ID_LIKE" =~ "ubuntu" ]]; then
                DISTRO_FAMILY="debian"
            elif [[ "$ID_LIKE" =~ "rhel" ]] || [[ "$ID_LIKE" =~ "fedora" ]]; then
                DISTRO_FAMILY="fedora"
            fi
            ;;
    esac
fi

echo -e "${GREEN}✓ Detected OS:${NC} ${BOLD}${DISTRO}${NC} (Family: ${DISTRO_FAMILY})"

# 2. Check Python 3
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}✗ Python 3 not found.${NC} Please install python3 using your package manager:"
    case "$DISTRO_FAMILY" in
        arch) echo "  sudo pacman -S python python-pip" ;;
        debian) echo "  sudo apt update && sudo apt install -y python3 python3-pip python3-venv" ;;
        fedora) echo "  sudo dnf install -y python3 python3-pip" ;;
        *) echo "  Install python3 and python3-venv" ;;
    esac
    exit 1
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}✓ Python Version:${NC} ${PY_VER}"

# 3. Determine Project Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_ROOT/venv"

# 4. Set Up Python Virtual Environment
echo -e "${CYAN}→ Setting up isolated Python environment...${NC}"
if command -v uv &>/dev/null; then
    echo -e "${GREEN}✓ Found uv.${NC} Fast-installing dependencies..."
    uv venv "$VENV_DIR" --allow-existing
    uv pip install --python "$VENV_DIR/bin/python" -r "$PROJECT_ROOT/server/requirements.txt"
else
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "$PROJECT_ROOT/server/requirements.txt"
fi

echo -e "${GREEN}✓ Dependencies installed successfully.${NC}"

# 5. Create Systemd User Service (Runs automatically on login/boot)
echo -e "${CYAN}→ Configuring systemd background service...${NC}"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"

SERVICE_FILE="$SYSTEMD_USER_DIR/syspulse.service"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=SysPulse Hardware Monitor & Remote Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_ROOT/server
ExecStart=$VENV_DIR/bin/python main.py
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable syspulse.service
systemctl --user restart syspulse.service

echo -e "${GREEN}✓ SysPulse service enabled and started!${NC}"

# 6. Optional: Passwordless sudoers rule for system updates
echo ""
echo -e "${YELLOW}Notice on Remote Updates:${NC}"
echo "To allow SysPulse to execute system updates from your phone without typing"
echo "your PC password, you can optionally install a sudoers rule."
echo "If you wish to do this, run:"
case "$DISTRO_FAMILY" in
    arch)
        echo -e "  ${BOLD}echo '$USER ALL=(ALL) NOPASSWD: /usr/bin/pacman -Syu --noconfirm' | sudo tee /etc/sudoers.d/syspulse-updater${NC}"
        ;;
    debian)
        echo -e "  ${BOLD}echo '$USER ALL=(ALL) NOPASSWD: /usr/bin/apt-get update, /usr/bin/apt-get upgrade -y' | sudo tee /etc/sudoers.d/syspulse-updater${NC}"
        ;;
    fedora)
        echo -e "  ${BOLD}echo '$USER ALL=(ALL) NOPASSWD: /usr/bin/dnf upgrade -y' | sudo tee /etc/sudoers.d/syspulse-updater${NC}"
        ;;
    *)
        echo "  Configure your package manager in /etc/sudoers.d/"
        ;;
esac

echo ""
# 7. Print Pairing QR Code & Info
sleep 1
"$VENV_DIR/bin/python" "$PROJECT_ROOT/server/pairing.py"

echo ""
echo -e "${GREEN}${BOLD}Setup Complete!${NC}"
echo "You can manage the SysPulse service with:"
echo "  systemctl --user status syspulse"
echo "  systemctl --user restart syspulse"
echo "  systemctl --user stop syspulse"
