# Changelog

All notable changes to Distribution Model Manager are documented here.



















## [3.0.23] - 2026-08-10

### Fixed
- Corrected BusDis default domain from `0` to `1`.
- BusDis now uses Table ID `13506`, table `dms_bs_device`, Domain `1`.
- BusDis Expected KeyID therefore uses `DeviceID + (1 << 32)`.

### Migration
- Legacy saved configuration `BusDis / 13506 / Domain 0` is automatically migrated to Domain `1` on startup.

### Reporting
- Changed the HTML status-color legend from one horizontal row to a vertical list.
- Each status now has its own row with a dedicated label and explanation.

## [3.0.22] - 2026-08-10

### Fixed
- RMU NAME lookup now treats `dms_combined_device.NAME` as a native string field.
- Replaced `TRIM(TO_CHAR(name))` with `TRIM(name)` for RMU lookup.
- RMU names are never converted to integers.

### Changed
- RMU recognition now supports common engineering names containing letters,
  digits, hyphens, underscores and dots, up to 128 characters.
- Added regression coverage for names such as `RMU-42646`, `ABC_123`,
  `JED-RMU-01` and numeric-only names.

## [3.0.21] - 2026-08-10

### Changed
- Feeder mismatch is now warning-only and no longer blocks automatic model association.
- RMU feeder mismatch and device feeder mismatch use orange `FEEDER` status.
- Duplicate/missing RMU still produces a red RMU-summary error.
- Duplicate/missing RMU blocks automatic association only for unlinked G elements.
- Existing manual KeyIDs are still inspected when the RMU name is duplicated/missing.
- Existing manual links validate logical CODE/p_NameString and actual RMU ownership.
- Existing KeyID pointing to another RMU remains a hard `RMU_LINK` error.
- Duplicate-RMU device rows with a valid existing manual link can be PASS/FEEDER rather than being forced into BLOCKED.

## [3.0.20] - 2026-08-10

### UI
- Removed the model-operation combo box from the top task form.
- Added explicit bottom action buttons: Model Validation, Association Preview, Execute Association.
- Replaced ambiguous "Run Current Task" behavior with explicit task actions.
- Report buttons now use task-specific labels and are hidden when their files do not exist.

### Reporting
- Validation reports are stored under `validation_report`.
- Association-preview reports are stored under `association_preview_report`.
- After association write-back, the generated G-file copies are revalidated and a full final report is written to `association_result_report`.
- Final association report uses the same RMU/device report structure as model validation.

### Safety
- Original G files remain unchanged.
- Association write-back still targets only copies under Workspace `g_output`.

### Assets
- Rebuilt `app_logo.png` and `app_logo.ico` with transparent outer corners around the green rounded contour.

## [3.0.19] - 2026-08-10

### Fixed
- Fixed `RMU_NOT_FOUND_IN_DATABASE` rows being appended after all database-matched RMUs.
- RMU summary now always sorts strictly by G-file RMU sequence.

### Changed
- RMU summary is one row per G RMU frame.
- Duplicate Oracle RMU records no longer expand into multiple summary rows.
- Duplicate RMUs show only the database match count and a blocking error; multiple IDs are intentionally hidden.
- Removed duplicate report columns: first-frame XML ID, G match count, duplicate G RMU sequence, G frame XML IDs, and database record sequence.
- Device detail remains G-element based.

## [3.0.18] - 2026-08-10

### Changed
- RMU label color is now used only when one RMU owns multiple candidate names.
- A single candidate label is always selected directly, regardless of color.
- For multiple candidates: nearest green wins; if no green exists, nearest label wins.
- Text ownership remains one-to-one with the nearest RMU frame.

## [3.0.17] - 2026-08-10

### Fixed
- Fixed a green RMU label being reused by multiple vertically aligned RMU frames.
- Each candidate Text now belongs to exactly one nearest RMU frame.
- Fixed the reported duplicate `15953` caused by label ownership, not by Oracle.

### Changed
- RMU summary is now database-record based: one `dms_combined_device.ID`
  produces one summary row.
- Device details remain G-element based.
- If several G frames point to the same database RMU ID, their frame
  indices/XML IDs are aggregated on the single database summary row.

## [3.0.16] - 2026-08-10

### Fixed
- Restored the missing `RmuValidator._make_expected_keyid()` method.
- KeyID generation now explicitly uses `DeviceID + (Domain << 32)`.
- Fixed the runtime crash encountered during CBreakerDis validation.

### Added
- Added KeyID encoding regression tests for Domain 0 and Domain 40.
- Added a validator private-method integrity test that detects undefined
  `self._xxx()` method calls before release.

### Architecture
- Kept `src/dmm` intentionally. `dmm` is the Python package namespace for
  Distribution Model Manager, not a second application.

## [3.0.15] - 2026-08-10

### Added
- Added color-aware RMU label recognition from G-file Text lc/lcc attributes.
- Green RMU labels can be found across long directional distances.
- Added nearest-green selection when multiple labels exist above/beside an RMU.
- Added support for engineering RMU names such as AK-900841 instead of numeric-only labels.
- Added current-KeyID RMU-name verification via device combined_id -> dms_combined_device.
- Added purple RMU_LINK status for links that point to another RMU even on the same feeder.
- Added current linked RMU name/ID fields to device details.

### Changed
- Non-green RMU labels retain the legacy search-distance limit as a safe fallback.
- Existing-link correctness now validates RMU identity independently from feeder identity.

## [3.0.13] - 2026-08-10

### Added
- Added independent visual states: PASS / WARN / FEEDER / BLOCKED / FAIL.
- Added status-color legends to HTML reports and Help.
- Duplicate RMUs now permit read-only inspection of existing manual KeyID links.

### Changed
- Feeder mismatch uses orange FEEDER instead of red FAIL.
- Duplicate RMU remains a permanent automatic-association block.
- Under duplicate RMUs, unlinked devices are red FAIL; linked devices are inspected for CODE/feeder consistency and become orange FEEDER or blue BLOCKED.
- Unrelated database devices remain ignored.

## [3.0.12] - 2026-08-10

### Fixed
- Fixed `NameError: g_file is not defined`; feeder extraction now uses the parsed G-file path.

### Added
- Added strict feeder consistency checks for every unique RMU.
- Added feeder consistency checks for each uniquely CODE-matched database device.
- Device details now show the exact matched database device plus G-file feeder and database-device feeder.

### Changed
- RMU name 0 rows or multiple rows remains a hard association block.
- A unique RMU on the wrong feeder is now a hard association block.
- A requested CODE with no database row reports that the device does not exist.
- A requested CODE with multiple database rows reports a CODE duplication error.
- Unrelated extra database devices remain ignored.

## [3.0.11] - 2026-08-10

### Added
- Added G-file feeder hint extraction (`ABH-06` from `JED-NTH-ABH-06.sln.pic.g`).
- Added separator-insensitive feeder comparison for `ABH-06`, `ABH_06`, and `ABH 06`.
- Added explicit FEEDER_ID resolution through table 13500 / `dms_feeder_device`.
- Added readable database feeder composition using station name + feeder NAME.
- Added feeder validation columns to the RMU summary report.

### Changed
- Unlinked but database-matched G devices are WARN/yellow again, while remaining association-ready.
- Feeder mismatch now blocks RMU association.
- Device-detail report remains G-element-only.

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
