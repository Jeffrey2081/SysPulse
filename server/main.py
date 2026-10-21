"""
SysPulse Server
FastAPI + WebSockets + UDP Discovery + Telemetry & Update Controller
"""

import os
import sys
import json
import asyncio
import socket
import threading
import subprocess
import platform
from pathlib import Path
from typing import Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from metrics import get_system_snapshot
from updates import update_manager
from pairing import load_or_create_config, generate_pairing_info, print_pairing_banner, CONFIG_DIR

CLIENT_DIR = Path(__file__).resolve().parent.parent / "client"
APK_DIR = Path(__file__).resolve().parent.parent / "android" / "dist"

app = FastAPI(title="SysPulse Agent", version="1.0.0")

# Enable CORS for local network and mobile apps
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

config = load_or_create_config()
ACTIVE_TOKEN = config.get("token", "")
ACTIVE_PIN = config.get("pin", "")

# Connected WebSocket clients
connected_websockets: Set[WebSocket] = set()

def verify_token(request: Request, token: Optional[str] = Query(None), pin: Optional[str] = Query(None)):
    """Validates authorization token or PIN."""
    # Check query param token
    if token and token == ACTIVE_TOKEN:
        return True
    if pin and pin == ACTIVE_PIN:
        return True
    
    # Check Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1] == ACTIVE_TOKEN:
            return True

    # Check custom header
    if request.headers.get("X-SysPulse-Token") == ACTIVE_TOKEN:
        return True
    if request.headers.get("X-SysPulse-Pin") == ACTIVE_PIN:
        return True

    raise HTTPException(status_code=401, detail="Unauthorized: Invalid pairing token or PIN")

class UpdateTriggerRequest(BaseModel):
    sudo_password: Optional[str] = None

class PowerActionRequest(BaseModel):
    action: str  # reboot, shutdown, lock

@app.get("/api/info")
async def get_info():
    """Basic unauthenticated info for discovery and pairing check."""
    return {
        "app": "SysPulse",
        "version": "1.0.0",
        "hostname": socket.gethostname(),
        "os": platform.system(),
        "requires_auth": True
    }

@app.get("/api/pair")
async def pair_device(pin: str = Query(...)):
    """Exchange PIN for persistent auth token."""
    if pin == ACTIVE_PIN:
        return {"status": "success", "token": ACTIVE_TOKEN, "hostname": socket.gethostname()}
    raise HTTPException(status_code=403, detail="Invalid pairing PIN")

@app.get("/api/metrics")
async def get_metrics(auth: bool = Depends(verify_token)):
    """Returns instant snapshot of PC metrics."""
    return get_system_snapshot()

@app.get("/api/updates")
async def get_updates(force: bool = Query(False), auth: bool = Depends(verify_token)):
    """Returns list and count of pending updates."""
    return update_manager.get_pending_updates(force_refresh=force)

@app.post("/api/updates/apply")
async def apply_updates(body: UpdateTriggerRequest, auth: bool = Depends(verify_token)):
    """Triggers system update process."""
    success = update_manager.trigger_update(sudo_password=body.sudo_password)
    if not success:
        raise HTTPException(status_code=409, detail="An update process is already currently running")
    return {"status": "started", "message": "System update initiated successfully"}

@app.get("/api/updates/status")
async def get_update_status(auth: bool = Depends(verify_token)):
    """Returns current progress and logs of update execution."""
    return update_manager.get_update_status()

@app.post("/api/power")
async def execute_power_action(body: PowerActionRequest, auth: bool = Depends(verify_token)):
    """Executes remote PC power action (reboot, shutdown, lock)."""
    action = body.action.lower()
    os_name = platform.system().lower()

    if action == "lock":
        if os_name == "linux":
            # Try loginctl then hyprctl/swaymsg then xdg-screensaver
            cmd = "loginctl lock-session || hyprctl dispatch dpms off || xdg-screensaver lock"
            subprocess.Popen(cmd, shell=True)
        elif os_name == "windows":
            subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
        return {"status": "executed", "action": "lock"}

    elif action == "reboot":
        if os_name == "linux":
            subprocess.Popen(["systemctl", "reboot"])
        elif os_name == "windows":
            subprocess.Popen(["shutdown", "/r", "/t", "5"])
        return {"status": "initiated", "action": "reboot"}

    elif action == "shutdown":
        if os_name == "linux":
            subprocess.Popen(["systemctl", "poweroff"])
        elif os_name == "windows":
            subprocess.Popen(["shutdown", "/s", "/t", "5"])
        return {"status": "initiated", "action": "shutdown"}

    raise HTTPException(status_code=400, detail="Invalid power action")

@app.get("/api/qr")
async def get_qr_code():
    """Serves the generated pairing QR image."""
    qr_path = CONFIG_DIR / "pairing_qr.png"
    if qr_path.exists():
        return FileResponse(qr_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="QR image not generated yet")

@app.websocket("/ws")
async def websocket_telemetry_stream(websocket: WebSocket):
    """
    Real-time high-performance telemetry WebSocket stream.
    Clients receive live updates every 1-2 seconds with minimal overhead.
    """
    await websocket.accept()
    
    # Initial auth verification on WS connection
    query_params = dict(websocket.query_params)
    token = query_params.get("token")
    pin = query_params.get("pin")
    
    if token != ACTIVE_TOKEN and pin != ACTIVE_PIN:
        # Check first message for auth payload before disconnecting
        try:
            auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
            if auth_msg.get("token") != ACTIVE_TOKEN and auth_msg.get("pin") != ACTIVE_PIN:
                await websocket.close(code=4001, reason="Authentication failed")
                return
        except Exception:
            await websocket.close(code=4001, reason="Authentication timeout")
            return

    connected_websockets.add(websocket)
    interval = 1.0

    try:
        while True:
            snapshot = get_system_snapshot()
            # If an update is actively running, append update progress
            update_status = update_manager.get_update_status()
            payload = {
                "metrics": snapshot,
                "update_status": update_status
            }
            await websocket.send_json(payload)

            # Check for client messages (e.g. interval changes)
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=interval)
                if "interval" in msg:
                    interval = max(0.5, min(10.0, float(msg["interval"])))
            except asyncio.TimeoutError:
                pass
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        connected_websockets.discard(websocket)

# Direct APK download endpoint
@app.get("/download/syspulse.apk")
async def download_apk():
    """Direct download link for the phone APK file."""
    apk_file = APK_DIR / "syspulse.apk"
    if apk_file.exists():
        return FileResponse(
            apk_file,
            media_type="application/vnd.android.package-archive",
            filename="syspulse.apk"
        )
    raise HTTPException(status_code=404, detail="APK not built yet. Run build_apk.sh to compile.")

# Serve frontend static assets
if CLIENT_DIR.exists():
    app.mount("/", StaticFiles(directory=str(CLIENT_DIR), html=True), name="client")

def run_udp_discovery_responder(port: int = 8889, server_port: int = 8888):
    """
    Background UDP listener for zero-configuration discovery on the local Wi-Fi.
    When mobile app broadcasts SYSPULSE_DISCOVER, agent replies with hostname and port.
    """
    def listener():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('', port))
            hostname = socket.gethostname()
            while True:
                data, addr = sock.recvfrom(1024)
                text = data.decode("utf-8", errors="ignore").strip()
                if "SYSPULSE_DISCOVER" in text:
                    reply = json.dumps({
                        "app": "SysPulse",
                        "hostname": hostname,
                        "port": server_port,
                        "os": platform.system()
                    })
                    sock.sendto(reply.encode("utf-8"), addr)
        except Exception:
            pass

    t = threading.Thread(target=listener, daemon=True)
    t.start()

SERVER_PORT = int(config.get("port", 53317))

def main():
    info = generate_pairing_info(port=SERVER_PORT)
    print_pairing_banner(info)
    run_udp_discovery_responder(port=8889, server_port=SERVER_PORT)

    # Run Uvicorn server on all interfaces (0.0.0.0)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=SERVER_PORT,
        log_level="warning",
        access_log=False
    )

if __name__ == "__main__":
    main()
