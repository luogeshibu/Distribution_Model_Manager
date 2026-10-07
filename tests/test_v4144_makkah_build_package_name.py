from pathlib import Path


def test_build_exe_outputs_makkah_site_tagged_artifacts():
    source = Path("build_exe.ps1").read_text(encoding="utf-8")

    assert '$SiteTag = "makkah"' in source
    assert '$AppName = "Distribution_Model_Manager_${SiteTag}_v$AppVersion"' in source
    assert '$DistAppDir = Join-Path $DistDir $AppName' in source
    assert '$ReleaseZip = Join-Path $ReleaseDir "$AppName.zip"' in source
    assert '$DistExe = Join-Path $DistAppDir "$AppName.exe"' in source


def test_makkah_release_version_is_4188():
    constants = Path("src/dmm/config/constants.py").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert 'APP_VERSION = "4.1.112"' in constants
    assert 'version = "4.1.112"' in pyproject
