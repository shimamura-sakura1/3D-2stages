from importlib.resources import files

from runtime.errors import BoundaryError
from runtime.io import load_data


TRANSITIONS = load_data(files("policies").joinpath("stage_transitions.yaml"))


def check_transition(current, target):
    if target not in TRANSITIONS.get(current, []):
        raise BoundaryError(f"Illegal asset transition: {current} -> {target}")


SCENE_TRANSITIONS = load_data(files("policies").joinpath("scene_transitions_v02.yaml"))


def check_scene_transition(current, target):
    """Check a declared edge only. This neither writes state nor grants approval."""
    if target not in SCENE_TRANSITIONS.get(current, []):
        raise BoundaryError(f"Illegal scene transition: {current} -> {target}")
