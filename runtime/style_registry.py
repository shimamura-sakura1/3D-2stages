"""Load a bounded executable style; no semantic inference or fallback."""
from pathlib import Path
import hashlib
import json
import math
import re
import copy
import yaml
from runtime.io import inside
from runtime.errors import BoundaryError

CLASSES = {'painted_metal','bare_metal','concrete','rubber','glass','emissive'}
CONDITIONS = {'clean','lightly_weathered','weathered'}
RUBRIC_CATEGORIES = {'plasticity', 'material_separation', 'surface_uniformity', 'composition',
                    'depth_separation', 'lighting_flatness', 'contact_shadow',
                    'atmospheric_depth', 'style_compatibility'}


class UniqueKeyLoader(yaml.SafeLoader):
    """Style data never expands environment variables or executes supplied code."""
    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        if len(keys) != len(set(keys)):
            raise ValueError('duplicate style field')
        return super().construct_mapping(node, deep=deep)


def style_path(root, relative):
    target = inside(root, relative)
    cursor = Path(root)
    for part in Path(str(relative).replace('\\', '/')).parts:
        cursor = cursor / part
        if cursor.is_symlink() or getattr(cursor, 'is_junction', lambda: False)():
            raise BoundaryError('Linked style paths are unsupported')
    return target


def style_files(style):
    paths = ['profile.yaml', *style['components'].values(), *style['resources'].values()]
    if 'provenance' in style:
        paths.append(style['provenance'])
    else:
        # Legacy rubric location remains part of scene and delivery guards.
        paths.append('critic/rubric.yaml')
    if style.get('project_import'):
        paths.append('package-lock.json')
    return list(dict.fromkeys(paths))


def design_reviewed(style):
    signature = style.get('signature', {})
    reviewer = signature.get('reviewed_by')
    reviewer_valid = (isinstance(reviewer, str) and bool(reviewer.strip()) and reviewer != 'unreviewed')
    if 'format_version' not in style:
        reviewer_valid = reviewer == 'Codex'
    return reviewer_valid and signature.get('review_status') == 'design_reviewed'

def number(value, low, high):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError('finite bounded numeric value')

def vector(value, low, high):
    if not isinstance(value,list) or len(value)!=3:raise ValueError('three numeric components')
    for x in value:number(x,low,high)

def apply_signature(style, *, require_review=True):
    """Validate and consume an author-reviewed signature, without touching geometry."""
    signature=style['signature']
    if set(signature)!={'id','version','reviewed_by','review_status','evidence_scope','dimensions'}:
        raise ValueError('signature fields')
    if signature['id']!=style['id'] or signature['version']!=style['version']:
        raise ValueError('signature identity')
    if (not isinstance(signature['reviewed_by'], str) or not signature['reviewed_by'].strip()
            or signature['review_status'] not in ('unreviewed', 'design_reviewed')):
        raise ValueError('signature review fields')
    if require_review and not design_reviewed(style):
        raise ValueError('signature design review is not artistic approval')
    evidence=signature['evidence_scope']
    if (not isinstance(evidence,dict) or not evidence
            or ('format_version' not in style and set(evidence)!={'original_calibration','original_pump','user_station'})
            or any(not isinstance(k,str) or not k.strip() or not isinstance(v,str) or not v.strip() for k,v in evidence.items())):
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

def visual_priors(style):
    """Read authored visual priors; shader defaults are not aesthetic mandates."""
    result={key:copy.deepcopy(style.get('direction_prior',{}).get(key,{}))
            for key in ('camera','composition','lighting','atmosphere','material_readability')}
    root=Path(style['root'])
    for path in sorted((root/'semantic').glob('*.yaml')):
        data=yaml.safe_load(inside(root,path.relative_to(root).as_posix()).read_text(encoding='utf-8'))
        key='material_readability' if path.stem in ('materials','material') else path.stem
        if key in result and isinstance(data,dict):result[key]['authored_semantics']=data
    return result


class StyleRegistry:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else Path(__file__).resolve().parents[1]/'styles'

    def load(self, name, *, version=None, require_resources=True, project_root=None):
        version='1.0.0' if version is None else version
        if not isinstance(version,str) or len(version)>32 or re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version) is None:
            raise BoundaryError(f'Unknown style version: {version}')
        if not isinstance(name,str) or re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}',name) is None:
            raise BoundaryError('Unknown style identifier')
        if project_root is not None:
            local = style_path(project_root, f'styles/{name}/versions/{version}')
            if local.exists():
                result = self.load_package(local, require_resources=require_resources)
                lock_path = style_path(local, 'package-lock.json')
                lock = json.loads(lock_path.read_text(encoding='utf-8')) if lock_path.is_file() else None
                if (not isinstance(lock,dict) or lock.get('style_id')!=name or lock.get('version')!=version
                        or lock.get('files')!=result['source_hashes']):
                    raise BoundaryError('Imported style hash inventory missing or changed; use style-import')
                result['project_import'] = True
                return result
        folder=inside(self.root,name)
        if version!='1.0.0' or not (folder/'profile.yaml').is_file():folder=inside(folder,'versions/'+version)
        if not (folder/'profile.yaml').is_file():
            raise BoundaryError(f'Unknown style or version: {name}@{version}')
        result = self._load_folder(folder, require_resources=require_resources)
        if result['id']!=name or result['version']!=version:
            raise BoundaryError('Invalid style definition: profile identity/version')
        return result

    def load_package(self, folder, *, require_resources=True, require_review=True):
        result = self._load_folder(folder, require_resources=require_resources, require_review=require_review)
        if 'format_version' not in result:
            raise BoundaryError('User style package requires explicit format_version; see docs/v02/user-styles.md')
        return result

    def _load_folder(self, folder, *, require_resources=True, require_review=True):
        folder = Path(folder).absolute()
        if folder.is_symlink() or getattr(folder, 'is_junction', lambda: False)():
            raise BoundaryError('Linked style directory is unsupported')
        folder = folder.resolve()
        raw_files = {}
        def read(relative):
            raw = style_path(folder, relative).read_bytes()
            raw_files[relative] = raw
            value = yaml.load(raw.decode('utf-8'), Loader=UniqueKeyLoader)
            json.dumps(value, allow_nan=False)
            return value
        try:
            p=read('profile.yaml')
            if not isinstance(p,dict):raise ValueError('profile must be an object')
            custom = 'format_version' in p
            if custom:
                from runtime.validators import validate_contract
                validate_contract('style_package',p)
                if tuple(p['blender_minimum']) < (4,2,0):raise ValueError('Blender minimum must be at least 4.2')
            elif p['version'] not in ('1.0.0','1.1.0'):
                raise ValueError('Unknown legacy style version; declare a user package format_version')
            refined = custom or p['version']=='1.1.0'
            expected_components={'materials','lighting','atmosphere','camera','color','render'}
            if refined:expected_components.add('signature')
            if custom:expected_components.add('critic')
            if set(p['components'])!=expected_components or set(p['resources'])!={'library','calibration'}:
                raise ValueError('profile components/resources')
            declared = ['profile.yaml', *p['components'].values(), *p['resources'].values()]
            if custom:declared.append(p['provenance'])
            resolved = [style_path(folder,path) for path in declared]
            if len(set(resolved))!=len(resolved):raise ValueError('style file paths must be distinct')
            if any(path.name in ('package-lock.json','calibration-request.json','calibration-result.json','preview.png') for path in resolved):
                raise ValueError('reserved style output path')
            result={**p,'root':str(folder)}
            priors = copy.deepcopy(p.get('direction_prior', {}))
            for key,path in p['components'].items():
                result[key]=read(path)
                if not isinstance(result[key],dict):raise ValueError('component must be an object: '+key)
                component=result[key]
                if 'execution_default' in component:
                    if not isinstance(component['execution_default'],dict):raise ValueError('execution_default must be an object')
                    result[key]={**{k:v for k,v in component.items() if k not in ('execution_default','direction_prior')},
                                 **component['execution_default']}
                if 'direction_prior' in component:
                    if not isinstance(component['direction_prior'],dict):raise ValueError('direction_prior must be an object')
                    priors[key]=copy.deepcopy(component['direction_prior'])
                    result[key].pop('direction_prior',None)
            if custom:
                for key in ('lighting','atmosphere','camera','color'):
                    profile_name = result[key].get('profile')
                    if not isinstance(profile_name,str) or re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}',profile_name) is None:
                        raise ValueError('component profile: '+key)
                rubric=result['critic']
                if (rubric.get('profile_version')!=p['version'] or not isinstance(rubric.get('categories'),dict)
                        or set(rubric['categories'])!=RUBRIC_CATEGORIES
                        or any(not isinstance(v,str) or not v.strip() for v in rubric['categories'].values())
                        or not isinstance(rubric.get('score_semantics'),str) or not rubric['score_semantics'].strip()):
                    raise ValueError('style critic rubric')
                provenance=read(p['provenance'])
                if (not isinstance(provenance,dict) or provenance.get('style_id')!=p['id'] or provenance.get('version')!=p['version']
                        or not isinstance(provenance.get('evidence_limits'),list) or not provenance['evidence_limits']
                        or any(not isinstance(v,str) or not v.strip() for v in provenance['evidence_limits'])):
                    raise ValueError('style provenance identity/evidence_limits')
            definitions=result['materials']
            if not isinstance(definitions.get('materials'),dict) or not isinstance(definitions.get('conditions'),dict):
                raise ValueError('materials and conditions must be objects')
            classes=CLASSES|({'vegetation'} if refined else set())
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
            if not custom and result['lighting']['profile']!='overcast': raise ValueError('lighting profile')
            if refined:
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
                apply_signature(result, require_review=require_review)
            for key,path in p['resources'].items():
                resource=style_path(folder,path)
                if resource.is_file():raw_files[path]=resource.read_bytes()
                if (require_resources or resource.exists()) and (path not in raw_files or raw_files[path][:7]!=b'BLENDER'):
                    raise BoundaryError(f'Missing Blender resource: {path}')
                result[key]=str(resource)
            if custom:
                result['source_hashes']={path:hashlib.sha256(raw).hexdigest() for path,raw in sorted(raw_files.items())}
            result['direction_prior']=priors
            result['execution_default']={key:copy.deepcopy(result[key]) for key in
                                          ('lighting','atmosphere','camera','color','render')}
            return result
        except (KeyError,TypeError,ValueError,OverflowError,OSError,yaml.YAMLError) as exc:
            raise BoundaryError(f'Invalid style definition: {exc}') from exc
