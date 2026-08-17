"""
Shared startup and launch helpers for Pokemon TCG Live Monitor.
"""

from __future__ import annotations

import os
import subprocess
import sys
import winreg
from pathlib import Path

VERSION = "2.3"
TASK_NAME = "PokemonTCGLiveMonitor_v2.3"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VALUE = "PokemonTCGLiveMonitor"
LEGACY_TASK_NAMES = (
    "PokemonTCGLiveMonitor_v2",
    "PokemonTCGLiveMonitor_v2.1",
    "PokemonTCGLiveMonitor_v2.2",
    "StartTCGLiveMonitor",
)
MONITOR_SCRIPT_NAME = "TCGLiveMonitor.py"


def find_install_root(explicit_base: str | os.PathLike[str] | None = None) -> Path:
    """Locate the monitor install root from likely script/exe locations."""
    candidates: list[Path] = []

    if explicit_base:
        base = Path(explicit_base).resolve()
        candidates.extend([base, base.parent])

    exe_dir = Path(sys.executable).resolve().parent
    script_dir = Path(__file__).resolve().parent
    candidates.extend(
        [
            exe_dir,
            script_dir,
            exe_dir.parent,
            script_dir.parent,
            Path(os.environ.get("USERPROFILE", "C:\\")) / "PokemonTCGLiveMonitor",
        ]
    )

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / MONITOR_SCRIPT_NAME).exists():
            return candidate
    return script_dir


def venv_python(root: str | os.PathLike[str], windowed: bool = False) -> Path | None:
    exe_name = "pythonw.exe" if windowed else "python.exe"
    candidate = Path(root) / ".venv" / "Scripts" / exe_name
    return candidate if candidate.exists() else None


def resolve_python(root: str | os.PathLike[str], windowed: bool = False) -> Path | None:
    python = venv_python(root, windowed=windowed)
    if python:
        return python

    current_python = Path(sys.executable).resolve()
    current_name = current_python.name.lower()

    if windowed:
        if current_name == "pythonw.exe" and current_python.exists():
            return current_python
        pythonw = current_python.with_name("pythonw.exe")
        return pythonw if pythonw.exists() else None

    if current_name == "pythonw.exe":
        python = current_python.with_name("python.exe")
        if python.exists():
            return python

    return current_python if current_python.exists() else None


def monitor_script(root: str | os.PathLike[str]) -> Path:
    return Path(root) / MONITOR_SCRIPT_NAME


def build_headless_command(root: str | os.PathLike[str]) -> tuple[Path | None, Path, str]:
    python = resolve_python(root, windowed=True)
    script = monitor_script(root)
    command = f'"{python}" "{script}" --headless' if python else ""
    return python, script, command


def is_task_registered(task_name: str = TASK_NAME) -> bool:
    result = subprocess.run(
        ["schtasks", "/query", "/tn", task_name],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def is_registry_registered() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as key:
            winreg.QueryValueEx(key, REG_VALUE)
            return True
    except FileNotFoundError:
        return False


def add_registry(root: str | os.PathLike[str]) -> tuple[bool, str | None]:
    python, script, command = build_headless_command(root)
    if not python:
        return False, "pythonw.exe was not found."
    if not script.exists():
        return False, f"{MONITOR_SCRIPT_NAME} was not found."

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as key:
            winreg.SetValueEx(key, REG_VALUE, 0, winreg.REG_SZ, command)
        return True, None
    except Exception as exc:
        return False, str(exc)


def remove_registry() -> tuple[bool, str | None]:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, REG_VALUE)
        return True, None
    except FileNotFoundError:
        return True, None
    except Exception as exc:
        return False, str(exc)


def add_task(root: str | os.PathLike[str]) -> tuple[bool, str | None]:
    python, script, command = build_headless_command(root)
    if not python:
        return False, "pythonw.exe was not found."
    if not script.exists():
        return False, f"{MONITOR_SCRIPT_NAME} was not found."

    result = subprocess.run(
        [
            "schtasks",
            "/create",
            "/tn",
            TASK_NAME,
            "/tr",
            command,
            "/sc",
            "onlogon",
            "/rl",
            "highest",
            "/f",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True, None
    return False, (result.stderr or result.stdout or "Unknown error").strip()


def remove_task() -> tuple[bool, list[str], list[str]]:
    removed: list[str] = []
    errors: list[str] = []
    task_names = (TASK_NAME, *LEGACY_TASK_NAMES)

    for task_name in task_names:
        result = subprocess.run(
            ["schtasks", "/delete", "/tn", task_name, "/f"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            removed.append(task_name)
            continue

        message = (result.stderr or result.stdout or "").lower()
        if "cannot find the file" in message or "cannot find the path" in message:
            continue
        errors.append(f"{task_name}: {(result.stderr or result.stdout).strip()}")

    return not errors, removed, errors


def enable_startup(root: str | os.PathLike[str] | None = None) -> dict:
    install_root = find_install_root(root)
    reg_ok, reg_error = add_registry(install_root)
    task_ok, task_error = add_task(install_root)
    return {
        "root": install_root,
        "registry_ok": reg_ok,
        "registry_error": reg_error,
        "task_ok": task_ok,
        "task_error": task_error,
        "registry_enabled": is_registry_registered(),
        "task_enabled": is_task_registered(),
    }


def disable_startup() -> dict:
    reg_ok, reg_error = remove_registry()
    task_ok, removed_tasks, task_errors = remove_task()
    return {
        "registry_ok": reg_ok,
        "registry_error": reg_error,
        "task_ok": task_ok,
        "removed_tasks": removed_tasks,
        "task_errors": task_errors,
        "registry_enabled": is_registry_registered(),
        "task_enabled": is_task_registered(),
    }


def launch_monitor(
    root: str | os.PathLike[str] | None = None,
    *,
    headless: bool,
) -> dict:
    install_root = find_install_root(root)
    python = resolve_python(install_root, windowed=headless)
    if not python:
        return {"ok": False, "error": "Python executable was not found.", "root": install_root}

    script = monitor_script(install_root)
    if not script.exists():
        return {
            "ok": False,
            "error": f"{MONITOR_SCRIPT_NAME} was not found in {install_root}",
            "root": install_root,
        }

    command = [str(python), str(script)]
    if headless:
        command.append("--headless")

    kwargs = {"cwd": str(install_root)}
    if os.name == "nt" and not headless:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)

    subprocess.Popen(command, **kwargs)
    return {
        "ok": True,
        "root": install_root,
        "python": str(python),
        "script": str(script),
        "headless": headless,
    }
