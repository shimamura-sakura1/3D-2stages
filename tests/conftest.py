import copy
import json
import struct
from pathlib import Path

import pytest

from providers.local_library import LocalLibraryProvider
from runtime.io import atomic_write, load_data
from runtime.manifest_manager import ManifestManager
from runtime.planning import create_project, new_task
from runtime.stage1_executor import Stage1Executor


REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def candidate():
    return load_data(REPO / "examples/library/catalog.yaml")["assets"][0]


@pytest.fixture
def task():
    return new_task("bench", "wooden station bench")


@pytest.fixture
def provider():
    return LocalLibraryProvider(REPO / "examples/library/catalog.yaml")


@pytest.fixture
def project(tmp_path, task):
    root = tmp_path / "project"
    create_project(root, "test_project", "Quiet rural station", "full_pipeline", [task])
    manager = ManifestManager(root)
    manager.approve_plan()
    atomic_write(root / "stage2/blender_plan.yaml", load_data(REPO / "templates/blender_plan.yaml"))
    return manager


@pytest.fixture
def acquired(project, provider):
    Stage1Executor(project, {provider.name: provider}).run("bench")
    return project


def review(manager, decision="approved", instruction="", reviewer="user", asset_id="bench"):
    return manager.review({"asset_id": asset_id, "revision": manager.read()["assets"][asset_id]["revision"],
                           "decision": decision, "issues": [], "instruction": instruction, "reviewer": reviewer})


@pytest.fixture
def approved(acquired):
    review(acquired)
    return acquired


@pytest.fixture
def glb_bytes():
    # A genuine indexed triangle, not a mocked file extension.
    binary = struct.pack("<9f3H", 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 2)
    binary += b"\0" * ((-len(binary)) % 4)
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"mesh": 0}], "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
           "buffers": [{"byteLength": len(binary)}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36},
                           {"buffer": 0, "byteOffset": 36, "byteLength": 6}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                          "min": [0, 0, 0], "max": [1, 1, 0]},
                         {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"}]}
    data = json.dumps(doc).encode()
    data += b" " * ((-len(data)) % 4)
    return (struct.pack("<4sII", b"glTF", 2, 28 + len(data) + len(binary))
            + struct.pack("<II", len(data), 0x4E4F534A) + data
            + struct.pack("<II", len(binary), 0x004E4942) + binary)
