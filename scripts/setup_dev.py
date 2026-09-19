"""Inspect a development host; persist only explicitly supplied local paths."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_local(root):
    path = Path(root) / '.deps/development-host.json'
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or any(k not in {'blender', 'framework', 'render_director'} or not isinstance(v, str) for k, v in data.items()):
        raise ValueError('Invalid local development settings')
    return data


def save_local(root, updates):
    root = Path(root)
    settings = {**load_local(root), **updates}
    local = root / '.deps/development-host.json'
    if local.is_symlink() or local.parent.is_symlink() or (root/'.env').is_symlink():
        raise ValueError('Local settings must not be symbolic links')
    env_path = root / '.env'
    template = root / '.env.example'
    text = env_path.read_text(encoding='utf-8-sig') if env_path.exists() else template.read_text(encoding='utf-8') if template.exists() else ''
    if 'blender' in updates:
        value = updates['blender'].replace('\\', '/')
        if any(c in value for c in "'\r\n"):
            raise ValueError('Blender path cannot be represented safely in .env')
        assignment = f"BLENDER_EXECUTABLE='{value}'"
        pattern = r'(?m)^\s*(?:export\s+)?BLENDER_EXECUTABLE\s*=[^\r\n]*'
        text = re.sub(pattern, lambda _: assignment, text) if re.search(pattern, text) else text.rstrip() + '\n' + assignment + '\n'
    local.parent.mkdir(parents=True, exist_ok=True)
    staged = local.with_suffix('.json.tmp')
    staged.write_text(json.dumps(settings, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    staged.replace(local)
    if 'blender' in updates or not env_path.exists():
        staged_env = root / '.deps/development-env.tmp'
        staged_env.write_text(text, encoding='utf-8')
        staged_env.replace(env_path)


def inspect_blender(value):
    if value:
        executable = str(Path(value).expanduser().resolve()) if Path(value).expanduser().is_file() else shutil.which(value)
    else:
        from runtime.platform_support import find_blender
        try:
            executable = find_blender()
        except Exception:
            executable = None
    if not executable:
        return {'status': 'missing'}
    try:
        result = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=15)
        match = re.search(r'^Blender (\d+)\.(\d+)\.(\d+)', result.stdout, re.M)
        if result.returncode or not match:
            return {'status': 'invalid', 'executable': executable}
        version = [int(v) for v in match.groups()]
        return {'status': 'ready' if version >= [4, 2, 0] else 'unsupported', 'executable': executable, 'version': version}
    except (OSError, subprocess.TimeoutExpired):
        return {'status': 'unavailable', 'executable': executable}


def checkout(path, markers):
    if not path:
        return {'status': 'missing'}
    resolved = Path(path).expanduser().resolve()
    return {'status': 'ready' if all((resolved / marker).is_file() for marker in markers) else 'invalid', 'path': str(resolved)}


def inspect_host(root, settings):
    dependencies = {}
    for name in ('PyYAML', 'jsonschema', 'pytest'):
        try:
            dependencies[name] = {'status': 'ready', 'version': importlib.metadata.version(name)}
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = {'status': 'missing'}
    blender = inspect_blender(settings.get('blender') or os.environ.get('BLENDER_EXECUTABLE'))
    framework = checkout(settings.get('framework') or os.environ.get('CONTRACT_GOVERN_HOME') or str(Path(root).parent/'contract-govern-skil'), ['spec/SPEC.md', 'skillctl/__main__.py'])
    director = checkout(settings.get('render_director') or os.environ.get('RENDER_DIRECTOR_HOME'), ['SKILL.md', 'contracts/render_context.schema.json', 'contracts/render_direction.schema.json', 'contracts/render_review.schema.json'])
    if director['status'] == 'ready':
        try:
            for name in ('render_context', 'render_direction', 'render_review'):
                relative = f'contracts/{name}.schema.json'
                if json.loads((Path(director['path'])/relative).read_text(encoding='utf-8')) != json.loads((Path(root)/relative).read_text(encoding='utf-8')):
                    director['status'] = 'incompatible'
                    break
        except (ValueError, OSError):
            director['status'] = 'incompatible'
    return {'platform': sys.platform, 'python': {'executable': sys.executable, 'version': list(sys.version_info[:3]), 'supported': sys.version_info >= (3,11)}, 'dependencies': dependencies, 'blender': blender, 'framework': framework, 'render_director': director, 'mcp': {'status': 'not_checked', 'required_checks': ['get_addon_status', 'get_scene_info']}, 'ready_for_development': sys.version_info >= (3,11) and all(x['status']=='ready' for x in [blender,framework,director,*dependencies.values()])}


def configure(root, updates, write=False):
    report = inspect_host(root, {**load_local(root), **updates})
    for key in updates:
        if report[key]['status'] != 'ready':
            raise ValueError(f"{'Blender' if key == 'blender' else key} installation is {report[key]['status']}; local settings were not written")
    if write:
        normalized = {key: report[key]['executable' if key == 'blender' else 'path'] for key in updates}
        save_local(root, normalized)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender')
    parser.add_argument('--framework')
    parser.add_argument('--render-director')
    parser.add_argument('--write-local', action='store_true')
    args = parser.parse_args()
    try:
        updates = {key: getattr(args,key) for key in ('blender','framework','render_director') if getattr(args,key) is not None}
        report = configure(ROOT, updates, args.write_local)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['ready_for_development'] else 1
    except (ValueError, OSError) as exc:
        print(json.dumps({'status':'error','message':str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
