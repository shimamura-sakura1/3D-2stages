"""Validate separated plans and prepare reproducible MCP operations."""
import copy
import json
from pathlib import Path
from runtime.errors import BoundaryError
from runtime.io import inside,load_data,atomic_write,sha256
from runtime.validators import validate_contract
from runtime.visual_contracts import require,unique,document_hash
from runtime.visual_planning import current_documents,validate_plan
from runtime.geometry_acquisition import validate_geometry
from runtime.style_resolver import resolve_material
from runtime.style_registry import StyleRegistry

PLAN_KINDS=('blockout_plan','semantic_material_map','lookdev_plan','render_plan')

def validate_scene_plans(manager,m,plans):
    require(set(plans)==set(PLAN_KINDS),'Exactly four separated scene plans are required')
    docs=current_documents(manager,m);validate_plan(manager.root,m,docs)
    assets=m.get('geometry_assets',{});objects={o['object_id'] for o in docs['scene_spec']['objects']}
    require(set(assets)==objects and all(a['status']=='approved' for a in assets.values()),'Current approved geometry is required')
    for a in assets.values():validate_geometry(manager.root,a['versions'][-1])
    for k,p in plans.items():
        validate_contract(k,p)
        require((p['project_id'],p['scene_version'])==(m['project_id'],m['scene_version']),'Plan project/scene mismatch')
    unique(plans.values(),'document_id','plan document')
    placement=unique(plans['blockout_plan']['objects'],'object_id','placement')
    require(set(placement)==objects,'Blockout must cover every scene object')
    for key,p in placement.items():
        result=assets[key]['versions'][-1]
        require(p['geometry_source']==result['geometry']['source'],'Blockout geometry source mismatch')
        require(p['asset_id'] in (key,None) and (p['asset_id']==key or p['geometry_source']=='procedural'),'Blockout asset identity mismatch')
        seen={key};parent=p['parent']
        while parent is not None:
            require(parent in placement and parent not in seen,'Invalid blockout hierarchy')
            seen.add(parent);parent=placement[parent]['parent']
    mappings=plans['semantic_material_map']['mappings']
    require({x['object_id'] for x in mappings}==objects and len(mappings)==len(objects),'One complete semantic material mapping per object is required')
    for item in mappings:
        require(item['slot']=='body','Unsupported material slot; this version supports body')
        require(item['surface_source'] is None,'Explicit surface-source blending is not implemented; retain sources for later use')
        resolve_material(docs['style_assignment']['style_profile'],item['material_class'],item['condition'],version=docs['style_assignment']['profile_version'])
    look=plans['lookdev_plan'];render=plans['render_plan'];style=docs['style_assignment']
    require(look['style_assignment_id']==style['document_id'] and look['material_map_id']==plans['semantic_material_map']['document_id'],'Lookdev document link mismatch')
    require(look['lighting']['profile']==style['lighting_profile'] and look['atmosphere']['profile']==style['atmosphere_profile'],'Lookdev profile mismatch')
    require(render['camera']['profile']==style['camera_profile'] and render['color']['profile']==style['color_profile'],'Render profile mismatch')
    require(render['camera']['location']!=render['camera']['target'],'Camera location and target must differ')
    require(render['purpose']=='preview','Only preview rendering is implemented')
    profile=StyleRegistry().load(style['style_profile'],version=style['profile_version'])
    if 'signature' in profile:
        low,high=profile['signature']['dimensions']['composition']['focal_length_mm_range']
        require(low<=render['camera']['focal_length_mm']<=high,'Camera focal length is outside style signature bounds')
    require(Path(render['output']['image_path']).suffix.lower()=='.png','Preview output must be PNG')
    return docs

def verify_packet(path,expected_sha):
    from runtime.blender_operations import read_packet
    try:return read_packet(path,expected_sha)
    except (ValueError,OSError,KeyError) as exc:raise BoundaryError(str(exc)) from exc

def prepare_scene(manager):
    m=manager.read()
    if m['mode'] not in ('full_pipeline','stage2_only','repair') or m['state'] not in ('blockout_pending','render_pending'):
        raise BoundaryError('Scene preparation requires authorized mode and submitted plans')
    plans=current_documents(manager,m,PLAN_KINDS);docs=validate_scene_plans(manager,m,plans)
    geometry={k:a['versions'][-1] for k,a in m['geometry_assets'].items()}
    blockout_key=document_hash({'geometry_fingerprint_format':2,'blockout':plans['blockout_plan'],'geometry':geometry})
    build_id='build_'+blockout_key[:16]
    style=StyleRegistry().load(docs['style_assignment']['style_profile'],version=docs['style_assignment']['profile_version'])
    materials={x['object_id']:resolve_material(style['id'],x['material_class'],x['condition'],version=style['version']) for x in plans['semantic_material_map']['mappings']}
    inputs_digest=document_hash({'plans':plans,'style':docs['style_assignment'],'geometry':geometry})
    directory=f'stage2/builds/{build_id}/{inputs_digest[:16]}'
    root=Path(__file__).resolve().parents[1]
    dependencies=[manager.path]
    blockout_file=inside(manager.root,f'stage2/builds/{build_id}/blockout.blend')
    if blockout_file.is_file():dependencies.append(blockout_file)
    for kind in (*PLAN_KINDS,'visual_brief','reference_board','scene_spec','style_assignment'):
        records=[r for r in m['artifacts'][kind] if r['scene_version']==m['scene_version']]
        dependencies.append(inside(manager.root,max(records,key=lambda r:r['revision'])['path']))
    for result in geometry.values():
        if result['geometry']['model']:dependencies.append(inside(manager.root,result['geometry']['model']))
        dependencies.extend(inside(manager.root,s['path']) for s in result['surface_sources'])
    # Hash only the selected version; the legacy root contains newer versions.
    style_root=Path(style['root'])
    selected_paths=['profile.yaml',*style['components'].values(),*style['resources'].values()]
    dependencies.extend(inside(style_root,path) for path in selected_paths)
    rubric=inside(style_root,'critic/rubric.yaml')
    if rubric.is_file():dependencies.append(rubric)
    workers={k:str(root/'runtime'/filename) for k,filename in {'operations':'blender_operations.py','geometry':'blender_geometry_worker.py','style':'blender_style_worker.py'}.items()}
    dependencies.extend(Path(p) for p in workers.values())
    from runtime.blender_operations import OPERATIONS
    packet={'project':str(manager.root),'project_id':m['project_id'],'manifest_version':m['version'],'scene_version':m['scene_version'],'build_id':build_id,'blockout_key':blockout_key,'inputs_digest':inputs_digest,'plans':plans,'geometry':geometry,'materials':materials,'style':style,'workers':workers,'operations':list(OPERATIONS),'guard':{str(p.resolve()):sha256(p) for p in dependencies},'outputs':{'blockout':str(inside(manager.root,f'stage2/builds/{build_id}/blockout.blend')),'setup':str(inside(manager.root,directory+'/setup.blend')),'receipt':str(inside(manager.root,directory+'/setup-receipt.json')),'preview':str(inside(manager.root,plans['render_plan']['output']['image_path']))}}
    path=inside(manager.root,f'stage2/operations/{build_id}/request-v{m["version"]}.json')
    if path.exists():
        require(load_data(path)==packet,'Existing operation packet differs; regenerate with a new manifest version')
    else:atomic_write(path,packet)
    digest=sha256(path)
    return {'status':'prepared','backend':'mcp','build_id':build_id,'packet':str(path),'sha256':digest,'operations':list(OPERATIONS),'execute_code':f"import runpy; ops=runpy.run_path({workers['operations']!r}); ops['run']({str(path)!r}, {digest!r}, 'asset.import')"}

def check_setup_receipt(manager,path,expected_sha):
    packet=verify_packet(path,expected_sha)
    require(Path(packet['project']).resolve()==manager.root,'Operation packet belongs to another project')
    receipt_path=Path(packet['outputs']['receipt'])
    require(receipt_path.is_file(),'Missing completed setup receipt')
    receipt=load_data(receipt_path)
    require(receipt.get('status')=='setup_complete' and receipt.get('build_id')==packet['build_id'] and receipt.get('inputs_digest')==packet['inputs_digest'],'Stale or incomplete setup receipt')
    require(receipt.get('geometry_before')==receipt.get('geometry_after') and isinstance(receipt.get('geometry_after'),str) and len(receipt['geometry_after'])==64,'Lookdev changed geometry')
    blend=Path(packet['outputs']['setup'])
    require(blend.is_file() and blend.read_bytes()[:7]==b'BLENDER' and sha256(blend)==receipt.get('blend_sha256'),'Missing or changed Blender scene')
    return packet

def complete_setup(manager,path,expected_sha):
    packet=check_setup_receipt(manager,path,expected_sha)
    return manager.complete_scene_setup(path,expected_sha,expected_version=packet['manifest_version'])
