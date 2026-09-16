"""Validate a complete structural sample bundle using the production schemas.

This deterministic audit tool checks document shapes only. It does not approve
assets, execute providers, or prove that referenced model files exist.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.errors import WorkflowError
from runtime.io import atomic_write
from runtime.validators import validate_contract, validate_manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="audit-output")
    args = parser.parse_args(argv)
    try:
        bundle = json.load(sys.stdin)
        validate_contract("audit_bundle", bundle)
        documents = bundle["documents"]
        for name, value in documents.items():
            validate_contract(name, value)
        validate_manifest(documents["project_manifest"])
        output = Path(args.output)
        if output.exists() and any(output.iterdir()):
            raise ValueError("Audit output directory must be empty")
        for name, value in documents.items():
            atomic_write(output / (name + ".json"), value)
        print(json.dumps({"status": "valid", "contracts": sorted(documents)}))
        return 0
    except (WorkflowError, ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
