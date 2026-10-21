#!/usr/bin/env bash
# ==============================================================================
# SysPulse Uninstaller
# Stops and removes the systemd background service and clean up.
# ==============================================================================

CYAN='\033[0;36m'
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}Stopping and removing SysPulse service...${NC}"

if systemctl --user is-active --quiet syspulse.service 2>/dev/null; then
    systemctl --user stop syspulse.service
fi

if systemctl --user is-enabled --quiet syspulse.service 2>/dev/null; then
    systemctl --user disable syspulse.service
fi

rm -f "$HOME/.config/systemd/user/syspulse.service"
systemctl --user daemon-reload

echo -e "${GREEN}✓ SysPulse background service has been stopped and uninstalled.${NC}"
echo "Configuration files remain in ~/.config/syspulse (delete manually if desired)."
