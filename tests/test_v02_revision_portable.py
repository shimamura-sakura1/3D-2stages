"""Run every accepted visual revision assertion with the portable time budget."""

from tests import test_v02_revision as historical


globals().update({name: case for name, case in vars(historical).items()
                  if name.startswith('test_') and callable(case)})
