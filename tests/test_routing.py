import pytest

from providers.base import SearchReport
from runtime.asset_router import AssetRouter
from runtime.errors import BoundaryError


def choose(task, *candidates):
    return AssetRouter().choose(task, SearchReport(list(candidates), ("local_library",)))


def test_matching_library_asset_routes_a(task, candidate):
    assert choose(task, candidate).route == "library_direct"


def test_good_geometry_bad_style_routes_b(task, candidate):
    candidate["scores"]["style_fit"] = 0.1
    assert choose(task, candidate).route == "library_hy3d_refine"


def test_no_asset_routes_c(task):
    assert choose(task).route == "hy3d_generate"


@pytest.mark.parametrize("change", [{"license": "proprietary"}, {"license_verified": False}])
def test_invalid_license_excluded(task, candidate, change):
    candidate["source"].update(change)
    assert choose(task, candidate).candidate is None


def test_refinement_requires_modification_rights(task, candidate):
    candidate["scores"]["style_fit"] = 0.1
    candidate["source"]["modification_allowed"] = False
    assert choose(task, candidate).route == "hy3d_generate"


def test_generation_disabled_fails_instead_of_bypassing_license(task, candidate):
    candidate["source"]["license_verified"] = False
    task["routing"]["allow_route_c"] = False
    with pytest.raises(BoundaryError):
        choose(task, candidate)


def test_provider_failure_is_not_an_empty_library(task):
    with pytest.raises(BoundaryError, match="incomplete"):
        AssetRouter().choose(task, SearchReport([], ("local_library",), ("timeout",)))


def test_all_requested_libraries_must_be_searched(task):
    task["search"]["preferred_providers"].append("sketchfab")
    with pytest.raises(BoundaryError, match="All requested"):
        choose(task)


def test_explicit_route_still_obeys_quality_and_search(task, candidate):
    task["routing"]["preferred_route"] = "library_direct"
    candidate["scores"]["style_fit"] = 0.1
    with pytest.raises(BoundaryError):
        choose(task, candidate)


def test_unusable_geometry_not_selected(task, candidate):
    candidate["geometry_usable"] = False
    assert choose(task, candidate).route == "hy3d_generate"


def test_cc_by_cannot_drop_attribution(task, candidate):
    candidate["source"]["license"] = "cc_by"
    assert choose(task, candidate).route == "hy3d_generate"
    candidate["source"]["attribution_required"] = True
    assert choose(task, candidate).route == "library_direct"
