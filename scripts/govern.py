"""Use the external skillctl on a clean source projection, preserving real evidence."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from runtime.platform_support import find_framework
from runtime.errors import BoundaryError

DIRECTORIES = ("runtime", "providers", "contracts", "policies", "templates", "prompts", "configs",
               "examples", "tests", "docs", "scripts", "styles")
FILES = ("AGENTS.md", "SKILL.md", "interface.json", "requirements.json", "README.md", "pyproject.toml",
         "requirements-tested.txt", ".gitignore", ".gitattributes", ".env.example",
         "two_stage_3d_skill_codex_spec_v0.1.md")
IGNORED = {"__pycache__", ".pytest_cache"}


def source_files(root):
    result = []
    for name in FILES:
        path = root / name
        if path.is_file():
            result.append(path)
    for name in DIRECTORIES:
        folder = root / name
        if not folder.exists():
            continue
        for directory, dirs, names in os.walk(folder, followlinks=False):
            for child in dirs:
                path = Path(directory) / child
                if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                    raise ValueError(f"Linked source directory is unsupported: {path}")
            dirs[:] = sorted(d for d in dirs if d not in IGNORED)
            result.extend(Path(directory) / p for p in sorted(names) if not p.endswith(".pyc"))
    for path in result:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Source must stay in the repository: {path}")
    return sorted(result)


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files(root)}


def history_snapshot(root):
    records = {}
    for path in (root / "changes").glob("change-*.json"):
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Change records must stay in the repository")
        records[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return records


def restore_recorded_newlines(package):
    """Recover authenticated pre-checkout bytes in a disposable projection only."""
    package = Path(package).resolve()
    restored = []

    def recover(relative, expected):
        path = package / relative
        if path.is_symlink() or not path.resolve().is_relative_to(package):
            raise ValueError(f"Recorded path escapes governance projection: {relative}")
        original = path.read_bytes()
        if hashlib.sha256(original).hexdigest() == expected:
            return
        lf = original.replace(b"\r\n", b"\n")
        for candidate in (lf, lf.replace(b"\n", b"\r\n")):
            if hashlib.sha256(candidate).hexdigest() == expected:
                path.write_bytes(candidate)
                restored.append(relative)
                return
        raise ValueError(f"Historical content differs beyond newline transport: {relative}")

    entries = sorted((package / "changes").glob("change-*.json"), key=lambda p: int(p.stem.split("-")[-1]))
    for previous, following in zip(entries, entries[1:]):
        anchor = json.loads(following.read_text(encoding="utf-8"))["previous_record_sha256"]
        recover(previous.relative_to(package).as_posix(), anchor)
    if entries:
        recorded = json.loads(entries[-1].read_text(encoding="utf-8"))["snapshot"]
        for relative, expected in recorded.items():
            if relative.startswith("tests/") and relative != "tests/manifest.json":
                recover(relative, expected)
    return restored


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", help="Designated framework; otherwise CONTRACT_GOVERN_HOME or sibling contract-govern-skil")
    parser.add_argument("--python", dest="interpreter", help="Python with skillctl, pytest, PyYAML and jsonschema installed")
    parser.add_argument("command", choices=["validate", "graph", "impact", "contract-test", "test", "accept"])
    args, rest = parser.parse_known_args(argv)
    try:
        framework = find_framework(ROOT, args.framework)
    except BoundaryError as exc:
        parser.error(str(exc))
    interpreter = Path(args.interpreter).expanduser() if args.interpreter else Path(sys.executable)
    if not interpreter.is_file():
        parser.error("Set CONTRACT_GOVERN_HOME or --framework, or use --python with an installed skillctl environment")
    state = ROOT / ".skillctl"
    if state.is_symlink() or getattr(state, "is_junction", lambda: False)() or not state.resolve().is_relative_to(ROOT):
        parser.error("Governance workspace must stay in the source repository")
    state.mkdir(exist_ok=True)
    lock = state / "govern.lock"
    acquired = False
    try:
        with lock.open("x", encoding="utf-8") as stream:
            stream.write("Governance command in progress\n")
        acquired = True
        baseline = snapshot(ROOT)
        baseline_history = history_snapshot(ROOT)
        with tempfile.TemporaryDirectory(prefix="package-", dir=state) as temporary:
            package = Path(temporary) / "skill"
            package.mkdir()
            for relative in baseline:
                target = package / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            if (ROOT / "changes").exists():
                for source in (ROOT / "changes").glob("change-*.json"):
                    if source.is_symlink():
                        raise ValueError("Change records may not be symlinks")
                    (package / "changes").mkdir(exist_ok=True)
                    shutil.copy2(source, package / "changes" / source.name)
            restored = restore_recorded_newlines(package)
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONPATH=str(framework))
            result = subprocess.run([str(interpreter), "-B", "-m", "skillctl", args.command, str(package), *rest],
                                    capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT)
            reports = state / "reports"
            reports.mkdir(exist_ok=True)
            report_path = reports / (args.command + "-" + uuid.uuid4().hex[:12] + ".json")
            try:
                report = json.loads(result.stdout)
            except ValueError:
                report = {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
            report["source_projection"] = {"restored_newlines": restored}
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            if snapshot(ROOT) != baseline or history_snapshot(ROOT) != baseline_history:
                raise ValueError("Source changed while governance was running; no record will be copied back")
            if args.command == "accept" and result.returncode == 0 and report.get("status") == "pass" and report.get("change_record"):
                relative = Path(report["change_record"])
                if relative.parent != Path("changes") or not relative.name.startswith("change-"):
                    raise ValueError("Unexpected change record path from skillctl")
                record = (package / relative).read_bytes()
                target = ROOT / relative
                target.parent.mkdir(exist_ok=True)
                if target.exists():
                    if target.read_bytes() != record:
                        raise ValueError("Existing change record must not be overwritten")
                else:
                    pending = target.with_suffix(".pending")
                    with pending.open("xb") as stream:
                        stream.write(record)
                        stream.flush()
                        os.fsync(stream.fileno())
                    pending.rename(target)
            if args.command in ("graph", "impact", "validate"):
                print(result.stdout, end="")
            else:
                summary = {k: report[k] for k in ("status", "declared_contract", "runtime_contract", "errors",
                            "accepted_version", "change_record", "check_only", "selected_tests") if k in report}
                summary["report"] = str(report_path)
                if "selected" in report:
                    summary["selected_tests"] = report["selected"]
                if report.get("status") == "fail":
                    summary["failed_tests"] = [r for r in report.get("results", []) if r.get("status") != "pass"]
                if "tests" in report and isinstance(report["tests"], dict):
                    summary["tests_status"] = report["tests"].get("status")
                print(json.dumps(summary, ensure_ascii=False, indent=2))
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return result.returncode
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    finally:
        if acquired:
            lock.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
