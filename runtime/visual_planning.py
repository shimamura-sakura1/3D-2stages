"""Validate agent-authored direction; artistic interpretation stays in the Router."""
from runtime.validators import validate_contract
from runtime.visual_contracts import require, unique, document_hash
from runtime.reference_manager import check_reference
from runtime.style_registry import StyleRegistry
from runtime.io import inside, load_data

STAGE0_KINDS=('visual_brief','reference_board','scene_spec','style_assignment')

def validate_plan(root, manifest, documents):
    require(set(documents)==set(STAGE0_KINDS),'Stage 0 requires exactly four documents')
    for kind,doc in documents.items():
        validate_contract(kind,doc)
        require((doc['project_id'],doc['scene_version'])==(manifest['project_id'],manifest['scene_version']),'Stage 0 project/scene identity mismatch')
    unique(documents.values(),'document_id','document identity')
    refs=unique(documents['reference_board']['references'],'reference_id','reference')
    for ref in refs.values():check_reference(root,ref)
    assignment=documents['style_assignment'];unique(assignment['references'],'reference_id','assigned reference')
    for item in assignment['references']:
        require(item['reference_id'] in refs,'Unknown style reference')
        require(set(item['roles']).issubset(refs[item['reference_id']]['roles']),'Style reference role exceeds declared roles')
    style=StyleRegistry().load(assignment['style_profile'],version=assignment['profile_version'],project_root=root)
    require(assignment['profile_version']==style['version'],'Style version does not match executable profile')
    for key in ('lighting','atmosphere','camera','color'):
        require(assignment[key+'_profile']==style[key]['profile'],'Unknown '+key+' profile')
    scene=documents['scene_spec'];objects=unique(scene['objects'],'object_id','scene object')
    if 'signature' in style:
        require(set(style['signature']['dimensions']['depth']['required_layers']).issubset(scene['composition']['depth_layers']),'Scene depth layers do not satisfy style signature')
    require(scene['composition']['focal_subject'] in objects,'Unknown focal subject')
    for obj in objects.values():
        require(obj['depth_layer'] in scene['composition']['depth_layers'],'Undeclared depth layer')
        for relation in obj['relationships']:
            require(relation['object_id'] in objects and relation['object_id']!=obj['object_id'],'Unknown or self relationship')
    return documents

def current_documents(manager, manifest, kinds=STAGE0_KINDS):
    docs={}
    for kind in kinds:
        records=[r for r in manifest['artifacts'].get(kind,[]) if r['scene_version']==manifest['scene_version']]
        require(bool(records),'Missing current '+kind)
        record=max(records,key=lambda r:r['revision']);doc=load_data(inside(manager.root,record['path']))
        require(document_hash(doc)==record['sha256'],'Artifact hash mismatch: '+kind)
        require(doc['document_id']==record['document_id'] and doc['revision']==record['revision'],'Artifact identity mismatch')
        docs[kind]=doc
    return docs
