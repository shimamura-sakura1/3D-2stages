"""Deterministic embedded texture checks; these do not grant visual approval."""
import base64
import json
import struct

from runtime.errors import ValidationError
from runtime.validators import validate_model


def validate_surface_source(path):
    """Require a mesh material's base color texture backed by embedded image bytes."""
    try:
        path = validate_model(path)
    except (AttributeError, TypeError) as exc:
        raise ValidationError('Invalid HY3D surface model structure') from exc
    if path.suffix.lower() != '.glb':
        raise ValidationError('HY3D surface source must be an embedded textured GLB')
    try:
        raw = path.read_bytes()
        json_size = struct.unpack_from('<I', raw, 12)[0]
        doc = json.loads(raw[20:20 + json_size])
        unsupported_compression = {'KHR_draco_mesh_compression', 'EXT_meshopt_compression'}
        if unsupported_compression.intersection(doc.get('extensionsUsed', []) + doc.get('extensionsRequired', [])):
            raise ValueError('Unsupported compressed surface encoding')
        for view in doc.get('bufferViews', []):
            if 'EXT_meshopt_compression' in view.get('extensions', {}):
                raise ValueError('Unsupported meshopt surface encoding')
        binary = None
        offset = 20 + json_size
        while offset < len(raw):
            size, kind = struct.unpack_from('<II', raw, offset)
            if kind == 0x004E4942:
                if binary is not None: raise ValueError('multiple binary chunks')
                binary = raw[offset + 8:offset + 8 + size]
            offset += 8 + size

        def item(collection, index):
            if type(index) is not int or index < 0: raise ValueError('invalid texture resource index')
            return doc[collection][index]

        def embedded_view(index):
            view = item('bufferViews', index)
            buffer = item('buffers', view['buffer'])
            if 'uri' in buffer:
                header, encoded = buffer['uri'].split(',', 1)
                if header not in ('data:application/octet-stream;base64', 'data:application/gltf-buffer;base64'):
                    raise ValueError('unsupported embedded buffer URI')
                contents = base64.b64decode(encoded, validate=True)
            else:
                if view['buffer'] != 0 or binary is None: raise ValueError('missing embedded resource buffer')
                contents = binary
            start, size = view.get('byteOffset', 0), view['byteLength']
            length = buffer['byteLength']
            if any(type(x) is not int for x in (start, size, length)) or start < 0 or size <= 0 or start + size > length or length > len(contents):
                raise ValueError('resource buffer bounds are invalid')
            return contents[start:start + size]

        def embedded_image(image):
            if 'uri' in image:
                header, encoded = image['uri'].split(',', 1)
                if header not in ('data:image/png;base64', 'data:image/jpeg;base64'):
                    raise ValueError('unsupported embedded image URI')
                mime = header[5:-7]
                data = base64.b64decode(encoded, validate=True)
            else:
                data = embedded_view(image['bufferView'])
                mime = image['mimeType']
            if mime == 'image/png':
                if len(data) < 45 or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR' or not all(struct.unpack_from('>II', data, 16)) or b'IDAT' not in data or data[-8:-4] != b'IEND':
                    raise ValueError('invalid embedded PNG')
            elif mime == 'image/jpeg':
                if len(data) < 16 or data[:2] != b'\xff\xd8' or data[-2:] != b'\xff\xd9' or b'\xff\xda' not in data:
                    raise ValueError('invalid embedded JPEG')
            else: raise ValueError('unsupported embedded image MIME type')

        def texture_coordinates(primitive, info):
            coord = info.get('extensions', {}).get('KHR_texture_transform', {}).get('texCoord', info.get('texCoord', 0))
            if type(coord) is not int or coord < 0: raise ValueError('invalid texture coordinate set')
            accessor = item('accessors', primitive['attributes'][f'TEXCOORD_{coord}'])
            if 'sparse' in accessor:
                raise ValueError('Unsupported sparse texture coordinates')
            position = item('accessors', primitive['attributes']['POSITION'])
            count = accessor['count']
            component = accessor['componentType']
            if accessor['type'] != 'VEC2' or type(count) is not int or count <= 0 or count != position['count']:
                raise ValueError('texture coordinates must match the mesh vertices')
            if component not in (5121, 5123, 5126) or (component != 5126 and accessor.get('normalized') is not True):
                raise ValueError('unsupported texture coordinate components')
            view = item('bufferViews', accessor['bufferView'])
            contents = embedded_view(accessor['bufferView'])
            width = {5121: 2, 5123: 4, 5126: 8}[component]
            start, stride = accessor.get('byteOffset', 0), view.get('byteStride', width)
            if type(start) is not int or type(stride) is not int or start < 0 or stride < width or start + (count - 1) * stride + width > len(contents):
                raise ValueError('texture coordinate bounds are invalid')

        associated = False
        for mesh in doc['meshes']:
            for primitive in mesh.get('primitives', []):
                if 'KHR_draco_mesh_compression' in primitive.get('extensions', {}):
                    raise ValueError('Unsupported Draco surface encoding')
                if 'material' not in primitive: continue
                material = item('materials', primitive['material'])
                texture_info = material.get('pbrMetallicRoughness', {}).get('baseColorTexture')
                if texture_info is None: continue
                texture_coordinates(primitive, texture_info)
                texture = item('textures', texture_info['index'])
                embedded_image(item('images', texture['source']))
                associated = True
        if not associated: raise ValueError('no mesh material has an embedded base color texture')
    except (AttributeError, KeyError, IndexError, TypeError, ValueError, struct.error, UnicodeError, OSError) as exc:
        raise ValidationError(f'Invalid HY3D surface source: {exc}') from exc
    return path
