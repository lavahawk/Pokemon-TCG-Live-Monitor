"""
Shared startup and launch helpers for Pokemon TCG Live Monitor.
"""

from __future__ import annotations

import os
import subprocess
import sys
import winreg
from pathlib import Path

TASK_NAME = "PokemonTCGLiveMonitor_v2.4"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VALUE = "PokemonTCGLiveMonitor"
# Old scheduled tasks that should be cleaned up automatically. The registry
# Run key is the primary startup method; scheduled tasks are only a backup.
LEGACY_TASK_NAMES = (
    "PokemonTCGLiveMonitor_v2",
    "PokemonTCGLiveMonitor_v2.1",
    "PokemonTCGLiveMonitor_v2.2",
    "PokemonTCGLiveMonitor_v2.3",
    "StartTCGLiveMonitor",
    "PokemonLiveHelper",
)
MONITOR_SCRIPT_NAME = "TCGLiveMonitor.py"
# Relaunches the monitor every few minutes if it isn't running (killed,
# crashed, closed with the program that started it). Created and kept by the
# monitor itself while auto-start is on.
WATCHDOG_TASK_NAME = "PokemonTCGLiveMonitor_Watchdog"
WATCHDOG_MINUTES = 5
# Written when the user closes the app on purpose: the watchdog leaves it
# closed until the next sign-in or a normal launch.
STOPPED_MARKER = ".monitor_stopped"


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def find_install_root(explicit_base: str | os.PathLike[str] | None = None) -> Path:
    """Locate the monitor install root from likely script/exe locations.

    Works both when running from source (TCGLiveMonitor.py present) and when
    frozen into a single .exe (PyInstaller), where the install root is the
    directory containing the executable.
    """
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
        # Source layout: the monitor .py file lives here.
        if (candidate / MONITOR_SCRIPT_NAME).exists():
            return candidate
        # Frozen layout: the packaged monitor executable lives here.
        if (candidate / "TCGLiveMonitor.exe").exists():
            return candidate
        if (candidate / "TCGLiveMonitorNOCONSOLE.exe").exists():
            return candidate
    return script_dir


def venv_python(root: str | os.PathLike[str], windowed: bool = False) -> Path | None:
    """Python of an installed copy (bundled ``runtime\\``) or a dev checkout (``.venv``)."""
    exe_name = "pythonw.exe" if windowed else "python.exe"
    for candidate in (Path(root) / "runtime" / exe_name, Path(root) / ".venv" / "Scripts" / exe_name):
        if candidate.exists():
            return candidate
    return None


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
    """Build the command used to launch the monitor headless at login.

    When running from source, this is ``pythonw.exe TCGLiveMonitor.py
    --headless``. When frozen into a single .exe, this is the packaged
    executable itself with ``--headless``.
    """
    # Frozen (PyInstaller) layout: launch the packaged executable directly.
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        command = f'"{exe}" --headless'
        return exe, exe, command

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

    # Runs with normal (limited) rights - the monitor never needs admin, and
    # an elevated task would run the embedded browser as admin (SEC-11).
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
            "limited",
            "/f",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True, None
    return False, (result.stderr or result.stdout or "Unknown error").strip()


def _delete_task_elevated(task_name: str) -> bool:
    """Delete a scheduled task with an elevated (admin) prompt.

    Scheduled tasks created with /rl highest require administrator privileges
    to delete. When a normal (non-elevated) schtasks call fails with "Access
    is denied", we re-run the deletion elevated via ShellExecuteW so the user
    gets a UAC prompt instead of a confusing error.
    """
    try:
        import ctypes

        # ShellExecuteW with "runas" verb triggers a UAC elevation prompt.
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            "schtasks.exe",
            f'/delete /tn "{task_name}" /f',
            None,
            1,  # SW_SHOWNORMAL
        )
        # ShellExecuteW returns > 32 on success.
        return result > 32
    except Exception:
        return False


def remove_task(include_current: bool = True) -> tuple[bool, list[str], list[str]]:
    removed: list[str] = []
    errors: list[str] = []
    task_names = ((TASK_NAME,) if include_current else ()) + tuple(LEGACY_TASK_NAMES)

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

        # If access is denied (task requires admin), retry elevated so the
        # user gets a UAC prompt instead of a dead-end error.
        if "access is denied" in message:
            if _delete_task_elevated(task_name):
                removed.append(task_name)
                continue
            errors.append(f"{task_name}: Access is denied. Run this tool as Administrator to remove the scheduled task.")
            continue

        errors.append(f"{task_name}: {(result.stderr or result.stdout).strip()}")

    return not errors, removed, errors


def enable_startup(root: str | os.PathLike[str] | None = None) -> dict:
    """Enable auto-start using the registry Run key as the primary method.

    The scheduled task is only created as a backup if the registry method
    fails. Old/legacy scheduled tasks are removed automatically so they don't
    cause duplicate monitor instances.
    """
    install_root = find_install_root(root)

    # Primary: registry Run key (no admin needed, reliable).
    reg_ok, reg_error = add_registry(install_root)

    # Backup: only create a scheduled task if the registry method failed.
    task_ok = False
    task_error = None
    if not reg_ok:
        task_ok, task_error = add_task(install_root)

    # Clean up old/legacy scheduled tasks so they don't spawn duplicates.
    # Keep the current task if it was just created as the fallback (BUG-016);
    # if the registry worked, the current task is redundant and removed too.
    _, removed_tasks, _ = remove_task(include_current=reg_ok)
    if reg_ok:
        add_watchdog(install_root)

    return {
        "root": install_root,
        "registry_ok": reg_ok,
        "registry_error": reg_error,
        "task_ok": task_ok,
        "task_error": task_error,
        "removed_tasks": removed_tasks,
        "registry_enabled": is_registry_registered(),
        "task_enabled": is_task_registered(),
    }


def _registry_command() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as key:
            return str(winreg.QueryValueEx(key, REG_VALUE)[0] or "")
    except OSError:
        return ""


def _same_command(a: str, b: str) -> bool:
    return " ".join(a.lower().split()) == " ".join(b.lower().split())


def startup_is_ours(root: str | os.PathLike[str]) -> bool:
    """Auto-start is on and launches this copy (not another install or checkout)."""
    _, _, command = build_headless_command(root)
    return bool(command) and _same_command(_registry_command(), command)


def _xml_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def watchdog_xml(root: str | os.PathLike[str]) -> str | None:
    """Task Scheduler XML for the watchdog. Unlike schtasks' defaults it runs
    on battery, never stops the monitor (no time limit, no battery stop) and
    at normal priority (the default 7 would slow the overlay)."""
    python, script, _ = build_headless_command(root)
    if not python:
        return None
    if getattr(sys, "frozen", False):
        command, arguments = str(python), "--headless --watchdog"
    else:
        command, arguments = str(python), f'"{script}" --headless --watchdog'
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Starts Pokemon TCG Live Monitor again if it stopped running.</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>2025-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <Repetition>
        <Interval>PT{WATCHDOG_MINUTES}M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>false</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>4</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{_xml_text(command)}</Command>
      <Arguments>{_xml_text(arguments)}</Arguments>
      <WorkingDirectory>{_xml_text(str(Path(root)))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _watchdog_action() -> str:
    """The registered watchdog's command line ("" when there is none)."""
    result = subprocess.run(["schtasks", "/query", "/tn", WATCHDOG_TASK_NAME, "/xml"],
                            capture_output=True, text=True, creationflags=_NO_WINDOW)
    if result.returncode != 0:
        return ""
    import re
    import html
    command = re.search(r"<Command>(.*?)</Command>", result.stdout, re.S)
    arguments = re.search(r"<Arguments>(.*?)</Arguments>", result.stdout, re.S)
    return html.unescape(((command.group(1) if command else "") + " " +
                          (arguments.group(1) if arguments else "")).strip())


def add_watchdog(root: str | os.PathLike[str]) -> tuple[bool, str | None]:
    xml = watchdog_xml(root)
    if not xml:
        return False, "pythonw.exe was not found."
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".xml")
    try:
        with os.fdopen(fd, "w", encoding="utf-16") as fh:
            fh.write(xml)
        result = subprocess.run(["schtasks", "/create", "/tn", WATCHDOG_TASK_NAME, "/xml", path, "/f"],
                                capture_output=True, text=True, creationflags=_NO_WINDOW)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if result.returncode == 0:
        return True, None
    return False, (result.stderr or result.stdout or "Unknown error").strip()


def remove_watchdog() -> bool:
    result = subprocess.run(["schtasks", "/delete", "/tn", WATCHDOG_TASK_NAME, "/f"],
                            capture_output=True, text=True, creationflags=_NO_WINDOW)
    return result.returncode == 0


def ensure_watchdog(root: str | os.PathLike[str]) -> str:
    """Keep the watchdog in step with auto-start: there (launching this copy)
    while auto-start launches this copy, gone when auto-start is off. Another
    copy's watchdog (e.g. the installed app while a dev checkout runs) is left
    alone. Returns what it did: "ok", "added", "removed" or "skipped"."""
    if os.name != "nt":
        return "skipped"
    python, script, _ = build_headless_command(root)
    if not python:
        return "skipped"
    if not is_registry_registered():
        return "removed" if remove_watchdog() else "skipped"
    if not startup_is_ours(root):
        return "skipped"
    wanted = (f'{python} --headless --watchdog' if getattr(sys, "frozen", False)
              else f'{python} "{script}" --headless --watchdog')
    if _same_command(_watchdog_action(), wanted):
        return "ok"
    return "added" if add_watchdog(root)[0] else "skipped"


def run_watchdog_now() -> bool:
    """Start the monitor through the watchdog task: its parent is then Task
    Scheduler, so it never dies with whatever asked for the restart."""
    result = subprocess.run(["schtasks", "/run", "/tn", WATCHDOG_TASK_NAME],
                            capture_output=True, text=True, creationflags=_NO_WINDOW)
    return result.returncode == 0


def mark_stopped(root: str | os.PathLike[str]) -> None:
    try:
        Path(root, STOPPED_MARKER).write_text("closed by the user", encoding="utf-8")
    except OSError:
        pass


def clear_stopped(root: str | os.PathLike[str]) -> None:
    try:
        Path(root, STOPPED_MARKER).unlink()
    except OSError:
        pass


def stopped_on_purpose(root: str | os.PathLike[str]) -> bool:
    """Closed by the user since this sign-in (a restart of Windows clears it)."""
    marker = Path(root, STOPPED_MARKER)
    try:
        closed_at = marker.stat().st_mtime
    except OSError:
        return False
    try:
        import psutil
        return closed_at > psutil.boot_time()
    except Exception:
        return True


def disable_startup() -> dict:
    reg_ok, reg_error = remove_registry()
    task_ok, removed_tasks, task_errors = remove_task()
    if remove_watchdog():
        removed_tasks.append(WATCHDOG_TASK_NAME)
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

    # Frozen (PyInstaller) layout: launch the packaged executable directly.
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        command = [str(exe)]
        if headless:
            command.append("--headless")
        kwargs = {"cwd": str(install_root)}
        if os.name == "nt" and not headless:
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen(command, **kwargs)
        return {
            "ok": True,
            "root": install_root,
            "python": str(exe),
            "script": str(exe),
            "headless": headless,
        }

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
