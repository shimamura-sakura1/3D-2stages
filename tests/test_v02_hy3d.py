"""Phase 9 behavior tests; gateway responses are explicit test doubles, never GPU evidence."""
import base64
import copy
import json
import struct
from pathlib import Path

import pytest

from runtime.errors import WorkflowError, ProviderError
from runtime.hy3d_client import Hy3DClient
from runtime.io import sha256
from runtime.style_resolver import resolve_material
from tests.test_v02_geometry import ready, executor, request, GeneratedDouble, ROOT
from tests.test_v02_planning import cli


def pack_glb(document, binary):
    data = json.dumps(document).encode()
    data += b' ' * (-len(data) % 4)
    binary += b'\0' * (-len(binary) % 4)
    return (struct.pack('<4sII', b'glTF', 2, 28 + len(data) + len(binary))
            + struct.pack('<II', len(data), 0x4E4F534A) + data
            + struct.pack('<II', len(binary), 0x004E4942) + binary)


def paint_glb(shape, problem=None):
    size = struct.unpack_from('<I', shape, 12)[0]
    doc = json.loads(shape[20:20 + size])
    binary = shape[28 + size:]
    uv_offset = len(binary)
    binary += struct.pack('<6f', 0, 0, 1, 0, 0, 1)
    doc['bufferViews'].append({'buffer': 0, 'byteOffset': uv_offset, 'byteLength': 24})
    doc['accessors'].append({'bufferView': 2, 'componentType': 5126, 'count': 3, 'type': 'VEC2'})
    # One pixel embedded PNG and real material -> texture -> image association.
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
    offset = len(binary)
    binary += png
    doc['buffers'][0]['byteLength'] = len(binary)
    doc['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(png)})
    doc['images'] = [{'bufferView': 3, 'mimeType': 'image/png'}]
    doc['textures'] = [{'source': 0}]
    doc['materials'] = [{'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}}}]
    primitive = doc['meshes'][0]['primitives'][0]
    primitive['material'] = 0
    primitive['attributes']['TEXCOORD_0'] = 2
    if problem == 'unassigned': primitive.pop('material')
    if problem == 'missing_image': doc['textures'][0]['source'] = 4
    if problem == 'missing_texture': doc['materials'][0]['pbrMetallicRoughness'] = {}
    if problem == 'external': doc['images'] = [{'uri': 'outside.png'}]
    if problem == 'empty_image': doc['bufferViews'][3]['byteLength'] = 0
    if problem == 'bounds': doc['bufferViews'][3]['byteLength'] = 1000000
    if problem == 'bogus_image': binary = binary[:offset] + b'x' * len(png)
    if problem == 'missing_uv': primitive['attributes'].pop('TEXCOORD_0')
    if problem == 'unknown_uv': doc['materials'][0]['pbrMetallicRoughness']['baseColorTexture']['texCoord'] = 1
    if problem == 'bad_uv_index': primitive['attributes']['TEXCOORD_0'] = 100
    if problem == 'bad_uv_type': doc['accessors'][2]['type'] = 'VEC3'
    if problem == 'bad_uv_count': doc['accessors'][2]['count'] = 2
    if problem == 'bad_uv_bounds': doc['accessors'][2]['byteOffset'] = 20000
    if problem == 'null_mesh': doc['meshes'] = [None]
    if problem == 'list_primitive': doc['meshes'][0]['primitives'] = [[1, 2]]
    if problem == 'list_material': doc['materials'] = [[]]
    if problem == 'null_image': doc['images'] = [None]
    return pack_glb(doc, binary)


class GatewayTransportDouble:
    def __init__(self, shape, painted=None):
        self.shape = shape
        self.painted = painted or paint_glb(shape)
        self.capabilities = ['generate_shape', 'generate_textured_asset', 'retexture_mesh']
        self.calls = []
        self.fail = None

    def __call__(self, method, path, body):
        self.calls.append((method, path, body))
        if path == '/health': return {'status': 'ok', 'capabilities': self.capabilities}
        if path == self.fail: raise ProviderError('test double inference failure')
        return {'model_base64': base64.b64encode(self.painted if path == '/v1/retexture_mesh' else self.shape).decode()}


def gateway(shape, painted=None):
    transport = GatewayTransportDouble(shape, painted)
    config = {'type': 'local', 'endpoint': 'http://127.0.0.1:8765',
              'output_source': copy.deepcopy(GeneratedDouble.config['output_source'])}
    return Hy3DClient(config, transport), transport


def generated_request(surface=True):
    q = request('machine', None, 'C')
    q['task']['search']['keywords'] = ['unique machine']
    if surface is not None: q['surface_evidence'] = surface
    return q


def test_semantic_client_maps_operations_and_preserves_outputs(tmp_path, glb_bytes):
    client, transport = gateway(glb_bytes)
    kwargs = dict(prompt='machine', reference_images=[], style_bible={})
    shape = client.generate_geometry(output_dir=tmp_path/'shape', **kwargs)
    painted = client.generate_surface_source(mesh=shape, output_dir=tmp_path/'paint', **kwargs)
    assert shape.read_bytes() == glb_bytes and painted.read_bytes() == transport.painted
    posts = [c for c in transport.calls if c[0] == 'POST']
    assert [c[1] for c in posts] == ['/v1/generate_shape', '/v1/retexture_mesh']
    assert base64.b64decode(posts[1][2]['mesh']['data_base64']) == glb_bytes
    with pytest.raises(WorkflowError, match='already exists'):
        client.generate_surface_source(mesh=shape, output_dir=tmp_path/'paint', **kwargs)
    assert len([c for c in transport.calls if c[0] == 'POST']) == 2
    assert painted.read_bytes() == transport.painted


@pytest.mark.parametrize('mesh', [None, 'absent.glb'])
def test_surface_requires_existing_mesh_without_health_or_inference(tmp_path, glb_bytes, mesh):
    client, transport = gateway(glb_bytes)
    with pytest.raises(WorkflowError, match='mesh'):
        client.generate_surface_source(mesh=tmp_path/mesh if mesh else None, prompt='x', reference_images=[], output_dir=tmp_path/'paint', style_bible={})
    assert transport.calls == [] and not (tmp_path/'paint').exists()


@pytest.mark.parametrize('problem', ['untextured', 'empty', 'unassigned', 'missing_image', 'missing_texture', 'external', 'empty_image', 'bounds', 'bogus_image', 'missing_uv', 'unknown_uv', 'bad_uv_index', 'bad_uv_type', 'bad_uv_count', 'bad_uv_bounds', 'null_mesh', 'list_primitive', 'list_material', 'null_image'])
def test_paint_requires_embedded_associated_texture(tmp_path, glb_bytes, problem):
    bad = glb_bytes if problem == 'untextured' else b'' if problem == 'empty' else paint_glb(glb_bytes, problem)
    client, transport = gateway(glb_bytes)
    transport.painted = bad
    mesh = tmp_path/'input.glb';mesh.write_bytes(glb_bytes)
    with pytest.raises(WorkflowError):
        client.generate_surface_source(mesh=mesh, prompt='x', reference_images=[], output_dir=tmp_path/'paint', style_bible={})
    assert [c[1] for c in transport.calls if c[0] == 'POST'] == ['/v1/retexture_mesh']


def test_optional_surface_positive_retains_geometry_and_recipe(tmp_path, glb_bytes):
    m = ready(tmp_path);client, transport = gateway(glb_bytes)
    r = executor(m, client).run(generated_request())
    assert r['recipe']['operation'] == 'generate_geometry'
    assert (m.root/r['geometry']['model']).read_bytes() == glb_bytes
    surface, = r['surface_sources']
    assert surface['kind'] == 'hy3d_paint' and surface['role'] == 'reference_only'
    assert (m.root/surface['path']).read_bytes() == transport.painted
    assert surface['path'] != r['geometry']['model'] and surface['sha256'] != r['geometry']['sha256']
    assert r['recipe']['surface_operation'] == {'operation': 'generate_surface_source', 'gateway_operation': 'retexture_mesh', 'input_geometry_sha256': r['geometry']['sha256']}
    assert [c[1] for c in transport.calls] == ['/health', '/v1/generate_shape', '/v1/retexture_mesh']
    assert m.read()['geometry_assets']['machine']['status'] == 'review_required'
    assert resolve_material('industrial_acg_v1', **r['surface_semantics']) == resolve_material('industrial_acg_v1', 'painted_metal', 'lightly_weathered')


@pytest.mark.parametrize('surface', [None, False])
def test_default_geometry_only_and_legacy_adapter(tmp_path, glb_bytes, surface):
    m = ready(tmp_path);client, transport = gateway(glb_bytes)
    r = executor(m, client).run(generated_request(surface))
    assert not r['surface_sources'] and 'surface_operation' not in r['recipe']
    assert [c[1] for c in transport.calls] == ['/health', '/v1/generate_shape']
    old = GeneratedDouble();m2 = ready(tmp_path/'legacy')
    result = executor(m2, old).run(generated_request(surface))
    assert old.calls == 1 and result['recipe']['operation'] == 'generate_shape'


@pytest.mark.parametrize('problem', ['nonbool', 'route_a', 'route_b', 'route_d', 'capability', 'geometry_capability', 'reference_rights', 'output_rights'])
def test_optional_preflight_rejects_before_generation(tmp_path, glb_bytes, problem):
    m = ready(tmp_path);client, transport = gateway(glb_bytes);q = generated_request()
    if problem == 'nonbool': q['surface_evidence'] = 'true'
    if problem.startswith('route_'):
        q = request('machine', 'platform' if problem == 'route_d' else None, problem[-1].upper());q['surface_evidence'] = True
        if problem == 'route_b': q['modification'] = {'scale': [1, 2, 1]}
    if problem == 'capability': transport.capabilities.remove('retexture_mesh')
    if problem == 'geometry_capability': transport.capabilities.remove('generate_shape')
    if problem == 'reference_rights': q['reference_ids'] = ['ref_material']
    if problem == 'output_rights': client.config['output_source']['license_verified'] = False
    before = m.path.read_bytes()
    with pytest.raises(WorkflowError): executor(m, client).run(q)
    assert not [c for c in transport.calls if c[0] == 'POST']
    assert m.path.read_bytes() == before and not (m.root/'stage1').exists()


@pytest.mark.parametrize('operation', ['generate_shape', 'retexture_mesh'])
def test_inference_failure_never_retries_or_submits(tmp_path, glb_bytes, operation):
    m = ready(tmp_path);client, transport = gateway(glb_bytes);transport.fail = '/v1/' + operation
    before = m.path.read_bytes()
    with pytest.raises(ProviderError, match='test double'): executor(m, client).run(generated_request())
    assert m.path.read_bytes() == before
    assert [c[1] for c in transport.calls if c[0] == 'POST'] == (['/v1/generate_shape'] if operation == 'generate_shape' else ['/v1/generate_shape', '/v1/retexture_mesh'])


def test_surface_tamper_blocks_public_review(tmp_path, glb_bytes):
    m = ready(tmp_path);client, transport = gateway(glb_bytes);ex = executor(m, client)
    r = ex.run(generated_request())
    for name in ('platform', 'wall'): ex.run(request(name, None, 'A'))
    (m.root/r['surface_sources'][0]['path']).write_bytes(glb_bytes)
    before = m.path.read_bytes()
    reply = cli('geometry-review-v02', m.root, '--decision', 'approved', '--expected-version', m.read()['version'])
    assert reply.returncode != 0 and 'hash' in reply.stderr.lower()
    assert m.path.read_bytes() == before


def test_public_cli_default_and_optional_wrong_route(tmp_path):
    m = ready(tmp_path);path = tmp_path/'request.json'
    q = request();q['surface_evidence'] = False;path.write_text(json.dumps(q))
    reply = cli('geometry-acquire', m.root, '--request', path, '--catalog', ROOT/'examples/library/catalog.yaml')
    assert reply.returncode == 0, reply.stderr
    assert json.loads(reply.stdout)['route'] == 'D'
    q = request('wall');q['surface_evidence'] = True;path.write_text(json.dumps(q))
    before = m.path.read_bytes()
    reply = cli('geometry-acquire', m.root, '--request', path, '--catalog', ROOT/'examples/library/catalog.yaml')
    assert reply.returncode != 0 and 'Route C' in reply.stderr
    assert m.path.read_bytes() == before


def test_scene_preparation_retains_surface_without_material_blending(tmp_path, glb_bytes):
    from runtime.scene_production import PLAN_KINDS, prepare_scene, verify_packet
    m = ready(tmp_path);client, transport = gateway(glb_bytes);ex = executor(m, client)
    result = ex.run(generated_request())
    for name in ('platform', 'wall'): ex.run(request(name, None, 'A'))
    m.review_geometry('approved', expected_version=m.read()['version'])
    original = json.loads((ROOT/'tests/fixtures/v02/industrial_station.json').read_text())['documents']
    plans = {k: copy.deepcopy(original[k]) for k in PLAN_KINDS}
    for item in plans['blockout_plan']['objects']:
        item.update(geometry_source='generated' if item['object_id'] == 'machine' else 'library', asset_id=item['object_id'])
    for item in plans['semantic_material_map']['mappings']:
        item.update(slot='body', surface_source=None, material_class='painted_metal', condition='lightly_weathered')
    bad = copy.deepcopy(plans)
    bad['semantic_material_map']['mappings'][0]['surface_source'] = result['surface_sources'][0]['path']
    with pytest.raises(WorkflowError, match='blending'):
        m.submit_scene_plans(bad, expected_version=m.read()['version'])
    m.submit_scene_plans(plans, expected_version=m.read()['version'])
    packet = prepare_scene(m);data = verify_packet(packet['packet'], packet['sha256'])
    assert data['materials']['machine']['parameters'] == data['materials']['platform']['parameters']
    assert data['geometry']['machine']['geometry'] == result['geometry']
    surface_path = m.root/result['surface_sources'][0]['path']
    assert data['guard'][str(surface_path)] == result['surface_sources'][0]['sha256']
    surface_path.write_bytes(glb_bytes)
    with pytest.raises(WorkflowError, match='hash'): prepare_scene(m)


def test_surface_recipe_cannot_link_other_geometry(tmp_path, glb_bytes):
    from runtime.geometry_acquisition import validate_geometry
    m = ready(tmp_path);client, transport = gateway(glb_bytes)
    result = executor(m, client).run(generated_request())
    result['recipe']['surface_operation']['input_geometry_sha256'] = '0' * 64
    with pytest.raises(WorkflowError, match='linkage'): validate_geometry(m.root, result)


@pytest.mark.parametrize('encoding', ['sparse_uv', 'draco', 'meshopt'])
def test_unsupported_texture_encodings_rejected_before_submit(tmp_path, glb_bytes, encoding):
    raw = paint_glb(glb_bytes)
    size = struct.unpack_from('<I', raw, 12)[0]
    doc = json.loads(raw[20:20 + size]);binary = raw[28 + size:]
    if encoding == 'sparse_uv':
        doc['accessors'][2]['sparse'] = {'count': 1, 'indices': {'bufferView': 9999, 'componentType': 5123}, 'values': {'bufferView': 9999}}
    if encoding == 'draco':
        doc['extensionsRequired'] = ['KHR_draco_mesh_compression']
        doc['meshes'][0]['primitives'][0]['extensions'] = {'KHR_draco_mesh_compression': {'bufferView': 9999, 'attributes': {'POSITION': 0, 'TEXCOORD_0': 1}}}
    if encoding == 'meshopt':
        doc['bufferViews'][2]['extensions'] = {'EXT_meshopt_compression': {'buffer': 9999, 'byteOffset': 0, 'byteLength': 8, 'byteStride': 8, 'count': 3, 'mode': 'ATTRIBUTES'}}
    m = ready(tmp_path);client, transport = gateway(glb_bytes, pack_glb(doc, binary))
    before = m.path.read_bytes()
    with pytest.raises(WorkflowError, match='Unsupported'):
        executor(m, client).run(generated_request())
    assert m.path.read_bytes() == before
    assert [c[1] for c in transport.calls if c[0] == 'POST'] == ['/v1/generate_shape', '/v1/retexture_mesh']


def test_semantic_geometry_normalizes_invalid_document_structure(tmp_path, glb_bytes):
    client, transport = gateway(glb_bytes)
    transport.shape = pack_glb([], b'')
    with pytest.raises(ProviderError, match='model structure'):
        client.generate_geometry(prompt='x', reference_images=[], output_dir=tmp_path/'shape', style_bible={})
    assert [c[1] for c in transport.calls if c[0] == 'POST'] == ['/v1/generate_shape']


def test_texture_transform_coordinate_override_remains_supported(tmp_path, glb_bytes):
    raw = paint_glb(glb_bytes)
    size = struct.unpack_from('<I', raw, 12)[0]
    doc = json.loads(raw[20:20 + size]);binary = raw[28 + size:]
    attrs = doc['meshes'][0]['primitives'][0]['attributes']
    attrs['TEXCOORD_1'] = attrs.pop('TEXCOORD_0')
    doc['materials'][0]['pbrMetallicRoughness']['baseColorTexture']['extensions'] = {'KHR_texture_transform': {'texCoord': 1}}
    m = ready(tmp_path);client, transport = gateway(glb_bytes, pack_glb(doc, binary))
    result = executor(m, client).run(generated_request())
    assert result['surface_sources'][0]['sha256'] == sha256(m.root/result['surface_sources'][0]['path'])
