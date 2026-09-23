"""Production-owned visual task snapshots; an Agent supplies visual decisions."""
import copy
import hashlib
import json
import sys
import uuid
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from runtime.errors import WorkflowError
from runtime.io import inside, sha256
from runtime.validators import validate_contract
from runtime.visual_contracts import document_hash, require
from runtime.visual_planning import current_documents
from runtime.style_registry import StyleRegistry, style_files

OPERATIONS=('create_direction','review_render','refine_direction')
INPUTS={'visual_brief':'brief','scene_context':'scene','style_context':'style',
        'knowledge_context':'knowledge','scene_state':'scene_state','references':'references',
        'previous_render_direction':'direction','previous_render_review':'review'}


class _AlreadyPrepared(Exception):
    def __init__(self,record):self.record=copy.deepcopy(record)


def encoded(value):
    return (json.dumps(value,ensure_ascii=False,allow_nan=False,sort_keys=True,indent=2)+'\n').encode('utf-8')


def strict_json(path):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'Duplicate JSON key: '+key);result[key]=value
        return result
    def invalid(value):raise ValueError('Nonfinite JSON: '+value)
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=pairs,parse_constant=invalid)


def baseline(manifest):
    return document_hash({k:v for k,v in manifest.items() if k not in ('version','history','visual_tasks')})


def style_snapshot(manager,manifest):
    doc=current_documents(manager,manifest,('style_assignment',))['style_assignment']
    style=StyleRegistry().load(doc['style_profile'],version=doc['profile_version'],project_root=manager.root)
    paths=set(style_files(style))
    base=Path(style['root'])
    paths.update(p.relative_to(base).as_posix() for p in (base/'semantic').glob('*.yaml'))
    hashes={p:sha256(inside(base,p)) for p in sorted(paths) if inside(base,p).is_file()}
    return style,hashes


def acceptance_path(record):
    return (Path(record['request_path']).parent/'accepted-record.json').as_posix()


def read_task(manager,task_id,manifest=None,*,fresh=False):
    m=manifest if manifest is not None else manager.read()
    require(task_id in m.get('visual_tasks',{}),'Unknown visual task')
    record=m['visual_tasks'][task_id]
    validate_contract('visual_task_record',record)
    require(record['task_id']==task_id and record['scene_version']<=m['scene_version'],'Invalid task scene identity')
    if fresh:require(record['scene_version']==m['scene_version'],'Stale task scene identity')
    for relative,digest in record['files'].items():
        require(sha256(inside(manager.root,relative))==digest,'Visual task input or result changed: '+relative)
    if record['status']=='accepted':
        path=acceptance_path(record);require(path in record['files'],'Accepted task provenance is missing')
        expected=copy.deepcopy(record);expected['files'].pop(path)
        require(strict_json(inside(manager.root,path))==expected,'Accepted task provenance changed')
    request=strict_json(inside(manager.root,record['request_path']))
    validate_contract('visual_task_request',request)
    require((request['task_id'],request['operation'])==(task_id,record['operation']),'Task request identity mismatch')
    context=strict_json(inside(manager.root,record['context_path']))
    if fresh:
        require(record['source_hash']==baseline(m),'Visual task source changed; prepare a new task')
        _,hashes=style_snapshot(manager,m)
        require(hashes==context['style_hashes'],'Selected style resources changed')
    folder=inside(manager.root,record['request_path']).parent
    values={key:strict_json(inside(folder,path)) for key,path in request['inputs'].items()
            if path is not None and key!='render_image'}
    for key,value in values.items():validate_contract('visual_task_'+INPUTS[key],value)
    return record,request,context,values


def _project_inputs(manager,m,spec):
    docs=current_documents(manager,m)
    operation=spec['operation']
    if operation=='create_direction':
        require(m['state']=='geometry_approved' and not m.get('visual_direction') and not m.get('render_direction'),
                'Creation requires approved geometry and no registered direction')
        scene=copy.deepcopy(spec['scene_context']);plans=copy.deepcopy(spec['plans'])
    else:
        require(m.get('visual_direction'),'No current visual task direction')
        prior,_,internal,_=read_task(manager,m['visual_direction'],m)
        scene=copy.deepcopy(internal['scene_context'])
        from runtime.scene_production import PLAN_KINDS
        plans=current_documents(manager,m,PLAN_KINDS)
    validate_contract('scene_context',scene)
    require(scene['production']['project_id']==m['project_id'] and scene['production']['scene_version']==m['scene_version'],
            'Measured scene belongs to another project or version')
    require(scene['production'].get('geometry_hash')==document_hash(m['geometry_assets']) and
            scene['production'].get('scene_spec_hash')==document_hash(docs['scene_spec']) and
            scene['production'].get('blockout_hash')==document_hash(plans['blockout_plan']),
            'Measured geometry or blockout changed')
    style,hashes=style_snapshot(manager,m)
    from runtime.render_context_builder import visual_task_inputs
    values=visual_task_inputs(m,docs,scene,style)
    blobs={}
    if operation!='create_direction':
        values['previous_render_direction']=strict_json(inside(manager.root,prior['result_path']))
        from runtime.visual_review import current_render_context
        rendered=current_render_context(manager)
        metadata=rendered['documents']['render_metadata']
        blobs['render_image']=inside(manager.root,metadata['image']['path']).read_bytes()
        if operation=='review_render':
            require(m['state'] in ('render_review_required','visual_revision'),'No current render awaiting review')
        else:
            require(m['state']=='visual_revision' and m.get('visual_review_task'),'No accepted visual review for refinement')
            review,_,_,_=read_task(manager,m['visual_review_task'],m)
            values['previous_render_review']=strict_json(inside(manager.root,review['result_path']))
            require(values['previous_render_review']['direction_id']==values['previous_render_direction']['direction_id'] and
                    values['previous_render_review']['direction_revision']==values['previous_render_direction']['revision'],
                    'Review does not belong to current direction')
            from runtime.revision_controller import enforce_preview_budget
            enforce_preview_budget(manager,m)
        values['scene_state']={'schema_version':'1.0','scene_id':m['project_id'],'scene_version':m['scene_version'],
            'observations':[],'active_constraints':['Approved geometry must remain unchanged.'],'preserve':['approved_geometry']}
        if m.get('visual_review_task'):
            r,_,_,_=read_task(manager,m['visual_review_task'],m)
            report=strict_json(inside(manager.root,r['result_path']))
            values['scene_state']['observations']=[{'id':f'observation-{i}','content':item['observation'],
                'source':r['result_path']+'#'+r['files'][r['result_path']]} for i,item in enumerate([*report['findings'],*report['successful_decisions']])]
    # Copy only explicitly selected, valid raster references; never reinterpret SVG bytes.
    selected=spec.get('reference_ids',[])
    if selected:
        refs={r['reference_id']:r for r in docs['reference_board']['references']}
        require(set(selected)<=set(refs),'Unknown requested reference')
        entries=[]
        for i,identity in enumerate(selected):
            from runtime.reference_manager import check_reference
            from runtime.preview_renderer import validate_png
            import struct
            ref=refs[identity]; path=check_reference(manager.root,ref)
            require(path.suffix.lower()=='.png','Prepare a traceable PNG derivative for non-PNG references')
            data=path.read_bytes(); require(data[:8]==b'\x89PNG\r\n\x1a\n','Invalid reference PNG')
            require(len(data)>=24,'Truncated reference PNG')
            validate_png(path,*struct.unpack('>II',data[16:24]))
            relative=f'inputs/references/{i}.png';blobs[relative]=data
            entries.append({'id':identity,'path':relative,'role':','.join(ref['roles']),
                            'description':json.dumps(ref['source'],ensure_ascii=False)})
        values['references']={'schema_version':'1.0','references':entries}
    return values,blobs,{'scene_context':scene,'plans':plans,'style_hashes':hashes}


def prepare(manager,spec,*,expected_version):
    spec=copy.deepcopy(spec); result={}
    def mutate(m):
        require(set(spec)<= {'operation','scene_context','plans','reference_ids','execution_config','knowledge'},'Unknown task preparation field')
        require(spec.get('operation') in OPERATIONS,'Unknown visual operation')
        require(m['mode'] in ('full_pipeline','stage2_only','repair'),'Visual task requires authorized execution')
        values,blobs,context=_project_inputs(manager,m,spec)
        from runtime.env_config import visual_execution_config
        from runtime.visual_task_adapter import select_executor
        config=visual_execution_config(spec.get('execution_config'))
        selection=select_executor(config)
        from runtime.knowledge_resolver import resolve_knowledge
        knowledge=spec.get('knowledge',{})
        require(set(knowledge)<={'item_ids','renderer','renderer_version','applicability_notes'},'Unknown knowledge routing field')
        knowledge_home=config.get('knowledge_home')
        if knowledge_home and not Path(knowledge_home).is_dir():knowledge_home=None
        renderer=context['plans']['render_plan']['renderer']
        require(knowledge.get('renderer',renderer)==renderer,'Knowledge renderer differs from the production plan')
        resolved,evidence=resolve_knowledge(knowledge_home,knowledge.get('item_ids',[]),spec['operation'],
            renderer,values['scene_context']['scene_type'])
        if resolved:values['knowledge_context']=resolved
        context['knowledge_selection']={'query':knowledge,'items':evidence}
        fingerprint=document_hash({'spec':spec,'values':values,'context':context,'selection':selection,
            'blobs':{key:hashlib.sha256(data).hexdigest() for key,data in blobs.items()}})
        for old in m.get('visual_tasks',{}).values():
            if old['source_hash']==baseline(m) and old['selection'].get('preparation_hash')==fingerprint and old['status']!='accepted':
                read_task(manager,old['task_id'],m,fresh=True)
                raise _AlreadyPrepared(old)
        selection['preparation_hash']=fingerprint
        task_id='vt_'+uuid.uuid4().hex[:20]; base=f'stage2/visual_tasks/{task_id}'
        record={'task_id':task_id,'operation':spec['operation'],'scene_version':m['scene_version'],
            'status':'prepared','executor':selection['executor'],'request_path':base+'/request.json','context_path':base+'/context.json',
            'files':{},'source_hash':baseline(m),'source_version':m['version'],'attempt':0,
            'events':[{'status':'prepared','reason':'Inputs prepared; Agent execution required.'}],
            'result_path':None,'execution_path':None,'selection':selection}
        request={'schema_version':'1.0','task_id':task_id,'operation':spec['operation'],'inputs':{},
            'outputs':{'error':'outputs/error.json','render_review' if spec['operation']=='review_render' else 'render_direction':'outputs/result.json'}}
        pending=[]
        def add(relative,data):
            path=base+'/'+relative;raw=data if isinstance(data,bytes) else encoded(data)
            pending.append((path,raw));record['files'][path]=hashlib.sha256(raw).hexdigest()
        for key,value in values.items():
            validate_contract('visual_task_'+INPUTS[key],value)
            relative='inputs/'+key+'.json';request['inputs'][key]=relative;add(relative,value)
        for key,data in blobs.items():
            relative='inputs/render/preview.png' if key=='render_image' else key
            if key=='render_image':request['inputs'][key]=relative
            add(relative,data)
        validate_contract('visual_task_request',request)
        add('request.json',request);add('context.json',context)
        m.setdefault('visual_tasks',{})[task_id]=record;result.update(copy.deepcopy(record))
        return pending
    try:manager._visual_change('visual_task_prepared',mutate,expected_version)
    except _AlreadyPrepared as existing:return existing.record
    return result


def start(manager,task_id,*,expected_version):
    def mutate(m):
        record,request,_,_=read_task(manager,task_id,m,fresh=True)
        require(record['status'] in ('prepared','failed','interrupted'),'Task already started or completed')
        require(record['attempt']<3,'Visual task attempt limit reached')
        require(not record['selection'].get('input_error'),'Resolve the reported task error; switching executor cannot bypass it')
        folder=inside(manager.root,record['request_path']).parent
        require(not any(inside(folder,p).exists() for p in request['outputs'].values()),'Collect existing output before retrying')
        from runtime.visual_task_adapter import invocation
        if record['executor']=='external' and record['status'] in ('failed','interrupted') and record['selection'].get('mode','auto')=='auto':
            old=record['selection']
            record['selection']={'executor':'main','mode':'auto','transport':'local_agent',
                'reason':'Main took over a confirmed ended attempt.','preparation_hash':old.get('preparation_hash')}
            record['executor']='main'
            record['events'].append({'status':record['status'],'reason':'Previous execution selection: '+json.dumps(old,ensure_ascii=False)})
        try:call=invocation(record['selection'],folder,record['operation'])
        except (OSError,WorkflowError) as exc:
            require(record['executor']=='external' and record['selection'].get('mode')=='auto',str(exc))
            old=record['selection']
            record['selection']={'executor':'main','mode':'auto','transport':'local_agent','reason':str(exc),
                                 'preparation_hash':old.get('preparation_hash')}
            record['executor']='main'
            record['events'].append({'status':record['status'],'reason':'Unavailable selection: '+json.dumps(old,ensure_ascii=False)})
            call=invocation(record['selection'],folder,record['operation'])
        record['selection']['invocation']=call
        record['status']='running';record['attempt']+=1
        record['events'].append({'status':'running','reason':'Caller Agent explicitly started this attempt.'})
    manager._visual_change('visual_task_started',mutate,expected_version)
    return status(manager,task_id)


def _preserved(previous,decision,locks):
    aliases={'focal_length':'camera.focal_length_mm'}
    for lock in locks:
        path=aliases.get(lock,lock)
        if path.split('.')[0] not in ('camera','composition','lighting','atmosphere'):continue
        old,new=previous,decision
        for key in path.split('.'):
            require(isinstance(old,dict) and key in old and isinstance(new,dict) and key in new,'Unknown preserved path')
            old,new=old[key],new[key]
        require(old==new,'Direction changed a preserved field: '+lock)


def check_decision(request,values,decision):
    operation=request['operation'];review=operation=='review_render'
    validate_contract('visual_task_review' if review else 'visual_task_direction',decision)
    brief=values['visual_brief'];prior=values.get('previous_render_direction')
    locks=set(brief['preserve'])|set(values.get('scene_state',{}).get('preserve',[]))
    if prior:locks.update(prior['preserve'])
    old_review=values.get('previous_render_review')
    if old_review:locks.update(old_review['preserve'])
    require(locks<=set(decision['preserve']),'Decision dropped preserve constraints')
    if review:
        require((decision['direction_id'],decision['direction_revision'])==(prior['direction_id'],prior['revision']), 'Review direction identity mismatch')
        require(decision['render_path']==request['inputs']['render_image'],'Review must identify exact current image')
        require(not any(decision['recommended_changes'].values()) or bool(decision['findings']),'Recommendations require visible findings')
        for section in ('camera','composition','lighting','atmosphere'):
            require(section not in locks or not decision['recommended_changes'][section],'Review changes preserved section')
    else:
        require(decision['camera']['subject_ref']==values['scene_context']['primary_subject']['id'],'Direction subject identity mismatch')
        require(decision['camera']['subject_coverage']>0 and decision['camera']['focal_length_mm']>0,'Unexecutable coverage or focal length')
        require(set(brief['avoid'])|set(values['style_context']['avoid'])<=set(decision['avoid']),'Decision dropped avoid constraints')
        if operation=='create_direction':require(decision['parent_direction_id'] is None,'Initial direction cannot have a parent')
        else:
            require(decision['parent_direction_id']==prior['direction_id'] and decision['revision']>prior['revision'],'Invalid direction lineage')
            _preserved(prior,decision,locks)
            for section in ('camera','composition','lighting','atmosphere'):
                require(decision[section]==prior[section] or bool(old_review['recommended_changes'][section]),'Changed an unreviewed section')


def submit(manager,task_id,decision,*,expected_version,execution=None):
    decision=copy.deepcopy(decision)
    def mutate(m):
        record,request,context,values=read_task(manager,task_id,m,fresh=True)
        require(record['status']=='running' or (record['status']=='interrupted' and record['executor']=='external'),
                'Only a started task can submit a result')
        check_decision(request,values,decision)
        if record['executor']=='external':
            folder=inside(manager.root,record['request_path']).parent
            key='render_review' if record['operation']=='review_render' else 'render_direction'
            require(strict_json(inside(folder,request['outputs'][key]))==decision,'External result must match its published file')
        base=Path(record['request_path']).parent.as_posix();pending=[]
        for label,value in [('result',decision),('execution',execution)]:
            if value is None:continue
            path=f'{base}/{label}-attempt-{record["attempt"]}.json';raw=encoded(value)
            pending.append((path,raw));record['files'][path]=hashlib.sha256(raw).hexdigest();record[label+'_path']=path
        record['status']='result_available';record['events'].append({'status':'result_available','reason':'Candidate validated; production acceptance is separate.'})
        return pending
    manager._visual_change('visual_task_result_submitted',mutate,expected_version)
    return status(manager,task_id)


def status(manager,task_id):
    record,request,_,_=read_task(manager,task_id)
    result=copy.deepcopy(record);folder=inside(manager.root,record['request_path']).parent
    published={k:p for k,p in request['outputs'].items() if inside(folder,p).is_file()}
    action={'accepted':'continue','result_available':'accept_result','prepared':'start',
            'running':'verify_execution','interrupted':'resume','failed':'resolve_error'}[record['status']]
    if record['status'] not in ('accepted','result_available') and published:action='collect_result'
    if record['scene_version']!=manager.read()['scene_version'] or (record['status']!='accepted' and record['source_hash']!=baseline(manager.read())):action='prepare_new_task'
    result['recovery']={'next_action':action,'published_outputs':published}
    return result


def record_error(manager,task_id,error,*,expected_version):
    """Preserve a published error without treating bad input as executor absence."""
    validate_contract('visual_task_error',error)
    def mutate(m):
        record,_,_,_=read_task(manager,task_id,m,fresh=True)
        require(record['status'] in ('running','interrupted'),'No running attempt to fail')
        require((error['task_id'],error['operation'])==(task_id,record['operation']),'Error identity mismatch')
        path=(Path(record['request_path']).parent/f'error-attempt-{record["attempt"]}.json').as_posix();raw=encoded(error)
        record['files'][path]=hashlib.sha256(raw).hexdigest()
        record['status']='failed';record['selection']['input_error']=path
        record['events'].append({'status':'failed','reason':error['error_code']+': '+error['message']})
        return [(path,raw)]
    manager._visual_change('visual_task_error_collected',mutate,expected_version)
    return status(manager,task_id)


def compile_task(manager,m,task_id,plans):
    record,_,context,values=read_task(manager,task_id,m)
    require(record['result_path'] and record['execution_path'],'Direction needs an explicit execution interpretation')
    direction=strict_json(inside(manager.root,record['result_path']))
    execution=strict_json(inside(manager.root,record['execution_path']))
    scene=copy.deepcopy(context['scene_context'])
    require(scene['production']['geometry_hash']==document_hash(m['geometry_assets']) and
            scene['production']['blockout_hash']==document_hash(plans['blockout_plan']),'Measured geometry or blockout changed')
    docs=current_documents(manager,m);style,hashes=style_snapshot(manager,m)
    require(hashes==context['style_hashes'],'Visual direction style resources changed')
    require(scene['production']['scene_spec_hash']==document_hash(docs['scene_spec']),'Scene specification changed')
    scene['production'].update(style_assignment_id=docs['style_assignment']['document_id'],material_map_id=plans['semantic_material_map']['document_id'],
        look_revision=plans['lookdev_plan']['revision'],render_revision=plans['render_plan']['revision'])
    from runtime.render_direction_adapter import compile_visual_direction
    look,render=compile_visual_direction(direction,scene,style,execution,task_id)
    for kind,value in [('lookdev_plan',look),('render_plan',render)]:value['document_id']=plans[kind]['document_id']
    render['output']=copy.deepcopy(plans['render_plan']['output'])
    return {**copy.deepcopy(plans),'lookdev_plan':look,'render_plan':render}


def accept_direction(manager,m,task_id,plans,*,refinement=False):
    record,_,context,_=read_task(manager,task_id,m,fresh=True)
    require(record['status']=='result_available' and record['operation']==('refine_direction' if refinement else 'create_direction'),'No matching direction candidate')
    require(not m.get('render_direction'),'Legacy direction requires its existing compatibility path')
    if not refinement:
        require(not m.get('visual_direction') and m['state']=='geometry_approved','Initial visual direction already exists or geometry unapproved')
        require(document_hash(plans)==document_hash(context['plans']),'Prepared plan inputs changed')
    compiled=compile_task(manager,m,task_id,plans)
    record['status']='accepted';record['events'].append({'status':'accepted','reason':'Atomically accepted with executable plans.'})
    m['visual_direction']=task_id;m['visual_review_task']=None
    return compiled


def verify_plans(manager,m,plans):
    expected=m.get('visual_direction')
    if not expected:return
    require(not m.get('render_direction'),'Mixed visual protocols are unsupported')
    require(all(plans[k].get('visual_task')=={'task_id':expected} and not plans[k].get('render_direction') for k in ('lookdev_plan','render_plan')),'Visual plan task reference mismatch')
    compiled=compile_task(manager,m,expected,plans)
    require(all(compiled[k]==plans[k] for k in ('lookdev_plan','render_plan')),'Executable plan differs from its visual task')


def accept_review(manager,m,task_id,production_review):
    record,request,_,values=read_task(manager,task_id,m,fresh=True)
    require(record['status']=='result_available' and record['operation']=='review_render','No matching review candidate')
    require(m.get('visual_direction'),'No registered visual direction')
    current=m['visual_tasks'][m['visual_direction']]
    require(values['previous_render_direction']==strict_json(inside(manager.root,current['result_path'])),'Review uses stale direction')
    metadata=current_documents(manager,m,('render_metadata',))['render_metadata']
    image=(Path(record['request_path']).parent/request['inputs']['render_image']).as_posix()
    require(record['files'][image]==metadata['image']['sha256']==production_review['image_sha256'],'Review uses a different PNG')
    record['status']='accepted';record['events'].append({'status':'accepted','reason':'Accepted with current production diagnosis.'})
    m['visual_review_task']=task_id


def revise_task(manager,m,task_id,revision,plans):
    record,_,_,values=read_task(manager,task_id,m,fresh=True)
    require(record['operation']=='refine_direction' and record['status']=='result_available','No refinement candidate')
    old=values['previous_render_direction'];new=strict_json(inside(manager.root,record['result_path']))
    parent=m['visual_tasks'][m['visual_direction']]
    require(old==strict_json(inside(manager.root,parent['result_path'])),'Refinement parent is no longer current')
    review=m['visual_tasks'][m['visual_review_task']]
    require(values['previous_render_review']==strict_json(inside(manager.root,review['result_path'])),'Refinement review is no longer current')
    from runtime.render_director import changed_paths,get_path
    changes=changed_paths(old,new)-{'direction_id','revision','parent_direction_id','preserve','avoid'}
    actions={a['action']:a for a in revision['actions']}
    require(set(actions)<= {'camera_framing','lighting_direction','lighting_intensity','fog_amount'},'Unsupported visual task revision action')
    limits={'camera.azimuth_deg':('camera_framing',10),'camera.elevation_deg':('camera_framing',10),
        'camera.focal_length_mm':('camera_framing',10),'camera.subject_coverage':('camera_framing',.1),
        'lighting.key.azimuth_deg':('lighting_direction',10),'lighting.key.elevation_deg':('lighting_direction',10),
        'lighting.fill.ratio_to_key':('lighting_intensity',.2)}
    allowed=set();used=set()
    for path,(action,limit) in limits.items():
        if path not in changes:continue
        require(action in actions,'Direction change absent from production actions')
        limit*=.5 if actions[action]['amount']=='small' else 1
        require(0<abs(get_path(new,path)-get_path(old,path))<=limit+1e-9,'Direction change exceeds bounded revision')
        allowed.add(path);used.add(action)
    old_execution=strict_json(inside(manager.root,parent['execution_path']))
    new_execution=strict_json(inside(manager.root,record['execution_path']))
    require(old_execution['softness']==new_execution['softness'],'Softness changes are outside supported bounded actions')
    if 'atmosphere.fog' in changes or old_execution['fog_amount']!=new_execution['fog_amount']:
        require('fog_amount' in actions and 'atmosphere.fog' in changes,'Unreviewed fog execution change')
        options=['none','subtle','medium','dense'];delta=options.index(new_execution['fog_amount'])-options.index(old_execution['fog_amount'])
        sign=1 if actions['fog_amount']['direction']=='increase' else -1
        require(0<delta*sign<= (1 if actions['fog_amount']['amount']=='small' else 2),'Fog change exceeds reviewed bounded action')
        allowed.add('atmosphere.fog');used.add('fog_amount')
    require(changes==allowed and bool(changes) and set(actions)==used,'Unreviewed or unsupported visual changes')
    return accept_direction(manager,m,task_id,plans,refinement=True)


def formal_task_files(manager,m):
    """Explicitly anchored accepted tasks only; pending outputs never enter delivery."""
    paths=set()
    for identity,record in m.get('visual_tasks',{}).items():
        if record['status']=='accepted':
            read_task(manager,identity,m)
            paths.update(record['files'])
    return [inside(manager.root,p) for p in sorted(paths)]


def interrupt(manager,task_id,reason,*,expected_version):
    require(isinstance(reason,str) and bool(reason.strip()),'Interruption needs a concrete reason')
    def mutate(m):
        record,_,_,_=read_task(manager,task_id,m)
        require(record['status']=='running','Only a running task can be interrupted')
        record['status']='interrupted';record['events'].append({'status':'interrupted','reason':reason})
    manager._visual_change('visual_task_interrupted',mutate,expected_version)
    return status(manager,task_id)


def main():
    try:
        request=json.load(sys.stdin);validate_contract('visual_task_command',request)
        command=request['command']
        if command=='capabilities':result={'operations':list(OPERATIONS),'execution':'agent_required'}
        else:
            from runtime.manifest_manager import ManifestManager
            m=ManifestManager(request['project']);version=request.get('expected_version')
            if command=='prepare':result=prepare(m,request['spec'],expected_version=version)
            elif command=='start':result=start(m,request['task_id'],expected_version=version)
            elif command=='submit':result=submit(m,request['task_id'],request['decision'],execution=request.get('execution'),expected_version=version)
            elif command=='interrupt':result=interrupt(m,request['task_id'],request.get('reason',''),expected_version=version)
            elif command=='collect':
                from runtime.visual_task_adapter import collect
                result=collect(m,request['task_id'],execution=request.get('execution'),expected_version=version)
            else:result=status(m,request['task_id'])
        validate_contract('visual_task_result',result);print(json.dumps(result,ensure_ascii=False,allow_nan=False));return 0
    except (WorkflowError,ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps({'schema_version':'1.0','task_id':'unknown','operation':'unknown','error_code':'INVALID_TASK',
                          'message':str(exc),'invalid_inputs':[]},ensure_ascii=False),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
