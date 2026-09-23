import json
import yaml

def make_kb(tmp_path):
    root=tmp_path/'kb';folder=root/'packs/camera-core';(folder/'items').mkdir(parents=True)
    item={'schema_version':'1.0','id':'camera.test','version':'1.0.0','kind':'principle','domain':['camera'],'topics':['framing'],
        'applicability':{'tasks':['create_direction','review_render'],'scene_types':['*'],'renderers':['*']},
        'statement':'Perspective depends on position.','mechanism':'Relative distances change.','signals':{'positive':['readable'],'negative':['flat']},
        'diagnosis':{'inspect':['position']},'interventions':{'consider':['move camera']},'tradeoffs':['framing changes'],
        'non_applicability':['orthographic camera'],'evidence':{'confidence':'high','basis':['domain_knowledge'],'sources':[]},'status':'canonical'}
    (folder/'items/camera.test.yaml').write_text(yaml.safe_dump(item),encoding='utf-8')
    (folder/'pack.yaml').write_text(yaml.safe_dump({'schema_version':'1.0','id':'camera-core','version':'1.0.0','title':'Camera','description':'Camera knowledge','domains':['camera'],'item_ids':['camera.test'],'status':'canonical'}),encoding='utf-8')
    return root

def test_optional_knowledge_and_operation_filter(tmp_path):
    from runtime.knowledge_resolver import resolve_knowledge
    root=make_kb(tmp_path)
    knowledge,evidence=resolve_knowledge(root,['camera.test'],'create_direction','cycles','forest')
    assert json.loads(knowledge['domain'][0]['content'])['non_applicability']==['orthographic camera']
    assert evidence[0]['sha256'] and knowledge['scene_type']==[]
    assert resolve_knowledge(root,['camera.test'],'refine_direction','cycles','forest')[0] is None
    assert resolve_knowledge(None,[],'create_direction','cycles','forest')==(None,[])
