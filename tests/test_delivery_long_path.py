"""Publish approved deliveries under nested project roots on both hosts."""

import pytest

from runtime import cli as workflow_cli
from runtime import visual_delivery
from runtime.errors import WorkflowError
from runtime.io import filesystem_path, load_data, sha256
from tests.test_v02_delivery import approve, final_ready


def deliver(manager, version):
    args = workflow_cli.parser().parse_args([
        'deliver-v02', str(manager.root), '--expected-version', str(version)])
    return workflow_cli.execute(args)


def test_delivery_from_long_project_root(tmp_path):
    manager, _, _ = final_ready(tmp_path)
    approved = approve(manager)
    record = deliver(manager, approved['version'])
    package = manager.root / record['package']
    inventory = load_data(package / 'inventory.json')
    assert record['package'] == 'delivery/' + record['inventory_sha256']
    assert all(sha256(filesystem_path(package / entry['path'])) == entry['sha256']
               for entry in inventory['files'])
    assert manager.read()['state'] == 'delivered'


def test_delivery_copy_failure_rolls_back_on_long_root(tmp_path, monkeypatch):
    manager, _, _ = final_ready(tmp_path)
    approved = approve(manager)
    original = visual_delivery.shutil.copy2
    copied = 0

    def fail_after_one(source, target):
        nonlocal copied
        copied += 1
        if copied > 1:
            raise OSError('injected delivery copy failure')
        return original(source, target)

    before = manager.read()
    monkeypatch.setattr(visual_delivery.shutil, 'copy2', fail_after_one)
    with pytest.raises(WorkflowError, match='injected delivery copy failure'):
        deliver(manager, approved['version'])
    assert manager.read() == before
    assert not list(manager.root.glob('.delivery-stage-*'))
    assert not (manager.root / 'delivery').exists()
