"""Run every accepted visual critic assertion with the portable time budget."""

from tests import test_v02_critic as historical


globals().update({name: case for name, case in vars(historical).items()
                  if name.startswith('test_') and callable(case)})
