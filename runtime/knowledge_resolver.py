"""Read only explicitly selected canonical items; no semantic search or writes."""
import json
from pathlib import Path
import yaml
from runtime.io import inside,sha256
from runtime.validators import validate_contract
from runtime.visual_contracts import require


def resolve_knowledge(home,item_ids,operation,renderer,scene_type):
    if not home or not item_ids:return None,[]
    root=Path(home).expanduser().resolve()
    require(root.is_dir(),'Configured knowledge directory is missing')
    require(len(item_ids)==len(set(item_ids)) and len(item_ids)<=24,'Select a bounded unique knowledge item set')
    wanted=set(item_ids);candidates={}
    for pack_path in sorted((root/'packs').glob('*/pack.yaml')):
        pack_path=inside(root,pack_path.relative_to(root).as_posix())
        pack=yaml.safe_load(pack_path.read_text(encoding='utf-8'))
        validate_contract('visual_knowledge_pack',pack)
        require(pack['id']==pack_path.parent.name,'Knowledge pack identity mismatch')
        for identity in wanted.intersection(pack['item_ids']):
            require(identity not in candidates,'Ambiguous canonical knowledge identity')
            candidates[identity]=(pack_path,pack)
    require(wanted<=set(candidates),'Selected canonical knowledge item missing')
    context={'schema_version':'1.0','domain':[],'scene_type':[]};evidence=[]
    for identity in item_ids:
        pack_path,pack=candidates[identity]
        path=inside(root,(pack_path.parent/'items'/f'{identity}.yaml').relative_to(root).as_posix())
        item=yaml.safe_load(path.read_text(encoding='utf-8'));validate_contract('visual_knowledge_item',item)
        require(item['id']==identity,'Knowledge item identity mismatch')
        a=item['applicability']
        if pack['status']!='canonical' or item['status']!='canonical':continue
        if not all(value in options or '*' in options for value,options in [(operation,a['tasks']),(renderer,a['renderers']),(scene_type,a['scene_types'])]):continue
        bucket='scene_type' if 'scene_type' in item['domain'] else 'domain'
        context[bucket].append({'id':identity,'content':json.dumps(item,ensure_ascii=False,sort_keys=True)})
        evidence.append({'id':identity,'version':item['version'],'pack_id':pack['id'],'pack_version':pack['version'],
            'path':path.relative_to(root).as_posix(),'sha256':sha256(path),'pack_sha256':sha256(pack_path)})
    validate_contract('visual_task_knowledge',context)
    return (context if evidence else None),evidence
