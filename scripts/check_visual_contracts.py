"""Audit a complete v0.2 document fixture; never execute, migrate, or approve it."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.errors import WorkflowError
from runtime.io import atomic_write
from runtime.visual_contracts import validate_visual_bundle


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError(f"Non-finite JSON value: {value}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="visual-audit-output")
    args = parser.parse_args(argv)
    try:
        bundle = json.load(sys.stdin, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        validate_visual_bundle(bundle)
        output = Path(args.output)
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise ValueError("Audit output directory must be empty")
        for kind, document in bundle["documents"].items():
            atomic_write(output / (kind + ".json"), document)
        print(json.dumps({"status": "valid", "contracts": sorted(bundle["documents"]),
                          "approval_granted": False, "execution": "not_performed"}))
        return 0
    except (WorkflowError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
