from dataclasses import dataclass
from importlib.resources import files

from runtime.errors import BoundaryError
from runtime.io import load_data
from runtime.validators import validate_contract


@dataclass(frozen=True)
class RouteDecision:
    route: str
    candidate: dict | None
    score: float
    reason: str


class AssetRouter:
    def __init__(self):
        self.policy = load_data(files("policies").joinpath("routing_policy.yaml"))
        self.licenses = load_data(files("policies").joinpath("licensing_policy.yaml"))

    def legal(self, candidate, modification=False, *, generated_output=False):
        source = candidate["source"]
        license_id = source.get("license")
        if not isinstance(license_id, str):
            return False
        scoped = self.licenses.get("generated_output_licenses", {}).get(license_id)
        # Generated model terms must never activate from a library candidate.
        if scoped is not None:
            return (generated_output is True and source.get("license_verified") is True
                    and all(source.get(key) == scoped[key] for key in ("provider", "asset_id", "original_url"))
                    and source.get("attribution_required") is True
                    and (not modification or source.get("modification_allowed") is True))
        return (source.get("license_verified") is True and license_id in self.licenses["allowed_licenses"]
                and (source["license"] != "cc_by" or source.get("attribution_required") is True)
                and (not modification or source.get("modification_allowed") is True))

    def score(self, candidate):
        scores = candidate["scores"]
        return sum(weight * (1 if key == "licensing" else
                              1 - scores[key] if key == "cleanup_cost" else scores[key])
                   for key, weight in self.policy["weights"].items())

    def choose(self, task, report):
        validate_contract("asset_task", task)
        if not report.complete:
            raise BoundaryError("Library search incomplete: " + "; ".join(report.errors))
        if not set(task["search"]["preferred_providers"]).issubset(report.providers):
            raise BoundaryError("All requested libraries must be searched before routing")
        ranked = []
        for candidate in report.candidates:
            validate_contract("asset_candidate", candidate)
            if self.legal(candidate) and candidate["format"] in self.policy["supported_formats"]:
                ranked.append((self.score(candidate), candidate))
        ranked.sort(key=lambda pair: (-pair[0], pair[1]["candidate_id"]))
        routing = task["routing"]
        preferred = routing["preferred_route"]
        limits = self.policy["thresholds"]
        if routing["allow_route_a"] and preferred in ("auto", "library_direct"):
            for score, candidate in ranked:
                if (score >= limits["direct_use_score"] and candidate["geometry_usable"]
                        and candidate["scores"]["geometry_quality"] >= limits["geometry_min"]
                        and candidate["scores"]["style_fit"] >= limits["direct_style_min"]):
                    return RouteDecision("library_direct", candidate, score, "Suitable licensed library asset")
        if routing["allow_route_b"] and task["hy3d"]["enabled"] and preferred in ("auto", "library_hy3d_refine"):
            for score, candidate in ranked:
                if (score >= limits["refinement_score"] and candidate["geometry_usable"]
                        and candidate["scores"]["geometry_quality"] >= limits["geometry_min"]
                        and self.legal(candidate, modification=True)):
                    return RouteDecision("library_hy3d_refine", candidate, score, "Usable base with modification rights")
        if routing["allow_route_c"] and task["hy3d"]["enabled"] and preferred in ("auto", "hy3d_generate"):
            return RouteDecision("hy3d_generate", None, 0, "Completed library search; generation selected")
        raise BoundaryError("No suitable permitted route; change constraints or add a library asset")
