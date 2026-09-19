"""Export a complete consumer Skill using an explicit runtime/resource allowlist."""
import argparse
import copy
import json
import re
import shutil
from pathlib import Path


ROOT_FILES={'SKILL.md','README.md','pyproject.toml','.env.example'}
RUNTIME_DIRS={'runtime','providers','contracts','policies','templates','prompts','configs','examples'}
SCRIPTS={'python-env.ps1','two-stage-3d.ps1','check_contracts.py','check_visual_contracts.py'}


def selected_files(root):
    selected=set(ROOT_FILES)
    for directory in RUNTIME_DIRS:
        for path in (root/directory).rglob('*'):
            if path.is_symlink():raise ValueError('Linked consumer resources are unsupported')
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.blend1'):
                selected.add(path.relative_to(root).as_posix())
    for name in SCRIPTS:selected.add('scripts/'+name)
    for path in (root/'docs').rglob('*.md'):
        relative=path.relative_to(root).as_posix()
        if any(part in ('governance','superpowers') for part in path.parts):continue
        if path.name.startswith('phase-') or path.name in ('baseline.md','development.md'):continue
        selected.add(relative)
    # Style resources are declared by their profile, never an arbitrary recursive
    # copy of analysis inputs, user conversations, screenshots or local reviews.
    import yaml
    selected.add('styles/__init__.py')
    for profile in (root/'styles').rglob('profile.yaml'):
        data=yaml.safe_load(profile.read_text(encoding='utf-8'));base=profile.parent
        paths=['profile.yaml',*data['components'].values(),*data['resources'].values()]
        paths.extend([data['provenance']] if 'provenance' in data else ['critic/rubric.yaml'])
        if (base/'README.md').is_file():paths.append('README.md')
        # Legacy semantic data is consumed by authoring agents.
        if (base/'semantic').exists():paths.extend(p.relative_to(base).as_posix() for p in (base/'semantic').glob('*.yaml'))
        for name in paths:
            path=(base/name).resolve()
            if not path.is_relative_to(base.resolve()):raise ValueError('Style resource escaped its package')
            if path.is_file():selected.add(path.relative_to(root).as_posix())
    return sorted(selected)


def export_production(root,destination):
    root=Path(root).resolve();destination=Path(destination).resolve()
    if destination==root or destination.exists():raise ValueError('Consumer output must be a new directory')
    paths=selected_files(root)
    destination.mkdir(parents=True)
    for relative in paths:
        source=root/relative
        if source.is_symlink() or not source.is_file():raise ValueError('Missing or linked consumer resource: '+relative)
        target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    interface=json.loads((root/'interface.json').read_text(encoding='utf-8'))
    artifacts=[copy.deepcopy(a) for a in interface['artifacts'] if a['path'] in paths]
    ids={a['id'] for a in artifacts}
    # Runtime interface inventory has no claims, tests, or maintenance enforcement.
    for artifact in artifacts:artifact.pop('enforcement',None)
    public={'spec_version':interface['spec_version'],'skill':interface['skill'],'artifacts':artifacts,
            'relations':[r for r in interface.get('relations',[]) if r['from']['artifact'] in ids and r['to']['artifact'] in ids],
            'external_dependencies':[{'id':'render-director','entries':['analyze','review','refine'],
                'input':'contracts/render_context.schema.json',
                'outputs':['contracts/render_direction.schema.json','contracts/render_review.schema.json']}]}
    (destination/'interface.json').write_text(json.dumps(public,indent=2)+'\n',encoding='utf-8')
    package=destination/'pyproject.toml';text=package.read_text(encoding='utf-8')
    text=re.sub(r'(?ms)^\[project.optional-dependencies\].*?(?=^\[|\Z)','',text)
    text=re.sub(r'(?ms)^\[tool.pytest.ini_options\].*?(?=^\[|\Z)','',text)
    package.write_text(text.rstrip()+'\n',encoding='utf-8')
    (destination/'.gitattributes').write_text('examples/v02/reference.svg text eol=lf\n',encoding='utf-8')
    (destination/'.gitignore').write_text('.env\nprojects/\n.deps/\n__pycache__/\n*.egg-info/\n*.blend1\n',encoding='utf-8')
    return destination


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output');parser.add_argument('--source',default=Path(__file__).resolve().parents[1])
    args=parser.parse_args();print(export_production(args.source,args.output))
