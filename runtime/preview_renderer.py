"""Reserve and finalize explicit preview passes; never approve visual quality."""
import copy
import json
import struct
import zlib
from pathlib import Path
from runtime.errors import BoundaryError
from runtime.io import inside,load_data,atomic_write,sha256
from runtime.validators import validate_contract
from runtime.visual_contracts import require,document_hash
from runtime.visual_planning import current_documents
from runtime.scene_production import prepare_scene,verify_packet


def validate_png(path,width,height):
    try:
        data=Path(path).read_bytes()
        if data[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('signature')
        offset=8;header=None;compressed=[];ended=False
        while offset<len(data):
            length=struct.unpack('>I',data[offset:offset+4])[0];kind=data[offset+4:offset+8]
            end=offset+12+length
            if end>len(data):raise ValueError('truncated chunk')
            body=data[offset+8:offset+8+length];crc=struct.unpack('>I',data[offset+8+length:end])[0]
            if zlib.crc32(kind+body)!=crc:raise ValueError('chunk CRC')
            if kind==b'IHDR':
                if header is not None or offset!=8:raise ValueError('duplicate or misplaced header')
                header=struct.unpack('>IIBBBBB',body)
            elif kind==b'IDAT':compressed.append(body)
            elif kind==b'IEND':
                if length or end!=len(data):raise ValueError('trailing PNG bytes')
                ended=True
            offset=end
        if not ended or not header or not compressed:raise ValueError('incomplete PNG')
        w,h,depth,color,compression,filter_method,interlace=header
        if (w,h)!=(width,height):raise ValueError('dimensions do not match render plan')
        if depth not in (8,16) or color not in (0,2,4,6) or (compression,filter_method,interlace)!=(0,0,0):raise ValueError('unsupported rendered PNG encoding')
        stride=w*{0:1,2:3,4:2,6:4}[color]*(depth//8)+1;size=stride*h
        decoder=zlib.decompressobj();pixels=decoder.decompress(b''.join(compressed),size+1)
        if len(pixels)!=size or not decoder.eof or decoder.unused_data or any(pixels[i*stride]>4 for i in range(h)):raise ValueError('invalid PNG pixels')
    except (OSError,ValueError,struct.error,zlib.error) as exc:
        raise BoundaryError(f'Invalid preview PNG: {exc}') from exc


def inspect_preview(manager,job_path):
    path=Path(job_path).resolve()
    require(path.is_relative_to(manager.root),'Preview job escapes project')
    job=load_data(path)
    require(isinstance(job,dict),"Preview job must be an object")
    packet=verify_packet(job['packet'],job['sha256'])
    require(Path(packet['project']).resolve()==manager.root,'Preview belongs to another project')
    intent_path=Path(job['intent'])
    require(intent_path.is_file() and sha256(intent_path)==job['intent_sha256'],'Preview intent changed')
    intent=load_data(intent_path)
    require(isinstance(intent,dict),"Preview intent must be an object")
    output=packet['plans']['render_plan']['output']['image_path'];directory=Path(output).parent
    require(directory.as_posix()==f"stage2/previews/{job['pass_id']}" and Path(output).name=='preview.png','Invalid preview pass path')
    require(path==inside(manager.root,directory/'job.json') and intent_path==inside(manager.root,directory/'intent.json') and Path(job['receipt'])==inside(manager.root,directory/'worker-receipt.json'),'Preview job paths mismatch')
    plan=packet['plans']['render_plan']
    require(intent['project_id']==packet['project_id'] and intent['scene_version']==packet['scene_version'] and intent['manifest_version']==packet['manifest_version'],'Preview identity/version mismatch')
    require(intent['pass_id']==job['pass_id'] and intent['render_plan_hash']==document_hash(plan),'Preview plan hash mismatch')
    require(Path(job['receipt']).is_file(),'Missing preview worker receipt; queued is not completed')
    receipt=load_data(job['receipt'])
    require(isinstance(receipt,dict),"Preview receipt must be an object")
    for key,value in {'intent_sha256':job['intent_sha256'],'packet_sha256':job['sha256'],'build_id':packet['build_id'],'pass_id':job['pass_id'],'inputs_digest':packet['inputs_digest']}.items():
        require(receipt.get(key)==value,'Preview receipt mismatch: '+key)
    require(type(receipt.get('render_success')) is bool,'Invalid render success flag')
    image=None
    if receipt['render_success']:
        image_path=inside(manager.root,output)
        require(image_path.is_file(),'Missing rendered image')
        require(sha256(image_path)==receipt.get('image_sha256'),'Rendered image hash changed')
        validate_png(image_path,plan['preview']['width'],plan['preview']['height'])
        require(receipt.get('error') is None,'Successful render cannot include an error')
        require(isinstance(receipt.get('geometry_digest'),str) and len(receipt['geometry_digest'])==64,'Missing geometry receipt')
        image={'path':output,'sha256':sha256(image_path)}
    else:require(receipt.get('image_sha256') is None,'Failed render cannot claim an image')
    metadata={'schema_version':'0.2','project_id':packet['project_id'],'scene_version':packet['scene_version'],'document_id':'render_metadata_'+job['pass_id'],'revision':intent['metadata_revision'],'build_id':packet['build_id'],'pass_id':job['pass_id'],'style_profile':packet['style']['id'],'render_plan_id':plan['document_id'],'render_plan_hash':document_hash(plan),'image':image,'render_success':receipt['render_success'],'error':receipt.get('error'),'renderer':plan['renderer'],'timestamp':receipt['timestamp']}
    validate_contract('render_metadata',metadata)
    return packet,metadata

class PreviewRenderer:
    def __init__(self,manager):self.manager=manager
    def prepare(self):
        m=self.manager.reserve_preview(expected_version=self.manager.read()['version'])
        result=prepare_scene(self.manager);packet=load_data(result['packet'])
        directory=Path(packet['plans']['render_plan']['output']['image_path']).parent
        intent=inside(self.manager.root,directory/'intent.json');job_path=inside(self.manager.root,directory/'job.json')
        job={**result,'pass_id':directory.name,'intent':str(intent),'intent_sha256':sha256(intent),'receipt':str(inside(self.manager.root,directory/'worker-receipt.json')),'job':str(job_path)}
        worker=packet['workers']['operations']
        job['execute_code']=f"import runpy; worker=runpy.run_path({worker!r}); worker['render_job']({job['packet']!r}, {job['sha256']!r}, {job['intent']!r}, {job['intent_sha256']!r})"
        atomic_write(job_path,job)
        return job
    def complete(self,job_path):
        packet,metadata=inspect_preview(self.manager,job_path)
        state=self.manager.record_preview(job_path,expected_version=packet['manifest_version'])
        return load_data(inside(self.manager.root,state['artifacts']['render_metadata'][-1]['path']))
