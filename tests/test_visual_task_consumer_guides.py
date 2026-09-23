"""Check source guides and their consumer copies, including executable examples."""
import re
from pathlib import Path
import pytest

from runtime.cli import parser
from scripts.export_production import export_production

ROOT = Path(__file__).resolve().parents[1]


def test_consumer_guides_preserve_portability_and_legacy_scope(tmp_path):
    names = ['docs/platforms.md', 'docs/v02/render-director.md']
    sources = {name: (ROOT / name).read_text(encoding='utf-8') for name in names}
    destination = tmp_path / 'consumer'
    export_production(ROOT, destination)
    for name, source in sources.items():
        assert (destination / name).read_text(encoding='utf-8') == source
        for target in re.findall(r'\]\(([^)]+)\)', source):
            if '://' not in target and not target.startswith('#'):
                assert ((destination / name).parent / target.split('#')[0]).is_file()
        for example in re.findall(r'^python -m runtime.cli (.+)$', source, re.M):
            arguments = example.split()
            arguments = ['1' if item == 'N' else item for item in arguments]
            if arguments == ['--help']:
                with pytest.raises(SystemExit) as exit_info:
                    parser().parse_args(arguments)
                assert exit_info.value.code == 0
            else:
                assert parser().parse_args(arguments).command == arguments[0]
    platforms = sources[names[0]]
    assert 'BLENDER_EXECUTABLE' in platforms and '重新生成操作包' in platforms
    assert '不自动切换 MCP/batch' in platforms
    legacy = sources[names[1]]
    assert legacy.startswith('> Compatibility reference for existing legacy directed projects.')
    assert '(task-tracking.md)' in legacy and '(visual-task-adapters.md)' in legacy
