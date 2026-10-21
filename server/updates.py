"""
SysPulse Updates Manager
Detects pending system updates and triggers remote updates across Linux distros & Windows.
"""

import os
import sys
import shutil
import platform
import subprocess
import threading
import time
from typing import List, Dict, Any, Optional

class UpdateManager:
    def __init__(self):
        self.os_type = platform.system().lower()
        self.pkg_manager = self._detect_pkg_manager()
        self._cache_time = 0
        self._cache_data: Optional[Dict[str, Any]] = None
        self._cache_ttl = 120  # Cache for 2 minutes
        
        # Async execution state
        self.is_updating = False
        self.update_status = "idle"  # idle, running, success, error
        self.update_logs: List[str] = []
        self.update_start_time = 0
        self.update_end_time = 0
        self._lock = threading.Lock()

    def _detect_pkg_manager(self) -> str:
        """Detect the system's package manager."""
        if self.os_type == "windows":
            if shutil.which("winget"):
                return "winget"
            return "powershell_wu"

        if self.os_type == "linux":
            # Check Arch-based
            if shutil.which("checkupdates") or shutil.which("pacman"):
                return "pacman"
            # Check Debian/Ubuntu-based
            if shutil.which("apt-get"):
                return "apt"
            # Check Fedora/RHEL
            if shutil.which("dnf"):
                return "dnf"
            # Check openSUSE
            if shutil.which("zypper"):
                return "zypper"
            # Check Alpine
            if shutil.which("apk"):
                return "apk"

        return "unknown"

    def get_pending_updates(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch pending system updates and return a structured list."""
        now = time.time()
        if not force_refresh and self._cache_data and (now - self._cache_time < self._cache_ttl):
            return self._cache_data

        updates_list = []
        error_msg = None

        try:
            if self.pkg_manager == "pacman":
                updates_list = self._check_pacman_updates()
            elif self.pkg_manager == "apt":
                updates_list = self._check_apt_updates()
            elif self.pkg_manager == "dnf":
                updates_list = self._check_dnf_updates()
            elif self.pkg_manager == "winget":
                updates_list = self._check_winget_updates()
            else:
                error_msg = f"Unsupported package manager: {self.pkg_manager}"
        except Exception as e:
            error_msg = str(e)

        result = {
            "pkg_manager": self.pkg_manager,
            "os_type": self.os_type,
            "update_count": len(updates_list),
            "packages": updates_list,
            "error": error_msg,
            "checked_at": now
        }

        self._cache_data = result
        self._cache_time = now
        return result

    def _check_pacman_updates(self) -> List[Dict[str, str]]:
        packages = []
        cmd = None
        if shutil.which("checkupdates"):
            cmd = ["checkupdates"]
        else:
            cmd = ["pacman", "-Qu"]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
            for line in res.stdout.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                # Format: "pkgname old_version -> new_version"
                parts = line.split()
                if len(parts) >= 4 and parts[2] == "->":
                    packages.append({
                        "name": parts[0],
                        "current_version": parts[1],
                        "new_version": parts[3]
                    })
                elif len(parts) >= 2:
                    packages.append({
                        "name": parts[0],
                        "current_version": parts[1] if len(parts) > 1 else "",
                        "new_version": parts[2] if len(parts) > 2 else ""
                    })
        except Exception:
            pass
        return packages

    def _check_apt_updates(self) -> List[Dict[str, str]]:
        packages = []
        try:
            res = subprocess.run(
                ["apt", "list", "--upgradable"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30
            )
            for line in res.stdout.strip().splitlines():
                if "Listing..." in line or not line:
                    continue
                # Format: "pkg/jammy 2.0.1 amd64 [upgradable from: 1.9.0]"
                parts = line.split()
                if parts:
                    name = parts[0].split("/")[0]
                    new_ver = parts[1] if len(parts) > 1 else ""
                    cur_ver = ""
                    if "upgradable from:" in line:
                        cur_ver = line.split("upgradable from:")[-1].replace("]", "").strip()
                    packages.append({
                        "name": name,
                        "current_version": cur_ver,
                        "new_version": new_ver
                    })
        except Exception:
            pass
        return packages

    def _check_dnf_updates(self) -> List[Dict[str, str]]:
        packages = []
        try:
            # dnf check-update returns exit code 100 when updates exist
            res = subprocess.run(
                ["dnf", "check-update", "-q"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=45
            )
            for line in res.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 3 and not line.startswith("Obsoleting"):
                    packages.append({
                        "name": parts[0],
                        "current_version": "",
                        "new_version": parts[1]
                    })
        except Exception:
            pass
        return packages

    def _check_winget_updates(self) -> List[Dict[str, str]]:
        packages = []
        try:
            res = subprocess.run(
                ["winget", "upgrade"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=45
            )
            lines = res.stdout.strip().splitlines()
            start_parsing = False
            for line in lines:
                if "---" in line:
                    start_parsing = True
                    continue
                if start_parsing and line.strip():
                    parts = line.split()
                    if len(parts) >= 3:
                        packages.append({
                            "name": parts[0],
                            "current_version": parts[1],
                            "new_version": parts[2]
                        })
        except Exception:
            pass
        return packages

    def trigger_update(self, sudo_password: Optional[str] = None) -> bool:
        """
        Launches system update in a background thread and streams logs.
        Returns True if started, False if already running.
        """
        with self._lock:
            if self.is_updating:
                return False
            self.is_updating = True
            self.update_status = "running"
            self.update_logs = ["Initiating system update..."]
            self.update_start_time = time.time()
            self.update_end_time = 0

        thread = threading.Thread(target=self._run_update_process, args=(sudo_password,), daemon=True)
        thread.start()
        return True

    def _run_update_process(self, sudo_password: Optional[str] = None):
        """Worker thread to execute package manager update."""
        cmd = []
        env = os.environ.copy()

        if self.pkg_manager == "pacman":
            # Check if running as root or sudo
            if os.geteuid() == 0:
                cmd = ["pacman", "-Syu", "--noconfirm"]
            else:
                # Use sudo -n or password pipe
                cmd = ["sudo", "-n", "pacman", "-Syu", "--noconfirm"]
        elif self.pkg_manager == "apt":
            env["DEBIAN_FRONTEND"] = "noninteractive"
            if os.geteuid() == 0:
                cmd = ["bash", "-c", "apt-get update && apt-get upgrade -y"]
            else:
                cmd = ["sudo", "-n", "bash", "-c", "apt-get update && apt-get upgrade -y"]
        elif self.pkg_manager == "dnf":
            if os.geteuid() == 0:
                cmd = ["dnf", "upgrade", "-y"]
            else:
                cmd = ["sudo", "-n", "dnf", "upgrade", "-y"]
        elif self.pkg_manager == "winget":
            cmd = ["winget", "upgrade", "--all", "--include-unknown", "--accept-package-agreements", "--accept-source-agreements"]

        if not cmd:
            with self._lock:
                self.update_logs.append(f"Error: No update command configured for {self.pkg_manager}")
                self.update_status = "error"
                self.is_updating = False
                self.update_end_time = time.time()
            return

        with self._lock:
            self.update_logs.append(f"Running: {' '.join(cmd)}")

        input_data = None
        if sudo_password and "sudo" in cmd and "-n" in cmd:
            # Replace -n with -S to read password from stdin
            cmd = [c if c != "-n" else "-S" for c in cmd]
            input_data = f"{sudo_password}\n"

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE if input_data else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )

            if input_data and proc.stdin:
                try:
                    proc.stdin.write(input_data)
                    proc.stdin.flush()
                except Exception:
                    pass

            for line in iter(proc.stdout.readline, ''):
                clean_line = line.strip()
                if clean_line:
                    with self._lock:
                        # Keep the last 150 lines of logs
                        self.update_logs.append(clean_line)
                        if len(self.update_logs) > 150:
                            self.update_logs.pop(0)

            proc.stdout.close()
            return_code = proc.wait()

            with self._lock:
                if return_code == 0:
                    self.update_status = "success"
                    self.update_logs.append("System update completed successfully!")
                else:
                    self.update_status = "error"
                    self.update_logs.append(f"Process terminated with exit code {return_code}")
                # Invalidate updates cache so next query reflects updated packages
                self._cache_data = None
        except Exception as e:
            with self._lock:
                self.update_status = "error"
                self.update_logs.append(f"Update failed with exception: {str(e)}")
        finally:
            with self._lock:
                self.is_updating = False
                self.update_end_time = time.time()

    def get_update_status(self) -> Dict[str, Any]:
        """Returns the current state and latest logs of the update process."""
        with self._lock:
            return {
                "is_updating": self.is_updating,
                "status": self.update_status,
                "logs": list(self.update_logs),
                "started_at": self.update_start_time,
                "ended_at": self.update_end_time,
                "duration_seconds": round((self.update_end_time or time.time()) - self.update_start_time, 1) if self.update_start_time else 0
            }

# Global singleton
update_manager = UpdateManager()

if __name__ == "__main__":
    print(f"Detected Package Manager: {update_manager.pkg_manager}")
    print("Checking pending updates...")
    res = update_manager.get_pending_updates(force_refresh=True)
    print(f"Pending updates count: {res['update_count']}")
    for pkg in res['packages'][:5]:
        print(f" - {pkg['name']}: {pkg['current_version']} -> {pkg['new_version']}")
