"""
SysPulse Pairing & Discovery Manager
Generates pairing tokens, QR codes (terminal ASCII & PNG), and manages configuration.
"""

import os
import sys
import json
import secrets
import socket
import qrcode
from pathlib import Path
from typing import Dict, Any, List

CONFIG_DIR = Path.home() / ".config" / "syspulse"
CONFIG_FILE = CONFIG_DIR / "config.json"

def get_lan_ips() -> List[str]:
    """Finds all non-loopback IPv4 addresses."""
    ips = []
    try:
        # Standard UDP socket trick to get primary routing IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        # Doesn't actually send packet
        s.connect(('10.255.255.255', 1))
        primary_ip = s.getsockname()[0]
        s.close()
        if primary_ip and not primary_ip.startswith("127."):
            ips.append(primary_ip)
    except Exception:
        pass

    # Secondary check through hostname
    try:
        host_ip = socket.gethostbyname(socket.gethostname())
        if host_ip and not host_ip.startswith("127.") and host_ip not in ips:
            ips.append(host_ip)
    except Exception:
        pass

    if not ips:
        ips.append("127.0.0.1")
    return ips

def load_or_create_config() -> Dict[str, Any]:
    """Loads existing config or generates new secure token and PIN."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                if "token" in data and "pin" in data:
                    return data
        except Exception:
            pass

    # Create new config
    token = secrets.token_urlsafe(24)
    pin = f"{secrets.randbelow(900000) + 100000}"  # 6-digit PIN
    config_data = {
        "port": 53317,
        "token": token,
        "pin": pin,
        "created_at": secrets.token_hex(4)
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(config_data, f, indent=2)
    return config_data

def generate_pairing_info(port: int = None) -> Dict[str, Any]:
    """Generates pairing URL, displays terminal ASCII QR code, and generates pairing PNG."""
    config = load_or_create_config()
    if port is None:
        port = int(config.get("port", 53317))
    ips = get_lan_ips()
    primary_ip = ips[0]
    hostname = socket.gethostname()
    
    # Construct pairing URL
    pairing_url = f"http://{primary_ip}:{port}/?token={config['token']}&host={hostname}"
    
    # Generate QR Code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(pairing_url)
    qr.make(fit=True)

    # Save QR image
    qr_img_path = CONFIG_DIR / "pairing_qr.png"
    try:
        img_qr = qrcode.make(pairing_url)
        img_qr.save(qr_img_path)
    except Exception:
        pass

    return {
        "hostname": hostname,
        "ip": primary_ip,
        "all_ips": ips,
        "port": port,
        "token": config["token"],
        "pin": config["pin"],
        "url": pairing_url,
        "qr_path": str(qr_img_path),
        "qr_ascii": qr
    }

def print_pairing_banner(info: Dict[str, Any]):
    """Renders a gorgeous terminal welcome and pairing banner."""
    print("=" * 64)
    print("      ⚡ SYSPULSE - PC HARDWARE MONITOR & REMOTE CONTROL ⚡")
    print("=" * 64)
    print(f" PC Name:       {info['hostname']}")
    print(f" Local IP:      {info['ip']}")
    print(f" Port:          {info['port']}")
    print(f" Pairing PIN:   {info['pin']}")
    print(f" Pairing URL:   {info['url']}")
    print("-" * 64)
    print(" SCAN THIS QR CODE WITH YOUR PHONE CAMERA OR SYSPULSE APP:")
    print("-" * 64)
    try:
        # Print ASCII QR
        info["qr_ascii"].print_ascii(invert=True)
    except Exception:
        pass
    print("-" * 64)
    print(f" Access directly from your phone browser or app at:")
    print(f" 👉  {info['url']}")
    print("=" * 64)

if __name__ == "__main__":
    info = generate_pairing_info()
    print_pairing_banner(info)
