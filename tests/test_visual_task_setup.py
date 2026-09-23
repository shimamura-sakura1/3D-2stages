from tests.test_developer_setup import helper

def test_optional_visual_dependency_is_reported_separately(tmp_path,monkeypatch):
    module=helper();monkeypatch.setattr(module,'inspect_blender',lambda _: {'status':'ready'})
    report=module.inspect_host(tmp_path,{})
    assert report['visual_execution']['executor']=='main'
    assert report['render_director']['status']=='missing'
