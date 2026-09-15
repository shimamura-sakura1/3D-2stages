"""Load a bounded executable style; no semantic inference or fallback."""
from pathlib import Path
import math
from runtime.io import load_data, inside
from runtime.errors import BoundaryError

CLASSES = {'painted_metal','bare_metal','concrete','rubber','glass','emissive'}
CONDITIONS = {'clean','lightly_weathered','weathered'}

def number(value, low, high):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError('finite bounded numeric value')

def vector(value, low, high):
    if not isinstance(value,list) or len(value)!=3:raise ValueError('three numeric components')
    for x in value:number(x,low,high)

def apply_signature(style):
    """Validate and consume an author-reviewed signature, without touching geometry."""
    signature=style['signature']
    if set(signature)!={'id','version','reviewed_by','review_status','evidence_scope','dimensions'}:
        raise ValueError('signature fields')
    if signature['id']!=style['id'] or signature['version']!=style['version']:
        raise ValueError('signature identity')
    if signature['reviewed_by']!='Codex' or signature['review_status']!='design_reviewed':
        raise ValueError('signature design review is not artistic approval')
    evidence=signature['evidence_scope']
    if not isinstance(evidence,dict) or set(evidence)!={'original_calibration','original_pump','user_station'} or any(not isinstance(v,str) or not v.strip() for v in evidence.values()):
        raise ValueError('signature evidence scope')
    d=signature['dimensions']
    fields={'geometry':{'preserve_approved'},'surface':{'bump_scale'},'palette':CLASSES|{'vegetation'},'roughness':{'offset'},'weathering':{'variation_scale'},'lighting':{'key_scale','fill_scale'},'fog':{'density_scale'},'depth':{'required_layers'},'composition':{'focal_length_mm_range'},'emissive':{'strength_scale'},'detail_density':{'noise_scale'}}
    if not isinstance(d,dict) or set(d)!=set(fields):raise ValueError('signature dimensions')
    for key,expected in fields.items():
        if not isinstance(d[key],dict) or set(d[key])!=expected:raise ValueError('signature '+key)
    if d['geometry']['preserve_approved'] is not True:raise ValueError('signature must preserve approved geometry')
    for section,key,lo,hi in [('surface','bump_scale',0,2),('roughness','offset',-.1,.1),('weathering','variation_scale',0,2),('lighting','key_scale',.25,2),('lighting','fill_scale',.1,2),('fog','density_scale',0,2),('emissive','strength_scale',0,2),('detail_density','noise_scale',.25,2)]:
        number(d[section][key],lo,hi)
    if d['depth']['required_layers']!=['foreground','midground','background']:raise ValueError('signature depth layers')
    focal=d['composition']['focal_length_mm_range']
    if not isinstance(focal,list) or len(focal)!=2:raise ValueError('signature focal range')
    for x in focal:number(x,20,100)
    if focal[0]>=focal[1]:raise ValueError('signature focal range order')
    for color in d['palette'].values():vector(color,0,1)
    for kind,p in style['materials']['materials'].items():
        p['base_color']=list(d['palette'][kind])
        p['bump_distance']*=d['surface']['bump_scale']
        p['roughness']=max(0,min(.98,p['roughness']+d['roughness']['offset']))
        p['roughness_variation']=min(1,p['roughness_variation']*d['weathering']['variation_scale'])
        p['emission_strength']*=d['emissive']['strength_scale']
        p['noise_scale']*=d['detail_density']['noise_scale']
    for role in ('key','fill'):style['lighting'][role+'_energy']*=d['lighting'][role+'_scale']
    style['atmosphere']['density']*=d['fog']['density_scale']

class StyleRegistry:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else Path(__file__).resolve().parents[1]/'styles'

    def load(self, name, *, version=None, require_resources=True):
        version='1.0.0' if version is None else version
        if not isinstance(version,str) or version not in ('1.0.0','1.1.0'):
            raise BoundaryError(f'Unknown style version: {version}')
        folder=inside(self.root,name)
        if version!='1.0.0':folder=inside(folder,'versions/'+version)
        if not (folder/'profile.yaml').is_file():
            raise BoundaryError(f'Unknown style: {name}')
        try:
            p=load_data(folder/'profile.yaml')
            if p['id']!=name or p['version']!=version:
                raise ValueError('profile identity/version')
            expected_components={'materials','lighting','atmosphere','camera','color','render'}
            if version=='1.1.0':expected_components.add('signature')
            if set(p['components'])!=expected_components or set(p['resources'])!={'library','calibration'}:
                raise ValueError('profile components/resources')
            result={**p,'root':str(folder)}
            for key,path in p['components'].items():
                result[key]=load_data(inside(folder,path))
            definitions=result['materials']
            classes=CLASSES|({'vegetation'} if version=='1.1.0' else set())
            if set(definitions['materials'])!=classes or set(definitions['conditions'])!=CONDITIONS:
                raise ValueError('material/condition set')
            expected={'base_color','roughness','metallic','transmission','emission_strength','bump_distance','noise_scale','roughness_variation','ior'}
            for value in definitions['materials'].values():
                if set(value)!=expected or len(value['base_color'])!=3:
                    raise ValueError('shader fields')
                for key in ('roughness','metallic','transmission','roughness_variation'):
                    number(value[key],0,1)
                for x in [*value['base_color'],value['emission_strength'],value['bump_distance'],value['noise_scale'],value['ior']]:
                    if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<0: raise ValueError('finite nonnegative shader values')
            for value in definitions['conditions'].values():
                if set(value)!={'roughness_add','variation_scale'} or not 0<=value['roughness_add']<=.2 or not 0<=value['variation_scale']<=2:
                    raise ValueError('condition values')
            if result['lighting']['profile']!='overcast': raise ValueError('lighting profile')
            if version=='1.1.0':
                for condition in definitions['conditions'].values():
                    number(condition['roughness_add'],0,.2);number(condition['variation_scale'],0,2)
                for params in definitions['materials'].values():
                    vector(params['base_color'],0,1)
                    number(params['emission_strength'],0,20);number(params['bump_distance'],0,.1)
                    number(params['noise_scale'],.1,200);number(params['ior'],1,3)
                light=result['lighting']
                for key in ('key_energy','fill_energy'):number(light[key],0,10000)
                for key in ('key_size','fill_size'):number(light[key],.1,30)
                for key in ('key_location','fill_location'):vector(light[key],-100,100)
                vector(light['world_color'],0,1);number(light['world_strength'],0,2)
                vector(result['atmosphere']['color'],0,1);number(result['atmosphere']['density'],0,.1)
                number(result['camera']['clip_start'],.001,10);number(result['camera']['clip_end'],10,5000)
                number(result['camera']['focal_length_mm'],20,100)
                number(result['color']['exposure'],-5,5);number(result['color']['gamma'],.1,3)
                if result['color']['view_transform']!='AgX':raise ValueError('refined color transform')
                render=result['render']
                for key,low,high in [('width',16,8192),('height',16,8192),('samples',1,4096),('seed',0,2147483647)]:
                    if type(render[key]) is not int:raise ValueError('integer render setting')
                    number(render[key],low,high)
                if render['renderer']!='cycles' or type(render['denoise']) is not bool:raise ValueError('refined render settings')
                apply_signature(result)
            for key,path in p['resources'].items():
                resource=inside(folder,path)
                if require_resources and (not resource.is_file() or resource.read_bytes()[:7]!=b'BLENDER'):
                    raise BoundaryError(f'Missing Blender resource: {path}')
                result[key]=str(resource)
            return result
        except (KeyError,TypeError,ValueError,OSError) as exc:
            raise BoundaryError(f'Invalid style definition: {exc}') from exc
