from providers.base import SearchReport
from runtime.errors import WorkflowError
from runtime.validators import validate_contract


def search_assets(task, providers):
    """No inference fallback when a requested library is missing or unavailable."""
    candidates, errors, checked = [], [], []
    seen = set()
    for name in task["search"]["preferred_providers"]:
        checked.append(name)
        provider = providers.get(name)
        if provider is None:
            errors.append(f"Provider not configured: {name}")
            continue
        try:
            for query in task["search"]["keywords"]:
                for candidate in provider.search(query, {}):
                    validate_contract("asset_candidate", candidate)
                    if candidate["provider"] != name or candidate["source"]["provider"] != name:
                        raise WorkflowError("Provider identity mismatch")
                    key = (name, candidate["candidate_id"])
                    if key not in seen:
                        candidates.append(candidate)
                        seen.add(key)
        except (WorkflowError, OSError, ValueError) as exc:
            errors.append(f"{name}: {exc}")
    return SearchReport(candidates, tuple(checked), tuple(errors))
