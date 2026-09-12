from importlib.resources import files

from runtime.errors import BoundaryError
from runtime.io import load_data


TRANSITIONS = load_data(files("policies").joinpath("stage_transitions.yaml"))


def check_transition(current, target):
    if target not in TRANSITIONS.get(current, []):
        raise BoundaryError(f"Illegal asset transition: {current} -> {target}")
