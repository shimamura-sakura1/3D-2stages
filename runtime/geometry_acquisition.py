"""Acquire geometry and propose a versioned result; material and review remain separate."""
import copy
import math
import shutil
import uuid
from contextlib import nullcontext
from runtime.asset_search import search_assets
from runtime.asset_router import AssetRouter
from runtime.geometry_router import GeometryRouter
from runtime.errors import BoundaryError
from runtime.io import inside,sha256
from runtime.validators import validate_contract,validate_model
from runtime.visual_planning import current_documents,validate_plan
from runtime.style_resolver import resolve_material
from runtime.hy3d_surface import validate_surface_source


def validate_geometry(root,result):
    validate_contract('geometry_result',result)
    geometry=result['geometry'];route=result['route']
    if result['recipe'].get('conditioning_mode')=='image_only':
        if route!='C' or len(result['recipe']['reference_sha256'])!=1:raise BoundaryError('Invalid image_only conditioning reference linkage')
    if not AssetRouter().legal({'source':result['provenance']},modification=True,generated_output=route=='C'):raise BoundaryError('Unverified geometry rights')
    if route=='D':
        if geometry['source']!='procedural' or geometry['primitive'] is None or geometry['model'] is not None or geometry['sha256'] is not None:raise BoundaryError('Invalid procedural geometry result')
    else:
        if geometry['source']!=('generated' if route=='C' else 'library') or geometry['primitive'] is not None or not geometry['model']:raise BoundaryError('Invalid acquired geometry result')
        path=inside(root,geometry['model']);validate_model(path)
        if sha256(path)!=geometry['sha256']:raise BoundaryError('Geometry hash mismatch')
    for surface in result['surface_sources']:
        if sha256(inside(root,surface['path']))!=surface['sha256']:raise BoundaryError('Surface source hash mismatch')
        if surface['kind']=='hy3d_paint':
            if route!='C' or surface.get('role')!='reference_only' or surface['path']==geometry['model']:raise BoundaryError('HY3D paint must remain separate reference-only evidence')
            validate_surface_source(inside(root,surface['path']))
    painted=[s for s in result['surface_sources'] if s['kind']=='hy3d_paint']
    operation=result['recipe'].get('surface_operation')
    if painted:
        if len(painted)!=1 or not operation or operation['input_geometry_sha256']!=geometry['sha256']:raise BoundaryError('Surface operation geometry linkage mismatch')
    elif operation is not None:raise BoundaryError('Surface operation requires retained paint evidence')
    return result

class GeometryAcquisition:
    def __init__(self,manager,providers,hy3d=None):
        self.manager=manager;self.providers=providers;self.hy3d=hy3d
    def run(self,request):
        m=self.manager.read()
        if m['schema_version']!='0.2' or m['mode'] not in ('full_pipeline','stage1_only','repair'):
            raise BoundaryError('Geometry acquisition prohibited in this mode')
        if m['state'] not in ('visual_approved','geometry_pending'):
            raise BoundaryError('Current visual approval is required before geometry acquisition')
        docs=current_documents(self.manager,m);validate_plan(self.manager.root,m,docs)
        required={'task','primitive','preferred_route','modification','material_class','condition','reference_ids'}
        if not isinstance(request,dict) or not required.issubset(request) or set(request)-required-{'surface_evidence','image_only'}:raise BoundaryError('Invalid geometry request fields')
        surface_evidence=request.get('surface_evidence',False)
        if type(surface_evidence) is not bool:raise BoundaryError('surface_evidence must be a boolean')
        image_only=request.get('image_only',False)
        if type(image_only) is not bool:raise BoundaryError('image_only must be a boolean')
        task=request['task'];validate_contract('asset_task',task);asset_id=task['asset_id']
        if image_only:
            if task['hy3d']['prompt']!='':raise BoundaryError('image_only cannot discard explicit HY3D prompt conditioning')
            if not isinstance(request['reference_ids'],list) or len(request['reference_ids'])!=1 or not isinstance(request['reference_ids'][0],str):raise BoundaryError('image_only requires exactly one reference ID')
        objects={o['object_id']:o for o in docs['scene_spec']['objects']}
        if asset_id not in objects or objects[asset_id]['size_m'] is None:raise BoundaryError('Geometry requires a declared scene object and dimensions')
        existing=m.get('geometry_assets',{}).get(asset_id)
        if existing and existing['status']!='revision_requested':raise BoundaryError('Geometry already awaits review; request rework first')
        revision=len(existing['versions']) if existing else 0
        if revision>3:raise BoundaryError('Geometry revision limit reached')
        modification=request['modification']
        if modification is not None:
            if not isinstance(modification,dict) or set(modification)!={'scale'}:raise BoundaryError('Unsupported geometry modification')
            scale=modification['scale']
            if not isinstance(scale,list) or len(scale)!=3 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<=0 for x in scale):raise BoundaryError('Invalid modification scale')
        style=docs['style_assignment']['style_profile']
        resolve_material(style,request['material_class'],request['condition'],version=docs['style_assignment']['profile_version'],project_root=self.manager.root)
        report=search_assets(task,self.providers);route,candidate=GeometryRouter().choose(request,report)
        if surface_evidence and route!='C':raise BoundaryError('Surface evidence is supported only for Route C')
        if image_only and route!='C':raise BoundaryError('image_only is supported only for Route C')
        references={r['reference_id']:r for r in docs['reference_board']['references']}
        selected=[]
        for key in request['reference_ids']:
            if key not in references:raise BoundaryError('Unknown generation reference')
            ref=references[key]
            if not ref['source']['license_verified'] or ref['source']['license'] not in ('cc0','cc_by'):
                raise BoundaryError('Generation reference rights are unverified or unsupported')
            if ref['source']['license']=='cc_by' and not ref['source']['attribution'].strip():raise BoundaryError('Missing reference attribution')
            selected.append(inside(self.manager.root,ref['path']))
        if image_only and selected[0].suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):raise BoundaryError('image_only requires a PNG, JPEG or WebP reference')
        if route=='C':
            if self.hy3d is None:raise BoundaryError('HY3D gateway is not configured')
            source=self.hy3d.config.get('output_source')
            if not source or not AssetRouter().legal({'source':source},modification=True,generated_output=True):raise BoundaryError('Unverified HY3D output rights')
        elif candidate:source=candidate['source']
        else:source={'provider':'blender_procedural','asset_id':asset_id,'original_url':'local:bounded-primitives-v1','creator':'Two-Stage 3D','license':'cc0','license_verified':True,'attribution_required':False,'modification_allowed':True}
        # Fully validate metadata before external work or filesystem output.
        validate_contract('asset_candidate',dict(candidate or {'candidate_id':asset_id,'provider':source['provider'],'source':source,'model':'prospective.obj','format':'obj','scale_m':1,'geometry_usable':True,'scores':{k:1 for k in ('semantic_fit','geometry_quality','style_fit','editability','texture_quality','cleanup_cost')},'keywords':[asset_id]}))
        root=self.manager.root;folder=inside(root,f'stage1/geometry/{asset_id}/rev{revision:02d}-{uuid.uuid4().hex[:8]}')
        model=None;source_hash=None;surfaces=[];surface_operation=None;geometry_operation='generate_shape'
        if candidate:
            original=self.providers[candidate['provider']].acquire(candidate['candidate_id'],folder/'source');validate_model(original)
            if not original.resolve().is_relative_to((folder/'source').resolve()):raise BoundaryError('Provider returned geometry outside its source directory')
            source_hash=sha256(original);model=folder/('asset'+original.suffix);shutil.copy2(original,model)
            surfaces=[{'kind':'original_surface','path':original.relative_to(root).as_posix(),'sha256':source_hash}]
        elif route=='C':
            semantic=getattr(self.hy3d,'generate_geometry',None)
            generate=semantic if callable(semantic) else self.hy3d.generate_shape
            geometry_operation='generate_geometry' if callable(semantic) else 'generate_shape'
            if surface_evidence and (not callable(getattr(self.hy3d,'generate_surface_source',None)) or not callable(getattr(self.hy3d,'operation_scope',None))):raise BoundaryError('Gateway does not support semantic surface evidence preflight')
            scope=self.hy3d.operation_scope(('generate_shape','retexture_mesh')) if surface_evidence else nullcontext()
            with scope:
                kwargs=dict(prompt='' if image_only else task['hy3d']['prompt'] or task['target']['description'],reference_images=selected,style_bible={},seed=revision)
                model=validate_model(generate(output_dir=folder,**kwargs))
                if not model.resolve().is_relative_to(folder.resolve()):raise BoundaryError('Gateway returned geometry outside its output directory')
                original_hash=sha256(model)
                if surface_evidence:
                    paint_dir=folder/'surface-source'
                    paint=validate_surface_source(self.hy3d.generate_surface_source(mesh=model,output_dir=paint_dir,**kwargs))
                    if not paint.resolve().is_relative_to(paint_dir.resolve()) or paint.resolve()==model.resolve():raise BoundaryError('Gateway returned surface outside its separate output directory')
                    if sha256(model)!=original_hash:raise BoundaryError('Surface generation changed the original geometry')
                    surfaces=[{'kind':'hy3d_paint','role':'reference_only','path':paint.relative_to(root).as_posix(),'sha256':sha256(paint)}]
                    surface_operation={'operation':'generate_surface_source','gateway_operation':'retexture_mesh','input_geometry_sha256':original_hash}
        result={'schema_version':'0.2','asset_id':asset_id,'revision':revision,'scene_version':m['scene_version'],'route':route,
                'geometry':{'source':{'A':'library','B':'library','C':'generated','D':'procedural'}[route],'primitive':request['primitive'] if route=='D' else None,'model':model.relative_to(root).as_posix() if model else None,'sha256':sha256(model) if model else None},
                'scale':{'unit':'meter','source_scale_m':candidate['scale_m'] if candidate else 1,'dimensions_m':objects[asset_id]['size_m']},
                'surface_semantics':{'material_class':request['material_class'],'condition':request['condition']},'surface_sources':surfaces,'provenance':copy.deepcopy(source),
                'recipe':{'searched_providers':list(report.providers),'operation':{'A':'library_direct','B':'library_modify','C':geometry_operation,'D':'procedural'}[route],'modification':modification if route=='B' else None,'source_sha256':source_hash,'reference_sha256':[sha256(p) for p in selected],'backend':self.hy3d.kind if route=='C' else None}}
        if surface_operation is not None:result['recipe']['surface_operation']=surface_operation
        if image_only:result['recipe']['conditioning_mode']='image_only'
        validate_geometry(root,result)
        self.manager.submit_geometry(result,expected_version=m['version'])
        return result
