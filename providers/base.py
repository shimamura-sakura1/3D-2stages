from abc import ABC, abstractmethod
from dataclasses import dataclass


class AssetProvider(ABC):
    name: str

    @abstractmethod
    def search(self, query, filters):
        """Return contract-valid candidate dictionaries."""

    @abstractmethod
    def get_metadata(self, asset_id):
        """Return a candidate with verified provenance."""

    @abstractmethod
    def acquire(self, asset_id, output_dir):
        """Copy/download source files into the isolated output directory."""


@dataclass(frozen=True)
class SearchReport:
    candidates: list
    providers: tuple
    errors: tuple = ()

    @property
    def complete(self):
        return bool(self.providers) and not self.errors
