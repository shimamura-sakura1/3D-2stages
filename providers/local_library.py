import copy
import re
import shutil
from pathlib import Path

from providers.base import AssetProvider
from runtime.errors import ProviderError
from runtime.io import inside, load_data
from runtime.validators import validate_contract, validate_model


class LocalLibraryProvider(AssetProvider):
    name = "local_library"

    def __init__(self, catalog_path):
        self.catalog_path = Path(catalog_path).resolve()
        document = load_data(self.catalog_path)
        if not isinstance(document, dict) or not isinstance(document.get("assets"), list):
            raise ProviderError("Local catalog must have an assets list")
        self.catalog = {}
        for candidate in document["assets"]:
            validate_contract("asset_candidate", candidate)
            key = candidate["candidate_id"]
            if key in self.catalog or candidate["provider"] != self.name:
                raise ProviderError("Duplicate candidate or incorrect local provider identity")
            self.catalog[key] = candidate

    def search(self, query, filters=None):
        terms = set(re.findall(r"\w+", query.casefold()))
        return [copy.deepcopy(c) for c in self.catalog.values()
                if terms & set(re.findall(r"\w+", " ".join(c["keywords"]).casefold()))]

    def get_metadata(self, asset_id):
        try:
            return copy.deepcopy(self.catalog[asset_id])
        except KeyError as exc:
            raise ProviderError(f"Local asset not found: {asset_id}") from exc

    def acquire(self, asset_id, output_dir):
        candidate = self.get_metadata(asset_id)
        source = validate_model(inside(self.catalog_path.parent, candidate["model"]))
        if source.suffix.lower().lstrip(".") != candidate["format"]:
            raise ProviderError("Catalog format does not match the source file")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"original{source.suffix.lower()}"
        if target.exists():
            raise ProviderError("Source revision already exists; it will not be overwritten")
        shutil.copy2(source, target)
        return target
