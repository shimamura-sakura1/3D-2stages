"""Content-addressed reference import; roles are supplied by the agent/user."""
import hashlib
from pathlib import Path
from runtime.io import inside
from runtime.errors import BoundaryError
from runtime.validators import validate_contract


def check_reference(root, reference):
    path=inside(root,reference['path'])
    if not path.is_file():raise BoundaryError('Missing reference file')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if path.stem != reference['reference_id']+'-'+digest:
        raise BoundaryError('Reference hash mismatch; import a new reference revision')
    return path


def import_reference(manager, source, reference_id, roles, metadata):
    source=Path(source)
    if source.suffix.lower() not in {'.png','.jpg','.jpeg','.webp','.svg'}:
        raise BoundaryError('Unsupported reference image format')
    raw=source.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    # Schema validation precedes using kind or ID as a filesystem component.
    reference={'reference_id':reference_id,'path':'references/selected/pending.png','roles':roles,'weight':1.0,'source':metadata}
    envelope={'schema_version':'0.2','project_id':'reference_import','scene_version':1,'document_id':'reference_import','revision':0,'references':[reference]}
    validate_contract('reference_board',envelope)
    folder='user' if metadata['kind']=='user' else 'generated' if metadata['kind']=='generated' else 'selected'
    reference['path']=f'references/{folder}/{reference_id}-{digest}{source.suffix.lower()}'
    with manager._lock():
        if manager.read()['schema_version']!='0.2':raise BoundaryError('Reference import requires schema 0.2')
        target=inside(manager.root,reference['path'])
        for name in ('user','generated','selected'):inside(manager.root,'references/'+name).mkdir(parents=True,exist_ok=True)
        if target.exists():
            if target.read_bytes()!=raw:raise BoundaryError('Reference path already contains different bytes')
        else:
            with target.open('xb') as f:f.write(raw)
    return reference
