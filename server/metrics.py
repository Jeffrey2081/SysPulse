"""
SysPulse Metrics Collector
Collects CPU, RAM, Disk, Network, System Info, and Processes across Linux & Windows.
"""

import os
import sys
import time
import socket
import platform
import psutil

# Cache for rate calculations (disk and network speed)
_last_check_time = None
_last_disk_io = None
_last_net_io = None

def get_cpu_model() -> str:
    """Detect CPU brand/model across Linux and Windows."""
    try:
        if platform.system() == "Windows":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            model, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            return model.strip()
        elif platform.system() == "Linux":
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "Unknown CPU"

def get_cpu_temp() -> float | None:
    """Retrieve primary CPU temperature if sensors are available."""
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return None
        # Common temperature sensors on Linux
        for name in ("k10temp", "coretemp", "cpu_thermal", "acpitz", "zenpower"):
            if name in temps and temps[name]:
                return round(temps[name][0].current, 1)
        # Fallback to first available temperature
        for entries in temps.values():
            if entries:
                return round(entries[0].current, 1)
    except Exception:
        pass
    return None

def get_storage_metrics() -> dict:
    """
    Collects per-drive storage and deduplicated total storage.
    Prevents counting the same physical device/btrfs filesystem multiple times.
    """
    partitions = psutil.disk_partitions(all=False)
    seen_devices = set()
    drives = []
    total_bytes = 0
    used_bytes = 0
    free_bytes = 0

    # Excluded filesystem types
    ignored_fstypes = {"squashfs", "tmpfs", "devtmpfs", "overlay", "iso9660"}

    for part in partitions:
        if part.fstype.lower() in ignored_fstypes:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
            
            # Format single drive
            drive_info = {
                "mountpoint": part.mountpoint,
                "device": part.device,
                "fstype": part.fstype,
                "total_gb": round(usage.total / (1024 ** 3), 2),
                "used_gb": round(usage.used / (1024 ** 3), 2),
                "free_gb": round(usage.free / (1024 ** 3), 2),
                "percent": usage.percent,
            }
            drives.append(drive_info)

            # Deduplicate by real device or unique filesystem id for total storage aggregation
            dev_key = part.device
            if dev_key not in seen_devices:
                seen_devices.add(dev_key)
                total_bytes += usage.total
                used_bytes += usage.used
                free_bytes += usage.free
        except (PermissionError, FileNotFoundError, OSError):
            continue

    total_gb = round(total_bytes / (1024 ** 3), 2)
    used_gb = round(used_bytes / (1024 ** 3), 2)
    free_gb = round(free_bytes / (1024 ** 3), 2)
    total_percent = round((used_bytes / total_bytes * 100), 1) if total_bytes > 0 else 0.0

    return {
        "total_bytes": total_bytes,
        "used_bytes": used_bytes,
        "free_bytes": free_bytes,
        "total_gb": total_gb,
        "used_gb": used_gb,
        "free_gb": free_gb,
        "percent": total_percent,
        "drives": drives
    }

def format_uptime(seconds: float) -> str:
    """Format uptime in human readable format."""
    secs = int(seconds)
    days, remainder = divmod(secs, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)

def get_system_snapshot() -> dict:
    """
    Gathers a comprehensive snapshot of all system telemetry.
    """
    global _last_check_time, _last_disk_io, _last_net_io

    current_time = time.time()
    dt = (current_time - _last_check_time) if _last_check_time else 1.0
    if dt <= 0:
        dt = 1.0

    # --- CPU ---
    cpu_percent = psutil.cpu_percent(interval=None)
    per_cpu = psutil.cpu_percent(interval=None, percpu=True)
    cpu_freq = psutil.cpu_freq()
    cpu_model = get_cpu_model()
    cpu_temp = get_cpu_temp()

    cpu_data = {
        "percent": cpu_percent,
        "per_core": per_cpu,
        "logical_cores": psutil.cpu_count(logical=True),
        "physical_cores": psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True),
        "freq_current_mhz": round(cpu_freq.current, 1) if cpu_freq else None,
        "freq_max_mhz": round(cpu_freq.max, 1) if cpu_freq and cpu_freq.max > 0 else None,
        "model": cpu_model,
        "temperature_c": cpu_temp
    }

    # --- RAM / Memory ---
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    memory_data = {
        "total_bytes": vm.total,
        "used_bytes": vm.used,
        "free_bytes": vm.free,
        "available_bytes": vm.available,
        "percent": vm.percent,
        "total_gb": round(vm.total / (1024 ** 3), 2),
        "used_gb": round(vm.used / (1024 ** 3), 2),
        "free_gb": round(vm.free / (1024 ** 3), 2),
        "available_gb": round(vm.available / (1024 ** 3), 2),
        "swap_total_gb": round(sm.total / (1024 ** 3), 2),
        "swap_used_gb": round(sm.used / (1024 ** 3), 2),
        "swap_percent": sm.percent
    }

    # --- Storage / Disk ---
    storage_data = get_storage_metrics()

    # Disk I/O speed
    current_disk_io = psutil.disk_io_counters()
    disk_read_kb_s = 0.0
    disk_write_kb_s = 0.0
    if _last_disk_io and current_disk_io:
        read_diff = current_disk_io.read_bytes - _last_disk_io.read_bytes
        write_diff = current_disk_io.write_bytes - _last_disk_io.write_bytes
        disk_read_kb_s = round((read_diff / dt) / 1024, 1)
        disk_write_kb_s = round((write_diff / dt) / 1024, 1)
    _last_disk_io = current_disk_io
    storage_data["io"] = {
        "read_kb_s": max(0.0, disk_read_kb_s),
        "write_kb_s": max(0.0, disk_write_kb_s)
    }

    # --- Network ---
    current_net_io = psutil.net_io_counters()
    net_down_kb_s = 0.0
    net_up_kb_s = 0.0
    if _last_net_io and current_net_io:
        recv_diff = current_net_io.bytes_recv - _last_net_io.bytes_recv
        sent_diff = current_net_io.bytes_sent - _last_net_io.bytes_sent
        net_down_kb_s = round((recv_diff / dt) / 1024, 1)
        net_up_kb_s = round((sent_diff / dt) / 1024, 1)
    _last_net_io = current_net_io

    # Interfaces IP map
    interfaces = {}
    try:
        if_addrs = psutil.net_if_addrs()
        if_stats = psutil.net_if_stats()
        for if_name, addrs in if_addrs.items():
            is_up = if_stats[if_name].isup if if_name in if_stats else False
            ipv4 = None
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    ipv4 = addr.address
                    break
            if ipv4:
                interfaces[if_name] = {"ip": ipv4, "is_up": is_up}
    except Exception:
        pass

    network_data = {
        "download_kb_s": max(0.0, net_down_kb_s),
        "upload_kb_s": max(0.0, net_up_kb_s),
        "interfaces": interfaces
    }

    # --- System Info ---
    boot_time = psutil.boot_time()
    uptime_sec = current_time - boot_time

    os_pretty = platform.system()
    if os_pretty == "Linux":
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        os_pretty = line.split("=", 1)[1].strip().strip('"')
                        break
        except Exception:
            pass
    elif os_pretty == "Windows":
        os_pretty = f"Windows {platform.release()}"

    # Battery
    battery_info = None
    try:
        battery = psutil.sensors_battery()
        if battery:
            battery_info = {
                "percent": battery.percent,
                "power_plugged": battery.power_plugged
            }
    except Exception:
        pass

    system_data = {
        "hostname": socket.gethostname(),
        "os_name": os_pretty,
        "os_platform": platform.system().lower(),
        "kernel": platform.release(),
        "arch": platform.machine(),
        "uptime_seconds": int(uptime_sec),
        "uptime_formatted": format_uptime(uptime_sec),
        "battery": battery_info,
        "timestamp": current_time
    }

    # --- Top Processes ---
    top_procs = []
    try:
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = p.info
                if info and info['name']:
                    top_procs.append({
                        "pid": info['pid'],
                        "name": info['name'],
                        "cpu": round(info['cpu_percent'] or 0.0, 1),
                        "ram": round(info['memory_percent'] or 0.0, 1)
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        # Sort by CPU usage descending
        top_procs.sort(key=lambda x: x["cpu"], reverse=True)
        top_procs = top_procs[:6]
    except Exception:
        top_procs = []

    _last_check_time = current_time

    return {
        "cpu": cpu_data,
        "memory": memory_data,
        "storage": storage_data,
        "network": network_data,
        "system": system_data,
        "top_processes": top_procs
    }

if __name__ == "__main__":
    import json
    # Warm up CPU measurement
    psutil.cpu_percent(interval=None)
    time.sleep(0.5)
    snapshot = get_system_snapshot()
    print(json.dumps(snapshot, indent=2))
