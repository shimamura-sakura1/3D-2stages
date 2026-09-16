"""Deterministic local discovery; never installs software or starts services."""
import os
import re
import shutil
import sys
from pathlib import Path

from runtime.errors import BoundaryError


def find_blender(executable=None, *, platform=None, environ=None, home=None, applications=None):
    env = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else Path(home)
    configured = executable if executable is not None else env.get("BLENDER_EXECUTABLE") or None
    if configured is not None:
        path = Path(configured).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
        found = shutil.which(str(configured)) if str(configured).strip() else None
        if found:
            return found
        raise BoundaryError("Configured Blender executable not found or not executable; fix --blender or BLENDER_EXECUTABLE")
    found = shutil.which("blender")
    if found:
        return found
    candidates = []
    if platform == "darwin":
        for folder in (Path(applications) if applications is not None else Path("/Applications"), home / "Applications"):
            candidates.append(folder / "Blender.app/Contents/MacOS/Blender")
    elif platform == "win32":
        for key in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)", "LOCALAPPDATA"):
            if not env.get(key):
                continue
            base = Path(env[key])
            roots = [base / "Blender Foundation"]
            if key == "LOCALAPPDATA":
                roots.append(base / "Programs/Blender Foundation")
            for folder in roots:
                installs = list(folder.glob("Blender*/blender.exe"))
                # Numeric installation-directory versions, not semantic classification.
                installs.sort(key=lambda p: (tuple(int(v) for v in re.findall(r"\d+", p.parent.name)), str(p)), reverse=True)
                candidates.extend(installs)
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
    raise BoundaryError("Blender executable not found; install Blender 4.2+ or set --blender / BLENDER_EXECUTABLE")


def find_framework(root, explicit=None, *, environ=None):
    env = os.environ if environ is None else environ
    value = explicit if explicit is not None else env.get("CONTRACT_GOVERN_HOME") or Path(root).resolve().parent / "contract-govern-skil"
    path = Path(value).expanduser().resolve()
    if not (path / "skillctl/__main__.py").is_file() or not (path / "spec/SPEC.md").is_file():
        raise BoundaryError("Governance framework not found; set CONTRACT_GOVERN_HOME or --framework to the designated contract-govern-skil checkout")
    return path


def environment_report(root, blender=None):
    result = {"platform": sys.platform,
              "python": {"executable": sys.executable, "version": list(sys.version_info[:3]), "prefix": sys.prefix},
              "blender": {"minimum_version": [4, 2, 0], "version_verified": False},
              "mcp": {"status": "requires_session_check"}}
    try:
        result["blender"].update(status="found", executable=find_blender(blender))
    except BoundaryError as exc:
        result["blender"].update(status="unavailable", reason=str(exc))
    try:
        result["governance"] = {"status": "found", "framework": str(find_framework(root))}
    except BoundaryError as exc:
        result["governance"] = {"status": "unavailable", "reason": str(exc)}
    return result
