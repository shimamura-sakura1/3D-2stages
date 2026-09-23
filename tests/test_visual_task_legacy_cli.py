"""Legacy CLI remains executable alongside the new visual-task boundary."""
import json

from tests.test_render_director import inputs
from tests.test_v02_planning import cli


def test_legacy_context_and_direction_submission(tmp_path):
    manager, plans, scene, context, direction = inputs(tmp_path)
    paths = {}
    for name, value in [('scene', scene), ('plans', plans), ('direction', direction)]:
        paths[name] = tmp_path / (name + '.json')
        paths[name].write_text(json.dumps(value), encoding='utf-8')
    before = manager.path.read_bytes()
    result = cli('render-context', manager.root, '--scene-context', paths['scene'])
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == context
    assert manager.path.read_bytes() == before

    result = cli('scene-plans-submit', manager.root, '--plans', paths['plans'],
                 '--render-direction', paths['direction'], '--scene-context', paths['scene'],
                 '--expected-version', manager.read()['version'])
    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)
    assert manifest == manager.read()
    stored = manager.root / manifest['render_direction']['artifact_path']
    assert json.loads(stored.read_text(encoding='utf-8')) == direction

    before = manager.path.read_bytes()
    direction['project_id'] = 'other-project'
    paths['direction'].write_text(json.dumps(direction), encoding='utf-8')
    result = cli('scene-plans-submit', manager.root, '--plans', paths['plans'],
                 '--render-direction', paths['direction'], '--scene-context', paths['scene'],
                 '--expected-version', manager.read()['version'])
    assert result.returncode == 2 and json.loads(result.stderr)['error']
    assert manager.path.read_bytes() == before
