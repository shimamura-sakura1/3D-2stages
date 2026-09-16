"""Geometry-only routing after library search; material fit is resolved separately."""
from importlib.resources import files
from runtime.io import load_data
from runtime.asset_router import AssetRouter
from runtime.errors import BoundaryError
from runtime.validators import validate_contract

class GeometryRouter:
    def __init__(self):
        self.policy=load_data(files('policies').joinpath('geometry_routing_v02.yaml'))
    def choose(self,request,report):
        task=request['task'];validate_contract('asset_task',task)
        if not report.complete or not set(task['search']['preferred_providers']).issubset(report.providers):
            raise BoundaryError('Library search incomplete; geometry routing cannot proceed')
        preferred=request['preferred_route'];primitive=request['primitive']
        if preferred not in ('auto','A','B','C','D'):raise BoundaryError('Unknown geometry route')
        if primitive is not None and primitive not in self.policy['procedural_priority']:raise BoundaryError('Unknown procedural primitive')
        if primitive is not None and preferred in ('auto','D'):return 'D',None
        if preferred=='D':raise BoundaryError('Route D requires a supported primitive')
        candidates=[c for c in report.candidates if c['geometry_usable'] and c['format'] in self.policy['supported_formats'] and c['scores']['geometry_quality']>=self.policy['geometry_min'] and c['scores']['semantic_fit']>=self.policy['semantic_min'] and AssetRouter().legal(c,modification=True)]
        candidates.sort(key=lambda c:(-c['scores']['semantic_fit'],-c['scores']['geometry_quality'],c['candidate_id']))
        if preferred in ('auto','A','B') and candidates:
            route='B' if preferred=='B' or request['modification'] is not None else 'A'
            if route=='A' and not task['routing']['allow_route_a']:raise BoundaryError('Route A prohibited')
            if route=='B' and not task['routing']['allow_route_b']:raise BoundaryError('Route B prohibited')
            if route=='B' and request['modification'] is None:raise BoundaryError('Route B requires an explicit modification')
            return route,candidates[0]
        if preferred in ('auto','C') and task['hy3d']['enabled'] and task['routing']['allow_route_c']:return 'C',None
        raise BoundaryError('No permitted geometry route')
