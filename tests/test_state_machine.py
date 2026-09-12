import pytest

from runtime.errors import BoundaryError
from runtime.state_machine import check_transition


@pytest.mark.parametrize("current,target", [("planned", "searching"), ("review_required", "approved"),
                                            ("approved", "revision_requested"), ("failed", "reworking")])
def test_valid_transitions(current, target):
    check_transition(current, target)


@pytest.mark.parametrize("current,target", [("planned", "approved"), ("failed", "approved"),
                                            ("approved", "generating"), ("planned", "planned")])
def test_invalid_transitions(current, target):
    with pytest.raises(BoundaryError):
        check_transition(current, target)
