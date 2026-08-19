from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule
from dmm.domain.feeder.topology import FeederDrawingTopologyClassifier
from dmm.domain.gfile.parser import GParser


def _write(path: Path, body: str):
    path.write_text(f'<G width="4000" height="2500"><Layer>{body}</Layer></G>', encoding='utf-8')
    return path


def test_one_cbreaker_is_high_confidence_single_even_without_feedline(tmp_path):
    g = _write(
        tmp_path / 'single.g',
        '<Bus id="b1" x="100" y="100" w="1000" h="6" />'
        '<CBreaker id="src1" x="400" y="180" w="20" h="30" />'
        '<Text id="t1" x="300" y="50" w="100" h="20" ts="AJWD-43" />',
    )
    p = FeederDrawingTopologyClassifier(GParser()).classify(g)
    assert p['source_cbreaker_count'] == 1
    assert p['drawing_type'] == 'SINGLE_FEEDER'
    assert p['classification_reason'] == 'SINGLE_SOURCE_CBREAKER'
    assert p['classification_confidence'] == 'HIGH'


def test_multiple_cbreakers_are_high_confidence_composite_without_links(tmp_path):
    g = _write(
        tmp_path / 'multi.g',
        '<CBreaker id="src1" x="400" y="180" w="20" h="30" />'
        '<CBreaker id="src2" x="1400" y="180" w="20" h="30" />',
    )
    p = FeederDrawingTopologyClassifier(GParser()).classify(g)
    assert p['source_cbreaker_count'] == 2
    assert p['drawing_type'] == 'MULTI_FEEDER_COMPOSITE'
    assert p['classification_reason'] == 'MULTIPLE_SOURCE_CBREAKERS'
    assert p['classification_confidence'] == 'HIGH'


def test_cbreakerdis_is_not_counted_as_source_breaker(tmp_path):
    g = _write(
        tmp_path / 'rmu_switches.g',
        '<CBreaker id="src1" x="400" y="180" w="20" h="30" />'
        + ''.join(f'<CBreakerDis id="rmu{i}" x="{500+i}" y="500" w="20" h="30" />' for i in range(20)),
    )
    p = FeederDrawingTopologyClassifier(GParser()).classify(g)
    assert p['source_cbreaker_count'] == 1
    assert p['drawing_type'] == 'SINGLE_FEEDER'


def test_zero_cbreaker_uses_topology_fallback(tmp_path):
    g = _write(
        tmp_path / 'legacy.g',
        '<Bus id="b1" x="100" y="100" w="1000" h="6" key_name="busbarsection AJWD" />'
        '<Text id="t1" x="300" y="50" w="100" h="20" ts="AJWD-43" />',
    )
    p = FeederDrawingTopologyClassifier(GParser()).classify(g)
    assert p['source_cbreaker_count'] == 0
    assert p['drawing_type'] == 'SINGLE_FEEDER'
    assert p['classification_reason'].startswith('TOPOLOGY_FALLBACK_')
    assert p['classification_confidence'] in {'MEDIUM', 'LOW'}


def test_uploaded_real_g_files_follow_source_cbreaker_contract():
    cases = [
        ('/mnt/data/TEST88.sln.pic(4).g', 1, 'SINGLE_FEEDER'),
        ('/mnt/data/JED-CTL-AJWD-03.sln.pic.g', 1, 'SINGLE_FEEDER'),
        ('/mnt/data/JED-NTH-ABH-03.sln.pic(3).g', 1, 'SINGLE_FEEDER'),
        ('/mnt/data/JED-NTH-ABH.sln.pic(8).g', 44, 'MULTI_FEEDER_COMPOSITE'),
    ]
    for filename, count, expected in cases:
        path = Path(filename)
        if not path.exists():
            continue
        profile = FeederModelModule._drawing_profile(path)
        assert profile['source_cbreaker_count'] == count
        assert profile['drawing_type'] == expected
        assert profile['classification_confidence'] == 'HIGH'
