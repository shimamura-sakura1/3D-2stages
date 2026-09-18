"""Run the accepted delivery assertions with portable physical file access."""

from tests import test_v02_delivery as historical
from runtime.io import filesystem_path


# All accepted cases keep their original function bodies unless physical Windows
# path access needs an equivalent extended-path spelling.
globals().update({name: case for name, case in vars(historical).items()
                  if name.startswith('test_') and callable(case)})


def test_latest_pass_history_and_rejection_snapshot_delivered(tmp_path):
    manager, job, metadata = historical.final_ready(tmp_path)
    manager.final_review_v02('rejected', expected_version=manager.read()['version'])
    review = historical.review_for(manager, metadata)
    review.update(document_id='post_rejection', revision=1)
    manager.submit_render_review(review, expected_version=manager.read()['version'])
    revision = {'schema_version': '0.2', 'project_id': manager.read()['project_id'],
                'scene_version': manager.read()['scene_version'],
                'document_id': 'revision_after_rejection', 'revision': 0,
                'based_on_review_id': review['document_id'],
                'render_metadata_id': metadata['document_id'], 'pass_index': 1,
                'max_preview_passes': 3,
                'actions': [{'action': 'roughness_variation', 'scope': 'machine',
                             'direction': 'increase', 'amount': 'small'}]}
    manager.apply_visual_revision(revision, expected_version=manager.read()['version'])
    job2, metadata2 = historical.complete_pass(manager)
    review2 = historical.review_for(manager, metadata2, 'final_review_required')
    review2.update(document_id='review_pass_01', revision=2)
    manager.submit_render_review(review2, expected_version=manager.read()['version'])
    from runtime.visual_delivery import final_review_context
    value = final_review_context(manager)['snapshot']
    assert value['pass_id'] == 'pass_01' and value['image'] == metadata2['image']['path']
    assert len(manager.read()['completion_evidence']) == 2
    historical.approve(manager)
    result = manager.deliver_v02(expected_version=manager.read()['version'])
    package = manager.root / result['package']
    for record in manager.read()['final_reviews']:
        assert filesystem_path(package / 'project' / record['path']).is_file()
    assert filesystem_path(package / 'project' / metadata['image']['path']).is_file()
    assert filesystem_path(package / 'project' / metadata2['image']['path']).is_file()
    setup = historical.Path(historical.load_data(job2['packet'])['outputs']['setup'])
    assert filesystem_path(package / 'project' / setup.relative_to(manager.root)).is_file()


def test_worker_role_and_missing_registered_package_refuse(tmp_path):
    from runtime.manifest_manager import ManifestManager
    manager, _, _ = historical.final_ready(tmp_path)
    worker = ManifestManager(manager.root, role='worker')
    before = historical.snapshot(manager)
    with historical.pytest.raises(historical.WorkflowError):
        worker.final_review_v02('approved', expected_version=manager.read()['version'])
    with historical.pytest.raises(historical.WorkflowError):
        worker.deliver_v02(expected_version=manager.read()['version'])
    assert historical.snapshot(manager) == before
    historical.approve(manager)
    result = manager.deliver_v02(expected_version=manager.read()['version'])
    historical.shutil.rmtree(filesystem_path(manager.root / result['package']))
    before = historical.snapshot(manager)
    with historical.pytest.raises(historical.WorkflowError):
        manager.deliver_v02(expected_version=manager.read()['version'])
    assert historical.snapshot(manager) == before
