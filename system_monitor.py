"""Small, dependency-free Linux system metrics collector.

The collector deliberately keeps no history on disk.  It reads procfs/sysfs
and asks nvidia-smi for GPU data when available; callers decide how many
recent samples to retain in memory.
"""
import os
import shutil
import subprocess
import time
from pathlib import Path


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_lines(path):
    try:
        return Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []


def _meminfo():
    values = {}
    for line in _read_lines("/proc/meminfo"):
        key, sep, rest = line.partition(":")
        if not sep:
            continue
        parts = rest.strip().split()
        if parts:
            values[key] = _number(parts[0]) * (1024 if len(parts) > 1 and parts[1].lower() == "kb" else 1)
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    swap_total = values.get("SwapTotal", 0)
    swap_free = values.get("SwapFree", 0)
    return {
        "total": total,
        "available": available,
        "used": max(0, total - available),
        "percent": (max(0, total - available) / total * 100) if total else 0,
        "swap_total": swap_total,
        "swap_used": max(0, swap_total - swap_free),
        "swap_percent": ((max(0, swap_total - swap_free) / swap_total) * 100) if swap_total else 0,
    }


def _cpu_times():
    first = next((line for line in _read_lines("/proc/stat") if line.startswith("cpu ")), "")
    parts = first.split()[1:]
    values = [_number(x) for x in parts]
    total = sum(values)
    idle = (values[3] if len(values) > 3 else 0) + (values[4] if len(values) > 4 else 0)
    return total, idle


def _load_average():
    try:
        return os.getloadavg()[0]
    except (AttributeError, OSError):
        return 0.0


def _temperature():
    values = []
    for path in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        try:
            value = _number(path.read_text().strip()) / 1000
            if 0 < value < 150:
                values.append(value)
        except (OSError, ValueError):
            pass
    for path in Path("/sys/class/hwmon").glob("hwmon*/temp*_input"):
        try:
            value = _number(path.read_text().strip()) / 1000
            if 0 < value < 150:
                values.append(value)
        except (OSError, ValueError):
            pass
    return max(values) if values else None


def _network_bytes():
    total_rx = total_tx = 0
    for line in _read_lines("/proc/net/dev"):
        if ":" not in line:
            continue
        name, data = line.split(":", 1)
        if name.strip() == "lo":
            continue
        columns = data.split()
        if len(columns) >= 9:
            total_rx += int(_number(columns[0]))
            total_tx += int(_number(columns[8]))
    return total_rx, total_tx


def _disk_io():
    read_sectors = write_sectors = 0
    for line in _read_lines("/proc/diskstats"):
        parts = line.split()
        if len(parts) < 14:
            continue
        name = parts[2]
        # Count physical devices and NVMe devices, not their partitions.
        if name.startswith("loop") or name.startswith("ram") or name.startswith("dm-"):
            continue
        if name.startswith("nvme") and "p" in name[name.find("nvme") + 4:]:
            continue
        if name[-1:].isdigit() and not name.startswith("nvme"):
            continue
        read_sectors += int(_number(parts[5]))
        write_sectors += int(_number(parts[9]))
    return read_sectors * 512, write_sectors * 512


def _disks():
    # /proc/mounts escapes spaces and non-ASCII characters using octal codes.
    def unescape(value):
        return value.replace("\\040", " ").replace("\\011", "\t").replace("\\134", "\\")

    pseudo_fs={"autofs","binfmt_misc","bpf","cgroup","cgroup2","configfs","debugfs","devpts","devtmpfs","efivarfs","fusectl","hugetlbfs","mqueue","nsfs","pstore","proc","securityfs","squashfs","sysfs","tmpfs","tracefs"}
    ignored_prefixes=("/proc","/sys","/dev","/run","/snap","/var/lib/docker","/tmp/fuse")
    mounts=[]; seen=set()
    for line in _read_lines("/proc/mounts"):
        fields=line.split()
        if len(fields)<3:continue
        source,target,fstype=map(unescape,fields[:3]); target=target.rstrip("/") or "/"
        if fstype in pseudo_fs or target.startswith(ignored_prefixes) or not os.path.exists(target):continue
        try:usage=shutil.disk_usage(target)
        except OSError:continue
        if not usage.total:continue
        # Bind mounts of the same device and size do not represent another
        # disk; keep the shortest, human-meaningful mount point.
        key=(source.split("[",1)[0],usage.total,usage.used)
        if key in seen:continue
        seen.add(key); mounts.append((target,source,fstype,usage))
    mounts.sort(key=lambda row:(row[0]!="/",row[0].count("/"),row[0]))
    rows = []
    for mount,source,fstype,usage in mounts:
        rows.append({"mount": mount, "source": source, "fstype": fstype, "total": usage.total, "used": usage.used, "free": usage.free, "percent": usage.used / usage.total * 100 if usage.total else 0})
    return rows


def _process_snapshot(previous, previous_time, now):
    rows = []
    hz = os.sysconf("SC_CLK_TCK")
    try:
        entries = Path("/proc").iterdir()
    except OSError:
        return rows
    for directory in entries:
        if not directory.name.isdigit():
            continue
        pid = directory.name
        try:
            stat = (directory / "stat").read_text()
            end = stat.rfind(")")
            fields = stat[end + 2:].split()
            ticks = int(fields[11]) + int(fields[12])
            rss_pages = int(fields[21])
            rss = rss_pages * os.sysconf("SC_PAGE_SIZE")
            command = (directory / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
            if not command:
                command = fields[0] if fields else "进程"
            cpu = 0.0
            if pid in previous and now > previous_time:
                cpu = max(0.0, (ticks - previous[pid]) / hz / (now - previous_time) * 100 / max(1, os.cpu_count() or 1))
            rows.append({"pid": pid, "name": command[:64], "cpu": cpu, "memory": rss})
            previous[pid] = ticks
        except (OSError, ValueError, IndexError):
            continue
    rows.sort(key=lambda row: (row["cpu"], row["memory"]), reverse=True)
    return rows[:8]


def _gpu():
    query = "index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"
    try:
        result = subprocess.run(["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=1.5)
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    rows = []
    for line in result.stdout.splitlines():
        fields = [item.strip() for item in line.split(",")]
        if len(fields) < 7:
            continue
        rows.append({"index": fields[0], "name": fields[1], "percent": _number(fields[2]), "used": _number(fields[3]) * 1024 * 1024, "total": _number(fields[4]) * 1024 * 1024, "temperature": _number(fields[5]), "power": _number(fields[6])})
        rows[-1]["memory_percent"] = rows[-1]["used"] / rows[-1]["total"] * 100 if rows[-1]["total"] else 0
    return rows


class SystemMonitor:
    def __init__(self):
        self._cpu_previous = _cpu_times()
        self._network_previous = _network_bytes()
        self._disk_previous = _disk_io()
        self._process_previous = {}
        self._previous_time = time.monotonic()

    def snapshot(self):
        now = time.monotonic()
        cpu_total, cpu_idle = _cpu_times()
        old_total, old_idle = self._cpu_previous
        total_delta = cpu_total - old_total
        idle_delta = cpu_idle - old_idle
        cpu_percent = max(0, min(100, (total_delta - idle_delta) / total_delta * 100)) if total_delta else 0
        self._cpu_previous = (cpu_total, cpu_idle)
        rx, tx = _network_bytes()
        old_rx, old_tx = self._network_previous
        elapsed = max(0.1, now - self._previous_time)
        self._network_previous = (rx, tx)
        read_bytes, write_bytes = _disk_io()
        old_read, old_write = self._disk_previous
        self._disk_previous = (read_bytes, write_bytes)
        memory = _meminfo()
        gpu = _gpu()
        self._previous_time = now
        return {
            "timestamp": time.time(),
            "cpu": {"percent": cpu_percent, "cores": os.cpu_count() or 1, "load": _load_average(), "temperature": _temperature()},
            "memory": memory,
            "gpu": gpu,
            "disks": _disks(),
            "network": {"download": max(0, rx - old_rx) / elapsed, "upload": max(0, tx - old_tx) / elapsed},
            "disk_io": {"read": max(0, read_bytes - old_read) / elapsed, "write": max(0, write_bytes - old_write) / elapsed},
            "processes": _process_snapshot(self._process_previous, self._previous_time, now),
        }

    @staticmethod
    def empty():
        return {"timestamp": 0, "cpu": {"percent": 0, "cores": os.cpu_count() or 1, "load": 0, "temperature": None}, "memory": {"total": 0, "used": 0, "available": 0, "percent": 0, "swap_total": 0, "swap_used": 0, "swap_percent": 0}, "gpu": [], "disks": [], "network": {"download": 0, "upload": 0}, "disk_io": {"read": 0, "write": 0}, "processes": []}
