# Changelog

All notable changes to Distribution Model Manager are documented here.











## [3.0.10] - 2026-08-10

### Changed
- Device validation is now G-file-driven: only database rows whose CODE is requested by a real G element participate in validation.
- Unrelated extra database device rows under the same combined_id are ignored.
- Device detail reports contain G elements only; DATABASE_INVENTORY pseudo rows were removed.
- An unlinked G element with a unique valid CODE match is now PASS and marked as requiring write-back instead of WARN.
- Complete database inventory parity and complete-table CODE integrity scans no longer block RMU association.

### Fixed
- Relevant device quantity is now derived from one unique matched DB device per G element.
- `_cffi_backend` packaging verification now checks for the actual binary module, not merely any cffi-related file.

## [3.0.9] - 2026-08-10

### Fixed
- Added explicit `cffi` and `_cffi_backend` packaging for python-oracledb / cryptography.
- Fixed packaged Oracle Thin Mode failure: `No module named '_cffi_backend'`.
- RMU summary now orders strictly by RMU sequence (`frame_index`).
- Device detail ordering now applies only one rule: group G object types inside each RMU.

### Changed
- Removed device-name, XML ID, DB ID, status, and RMU-name ordering from device-detail reports.
- Same-type device rows preserve validator/source order.

## [3.0.8] - 2026-08-10

### Fixed
- Fixed source-mode Workspace path. Runtime data now lives at `<project>/workspace/` instead of under `src/dmm/infrastructure/filesystem/`.
- Strengthened device-detail sorting so rows are grouped deterministically by G object type inside every RMU.
- Added regression coverage for duplicate-RMU (`RMU_NOT_UNIQUE`) rows.

### Changed
- Build output directory renamed from `Release/` to lowercase `release/`.
- `.gitignore` and documentation updated to match the lowercase release directory.

## [3.0.7] - 2026-08-10

### Fixed
- Explicitly packaged `cryptography`, required by python-oracledb Thin Mode.
- Fixed packaged Oracle connection failure `DPY-3016: No module named 'cryptography'`.

### Changed
- Replaced the build script again with a strict six-step build flow.
- Removed every smoke-test code path from `app.py` and `build_exe.ps1`.
- Build script now prints its own version, path, and target at startup to prevent accidentally running an older script.

## [3.0.6] - 2026-08-10

### Fixed
- Device detail reports are now consistently sorted instead of preserving validation-generation order.
- `CBreakerDis`, `ZhaiWaiJieDiDaoZha`, and `BusDis` records are grouped by device type.
- Database-only inventory rows remain grouped with their corresponding G object type.
- HTML and CSV exports now share the exact same canonical ordering.

### Added
- Natural sorting for RMU names and device names (`Y2` sorts before `Y10`).
- Report sorting unit tests.

## [3.0.5] - 2026-08-10

### Changed
- Removed packaged-EXE smoke testing from the build process.
- Simplified `build_exe.ps1` based on the proven GFileStudio v2.17.0 packaging flow.
- The build script no longer executes the freshly generated unsigned EXE.
- Retained source dependency validation and explicit PyInstaller collection for Oracle dependencies.

## [3.0.4] - 2026-08-10

### Fixed
- Windows Application Control blocking an unsigned freshly-built EXE no longer causes a false PyInstaller build failure.
- Runtime application failure and OS execution-policy blocking are now handled separately.

### Added
- PyInstaller xref verification for `getpass`, `oracledb`, `ssl`, `socket`, and `secrets`.
- `BUILD_VERIFICATION.txt` in every Release.
- Runtime smoke test remains mandatory whenever Windows allows the generated EXE to execute.

## [3.0.3] - 2026-08-10

### Fixed
- Fixed packaged EXE failure caused by missing Python standard library module `getpass`.
- Strengthened the PyInstaller `oracledb` hook with explicit dynamic/stdlib imports.
- Added a frozen-EXE smoke test that imports `getpass`, `ssl`, `socket`, `secrets`, `oracledb`, and `PySide6`.

### Changed
- Replaced the two-layer build entry with a single root `build_exe.ps1`.
- Removed `build.bat` and `scripts/build.ps1` to eliminate build-entry ambiguity.
- Release creation only happens after the actual packaged EXE passes the smoke test.

## [3.0.2] - 2026-08-10

### Fixed
- Fixed `RmuSettingsWidget.collect_settings()` being accidentally defined outside the class.
- Restored the fixed default Oracle password `OracleDV1Dec.25`.
- Empty passwords from older workspace configuration now fall back to the default password.

### Changed
- Kept `app.py` as the clearly documented Windows development entry point.
- Added `requirements.txt` for straightforward `pip install -r requirements.txt` setup.

## [3.0.1] - 2026-08-10

### Changed
- Added a root-level `app.py` as the standard Windows development launcher.
- `python app.py` now works directly from the project root.
- PyInstaller now uses the same `app.py` entry point for packaged builds.
- The internal `src/dmm` architecture remains unchanged.

## [3.0.0] - 2026-08-10

### Changed
- Reorganized the source tree into a `src/dmm` package layout.
- Separated UI, application orchestration, domain rules, infrastructure, configuration, and resources.
- Moved RMU label spatial constants out of global application configuration into RMU-specific constants.
- Renamed label parameters for clearer intent:
  - `DEFAULT_LABEL_MAX_DISTANCE` → `RMU_LABEL_SEARCH_MAX_DISTANCE`
  - `DEFAULT_LABEL_OVERLAP_TOLERANCE` → `RMU_LABEL_EDGE_TOLERANCE`
- Replaced `requirements.txt` with `pyproject.toml` as the dependency source of truth.
- Kept only one public build entry point: `build.bat`.
- Moved the PowerShell build implementation to `scripts/build.ps1`.
- Removed development convenience scripts `run.bat` and `install.bat`.
- Runtime output remains isolated under the application-owned `workspace/`.
- Preserved safe G-file association: original G files are never modified.

### Packaging
- Retained a dedicated PyInstaller hook for `oracledb`.
- Build fails if the Oracle dependency is not found in packaged output.
