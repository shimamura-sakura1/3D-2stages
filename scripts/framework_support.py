"""Maintenance-only framework discovery; excluded from consumer distributions."""
import os
from pathlib import Path
from runtime.errors import BoundaryError


def find_framework(root, explicit=None, *, environ=None):
    env = os.environ if environ is None else environ
    value = explicit if explicit is not None else env.get('CONTRACT_GOVERN_HOME') or Path(root).resolve().parent / 'contract-govern-skil'
    path = Path(value).expanduser().resolve()
    if not (path/'skillctl/__main__.py').is_file() or not (path/'spec/SPEC.md').is_file():
        raise BoundaryError('Framework not found; set CONTRACT_GOVERN_HOME or --framework to the designated checkout')
    return path
