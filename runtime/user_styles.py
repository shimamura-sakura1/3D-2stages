"""Explicit user style inputs; data-only preparation and immutable project import."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.errors import BoundaryError
from runtime.io import atomic_write, sha256
from runtime.style_registry import StyleRegistry, design_reviewed, style_path


def package_bytes(style):
    """Capture the exact bytes that were validated; do not copy unrelated user files."""
    result = {}
    for relative, digest in style['source_hashes'].items():
        raw = style_path(style['root'], relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise BoundaryError('Style source changed during validation: ' + relative)
        result[relative] = raw
    return result


def inspect_style(source):
    style = StyleRegistry().load_package(source, require_resources=False, require_review=False)
    pending = [] if design_reviewed(style) else ['design_review']
    pending.extend(key for key in style['resources'] if not Path(style[key]).is_file())
    return {'style_id': style['id'], 'version': style['version'], 'format_version': style['format_version'],
            'status': 'pending' if pending else 'validated', 'pending': pending,
            'material_classes': sorted(style['materials']['materials']), 'artistic_approval': False,
            'resource_validation': 'headers_only; named materials and visual quality require Blender inspection',
            'source_hashes': style['source_hashes']}


def prepare_style(source, output):
    style = StyleRegistry().load_package(source, require_resources=False, require_review=False)
    raw = package_bytes(style)
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise BoundaryError('Calibration output already exists; choose a new directory')
    output = output.resolve()
    if output.is_relative_to(Path(style['root'])):
        raise BoundaryError('Calibration output must be outside the source package')
    # Only validated definitions and provenance enter the candidate. Resources are
    # regenerated with this profile's material names, never borrowed by filename.
    definitions = set(raw) - set(style['resources'].values())
    output.mkdir(parents=True, exist_ok=False)
    try:
        for relative in sorted(definitions):
            path = style_path(output, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw[relative])
        candidate = StyleRegistry().load_package(output, require_resources=False, require_review=False)
        worker = Path(__file__).resolve().with_name('blender_style_worker.py')
        guard = {str(style_path(output, p)): digest for p, digest in candidate['source_hashes'].items()}
        guard[str(worker)] = sha256(worker)
        packet = output / 'calibration-request.json'
        atomic_write(packet, {'style': candidate, 'guard': guard, 'preview': str(output / 'preview.png'),
                              'receipt': str(output / 'calibration-result.json')})
        digest = sha256(packet)
        return {'status': 'prepared', 'backend': 'mcp', 'package': str(output), 'packet': str(packet),
                'sha256': digest, 'artistic_approval': False,
                'execute_code': f"import runpy; worker=runpy.run_path({str(worker)!r}); worker['execute_calibration']({str(packet)!r}, {digest!r})"}
    except Exception:
        # This directory was proven absent and created by this invocation only.
        shutil.rmtree(output)
        raise


def stage_import(manager, manifest, source):
    if manifest['state'] not in ('initialized', 'visual_planning', 'visual_review_required'):
        raise BoundaryError('Style import requires visual planning before approval')
    style = StyleRegistry().load_package(source)
    raw = package_bytes(style)
    relative_root = f"styles/{style['id']}/versions/{style['version']}"
    target = style_path(manager.root, relative_root)
    if target.exists() and any(target.iterdir()):
        raise BoundaryError('Immutable style package already exists; publish a new version')
    lock = {'format_version': '1.0', 'style_id': style['id'], 'version': style['version'],
            'files': style['source_hashes']}
    raw['package-lock.json'] = json.dumps(lock, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
    pending = []
    for relative, value in sorted(raw.items()):
        destination = f'{relative_root}/{relative}'
        style_path(manager.root, destination)
        pending.append((destination, value))
    return pending


def main(argv=None):
    """Actual-I/O profile probe; the public CLI supplies the richer status report."""
    import argparse
    import yaml
    from runtime.errors import WorkflowError
    from runtime.style_registry import UniqueKeyLoader
    parser = argparse.ArgumentParser(description='Inspect a user package and emit its validated profile')
    parser.add_argument('source')
    args = parser.parse_args(argv)
    try:
        style = StyleRegistry().load_package(args.source, require_resources=False, require_review=False)
        profile = yaml.load(package_bytes(style)['profile.yaml'].decode('utf-8'), Loader=UniqueKeyLoader)
    except (WorkflowError, OSError, ValueError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(profile, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
