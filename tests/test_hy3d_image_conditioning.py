"""Image-only protocol tests use local gateway doubles, never remote GPU evidence."""
import base64
import http.client
import io
import json
import struct
import urllib.error
import zlib

import pytest

from runtime.errors import WorkflowError, ProviderError
from runtime.geometry_acquisition import validate_geometry
from runtime.hy3d_client import Hy3DClient, NoRedirect
from runtime.io import sha256
from runtime.manifest_manager import ManifestManager
from runtime.reference_manager import import_reference
from tests.test_v02_geometry import executor, request, ROOT
from tests.test_v02_hy3d import gateway, generated_request
from tests.test_v02_planning import proposal, cli


def image_ready(tmp_path, suffix='.png'):
    root, docs = proposal(tmp_path)
    manager = ManifestManager(root)
    def chunk(name, data):
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 16, 16, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress((b'\0' + b'\x11\x22\x33' * 16) * 16)) + chunk(b'IEND', b'')
    source = tmp_path / ('licensed' + suffix)
    source.write_bytes(png)
    metadata = {'kind': 'user', 'creator': 'test fixture', 'license': 'cc0', 'license_verified': True, 'attribution': 'authored test image'}
    ref = import_reference(manager, source, 'ref_material', ['material_language'], metadata)
    docs['reference_board']['references'] = [ref]
    state = manager.submit_visual_plan(docs, expected_version=0)
    state = manager.review_visual('approved', expected_version=state['version'])
    manager.configure_visual('full_pipeline', expected_version=state['version'])
    return manager, ref


def image_request(surface=False):
    q = generated_request(surface)
    q.update(image_only=True, reference_ids=['ref_material'])
    q['task']['target']['description'] = 'semantic machine description retained for search'
    q['task']['hy3d']['prompt'] = ''
    return q


@pytest.mark.parametrize('surface', [False, True])
def test_image_only_payload_recipe_and_review(tmp_path, glb_bytes, surface):
    manager, ref = image_ready(tmp_path)
    client, transport = gateway(glb_bytes)
    q = image_request(surface)
    result = executor(manager, client).run(q)
    posts = [call for call in transport.calls if call[0] == 'POST']
    assert len(posts) == (2 if surface else 1)
    for _, _, body in posts:
        assert body['prompt'] == '' and body['style_bible'] == {}
        image, = body['reference_images']
        assert base64.b64decode(image['data_base64']) == (manager.root / ref['path']).read_bytes()
    assert q['task']['target']['description'] == 'semantic machine description retained for search'
    assert result['recipe']['conditioning_mode'] == 'image_only'
    assert result['recipe']['reference_sha256'] == [sha256(manager.root / ref['path'])]
    recorded = manager.read()['geometry_assets']['machine']
    assert recorded['status'] == 'review_required'
    assert recorded['versions'][-1]['recipe'] == result['recipe']


@pytest.mark.parametrize('flag', ['omitted', False])
@pytest.mark.parametrize('prompt', ['', 'explicit model prompt'])
def test_legacy_conditioning_is_unchanged(tmp_path, glb_bytes, flag, prompt):
    manager, _ = image_ready(tmp_path)
    client, transport = gateway(glb_bytes)
    q = image_request()
    if flag == 'omitted': q.pop('image_only')
    else: q['image_only'] = flag
    q['task']['hy3d']['prompt'] = prompt
    result = executor(manager, client).run(q)
    body = next(c[2] for c in transport.calls if c[0] == 'POST')
    assert body['prompt'] == (prompt or q['task']['target']['description'])
    assert 'conditioning_mode' not in result['recipe']


@pytest.mark.parametrize('problem', ['string', 'int', 'null', 'list', 'route_a', 'route_b', 'route_d', 'none', 'multi', 'wrong_refs_type', 'unknown_ref', 'prompt', 'whitespace_prompt', 'svg'])
def test_image_only_invalid_preflight_is_atomic(tmp_path, glb_bytes, problem):
    manager, _ = image_ready(tmp_path, '.svg' if problem == 'svg' else '.png')
    client, transport = gateway(glb_bytes)
    q = image_request()
    if problem in ('string', 'int', 'null', 'list'): q['image_only'] = {'string': 'true', 'int': 1, 'null': None, 'list': []}[problem]
    if problem.startswith('route_'):
        q = request('machine', 'platform' if problem == 'route_d' else None, problem[-1].upper())
        q.update(image_only=True, reference_ids=['ref_material'])
        q['task']['hy3d']['prompt'] = ''
        if problem == 'route_b': q['modification'] = {'scale': [1, 2, 1]}
    if problem == 'none': q['reference_ids'] = []
    if problem == 'multi': q['reference_ids'] = ['ref_material', 'ref_material']
    if problem == 'wrong_refs_type': q['reference_ids'] = 'ref_material'
    if problem == 'unknown_ref': q['reference_ids'] = ['unknown']
    if problem == 'prompt': q['task']['hy3d']['prompt'] = 'required model instruction'
    if problem == 'whitespace_prompt': q['task']['hy3d']['prompt'] = ' '
    before = manager.path.read_bytes()
    with pytest.raises(WorkflowError, match='image_only|reference|Route C|PNG'):
        executor(manager, client).run(q)
    assert transport.calls == []
    assert manager.path.read_bytes() == before and not (manager.root / 'stage1').exists()


@pytest.mark.parametrize('problem', ['missing_hash', 'multiple_hashes', 'route'])
def test_image_recipe_linkage_validation(tmp_path, glb_bytes, problem):
    manager, _ = image_ready(tmp_path)
    client, _ = gateway(glb_bytes)
    result = executor(manager, client).run(image_request())
    if problem == 'missing_hash': result['recipe']['reference_sha256'] = []
    if problem == 'multiple_hashes': result['recipe']['reference_sha256'] *= 2
    if problem == 'route': result['route'] = 'A'
    with pytest.raises(WorkflowError, match='conditioning|image_only'):
        validate_geometry(manager.root, result)


def test_public_cli_rejects_image_only_wrong_route(tmp_path):
    manager, _ = image_ready(tmp_path)
    q = request(); q['image_only'] = True; q['reference_ids'] = ['ref_material']
    q['task']['hy3d']['prompt'] = ''
    path = tmp_path / 'request.json'; path.write_text(json.dumps(q))
    before = manager.path.read_bytes()
    reply = cli('geometry-acquire', manager.root, '--request', path, '--catalog', ROOT / 'examples/library/catalog.yaml')
    assert reply.returncode != 0 and 'Route C' in reply.stderr
    assert manager.path.read_bytes() == before
    guide = (ROOT / 'docs/v02/hy3d-image-conditioning.md').read_text()
    assert 'image_only' in guide and 'target.description' in guide


class BoundedErrorBody(io.BytesIO):
    def read(self, size=-1):
        assert 0 < size <= 8193, 'HTTP failure bodies must be bounded'
        return super().read(size)


def failure_client(monkeypatch, body, status=422):
    stream = BoundedErrorBody(body)
    error = urllib.error.HTTPError('https://example.test/private', status, 'secret service reason', {'secret-header': 'header-secret'}, stream)
    class Opener:
        def open(self, *args, **kwargs): raise error
    monkeypatch.setattr('urllib.request.build_opener', lambda *args: Opener())
    return Hy3DClient({'type': 'remote', 'endpoint': 'https://example.test'}), stream


def test_http_failure_preserves_status_and_static_code_only(monkeypatch):
    client, stream = failure_client(monkeypatch, json.dumps({'error': {'code': 'unsupported_conditioning', 'message': 'Bearer secret /private/secret'}, 'token': 'secret'}).encode())
    with pytest.raises(ProviderError) as error:
        client._request('POST', '/v1/generate_shape', {})
    message = str(error.value)
    assert 'HTTP 422' in message and 'unsupported_conditioning' in message
    assert 'secret' not in message and 'Bearer' not in message and '/private' not in message


@pytest.mark.parametrize('body', [b'not json secret', b'[]', b'{"error":null}', b'{"error":{"code":42}}', b'{"error":{"code":"Bearer secret"}}', b'{"error":{"code":"/private/secret"}}', b'{"error":{"code":"secret\\nvalue"}}', b'{"error":{"code":"opaque_secret_123"}}', b'{"error":{"code":"unsupported_conditioning"},"padding":"' + b'x' * 8192 + b'"}', b'{"error":{"code":"' + b'x' * 100 + b'"}}'])
def test_http_untrusted_diagnostics_are_generic_and_bounded(monkeypatch, body):
    client, _ = failure_client(monkeypatch, body, status=503)
    with pytest.raises(ProviderError) as error: client._request('POST', '/v1/generate_shape', {})
    assert str(error.value) == 'HY3D gateway POST /v1/generate_shape failed (HTTP 503)'


def test_redirect_protection_remains():
    with pytest.raises(ProviderError, match='redirects are disabled'):
        NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere.test')


def test_http_incomplete_error_body_preserves_status_and_closes(monkeypatch):
    class InterruptedBody(BoundedErrorBody):
        def read(self, size=-1):
            assert 0 < size <= 8193
            raise http.client.IncompleteRead(b'Bearer secret /private/response', 100)
    stream = InterruptedBody()
    failure = urllib.error.HTTPError('https://example.test/private', 503, 'secret reason', {}, stream)
    class Opener:
        def open(self, *args, **kwargs): raise failure
    monkeypatch.setattr('urllib.request.build_opener', lambda *args: Opener())
    client = Hy3DClient({'type': 'remote', 'endpoint': 'https://example.test'})
    with pytest.raises(ProviderError) as error:
        client._request('POST', '/v1/generate_shape', {})
    assert str(error.value) == 'HY3D gateway POST /v1/generate_shape failed (HTTP 503)'
    assert stream.closed
