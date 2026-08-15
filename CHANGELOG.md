





## [3.7.1] - 2026-08-15

### RMU report cleanup
- Removed the `状态类型` column from RMU HTML summary and
  `环网柜汇总.csv`.
- `状态` and `说明` remain.
- Internal severity/status classification is still retained for business
  logic and row coloring; only the duplicated report column was removed.
- No validation, candidate, association, database, feeder, KeyID/BV_ID,
  SMART/SMR, or write-back logic was changed.

## [3.7.0] - 2026-08-15

### Baseline
- This version is rebuilt directly from the original v3.6.9 source package.

### Unified RMU report
- Removed the separate `环网柜档案.csv`.
- Merged its RMU-level fields into `环网柜汇总.csv`.
- HTML `环网柜汇总` uses the same unified RMU fields.
- Removed the `打开环网柜档案 CSV` button and `rmu_profile_csv` artifact.

### Unchanged from v3.6.9
- Simplified workflow remains:
  `模型校验 -> 勾选候选 -> 执行模型关联`.
- No separate association-preview button was reintroduced.
- RMU/feeder recognition, candidate generation, selected-only execution,
  database recheck, KeyID/BV_ID write-back, SMART/SMR, logical CODE,
  and all other validation/association logic are unchanged.

## [3.6.9] - 2026-08-15

### Simplified model-association workflow
- Removed the user-facing `模型关联预览` button.
- The workspace now exposes only:
  `模型校验` -> select validated candidates -> `执行模型关联`.
- RMU and feeder validation each perform one analysis pass and immediately
  populate the selectable association table from the same validated snapshot.
- The former `preview_association()` module function is retained only as an
  internal candidate builder; it is no longer a separate user task.

### Faster selected execution
- `执行模型关联` consumes the current validation snapshot and only the rows
  explicitly checked by the user.
- Source-file fingerprints and current database facts are still rechecked
  immediately before write-back.
- RMU execution continues to avoid a second full-drawing validation pass.
- Feeder execution now also avoids a second full-drawing validation pass:
  selected topology regions refresh the current `dms_section_device` pool,
  protect unselected valid links, recalculate only selected FeedLine targets,
  write exact selected XML IDs, and build an operation-scoped report directly.
- Association result HTML/CSV contains only the objects selected in this
  execution, including selected rows skipped because execution-time facts
  changed.

### UI wording
- Startup workflow text is now:
  `模型校验 -> 勾选可关联对象 -> 执行模型关联`.
- Removed user-facing wording that implied a separate association-preview step.

## [3.6.8] - 2026-08-15

### RMU HTML report
- Removed the `环网柜档案` section from RMU HTML only.
- `环网柜档案.csv` remains generated independently and unchanged.
- All other model validation, association, database, feeder and UI logic remains unchanged.

## [3.6.7] - 2026-08-13

### Startup fix
- Fixed the Help page startup crash:
  `NameError: name 'policy_text' is not defined`.
- The broken leftover variables `policy_text`, `policy_layout`, and `policy`
  were removed.
- The device-name help group now correctly uses its own
  `naming_text`, `naming_layout`, and `naming` widgets.

### Business naming refactor
- Renamed the RMU device business field from `p_name_string` to
  `logical_code`.
- `logical_code` now has one clear meaning:
  the logical device CODE derived from the visible G drawing and used to
  compare with the database `CODE`.
- `CBreakerDis.logical_code` = resolved graphical switch text.
- `ZhaiWaiJieDiDaoZha.logical_code` = paired graphical breaker code + `D`.
- `BusDis.logical_code` = `BUS`.
- The default RMU row no longer seeds any logical value from the raw XML
  `p_NameString` attribute.
- Renamed `CODE_EQUALS_PNAME` to `CODE_EQUALS_LOGICAL_CODE`.
- Renamed PNAME-oriented validation/error identifiers to logical-CODE
  terminology.

### Raw XML isolation
- The G parser raw XML accessor is now explicitly named
  `xml_p_name_string`.
- It exists only for parsing/debug compatibility and is not used by RMU
  business naming.
- Generic RMU/feeder visible-text recognition now reads `Text/DText.ts`
  instead of falling back to raw XML `p_NameString`.

### UI / report readability
- RMU work-table and reports use `逻辑CODE（图上规则）`.
- Internal association execution reads `logical_code`.
- `p_NameString` remains mentioned only in help text that explicitly says
  the raw XML attribute is ignored.

### Regression
- Added startup-help regression checks for the removed `policy_*` variables.
- Added a test proving the default RMU device row never copies XML
  `p_NameString` into `logical_code`.
- Added a source-level regression check ensuring the RMU business layer no
  longer contains the old `p_name_string` field.

## [3.6.6] - 2026-08-13

### Switch naming is graphical-text-only
- Removed the user-selectable `p_NameString` / graphical-text switch-name mode.
- `CBreakerDis` device names now ALWAYS come from visible text inside the RMU.
- XML `CBreakerDis.p_NameString` is never used as a device-name source.
- `ZhaiWaiJieDiDaoZha` logical name is always:
  `paired graphical breaker name + D`.
- `BusDis` logical name is always `BUS`.
- RMU settings UI now displays the fixed rule:
  `环网柜内图上文字（固定）`.
- Old persisted `P_NAME_STRING` configuration values are ignored safely.

### Graphical device-name database validation
- Every graphical breaker name is checked against database CODE under the
  current uniquely resolved RMU.
- A graphical name that cannot be resolved, has no corresponding CODE, or
  matches duplicate CODE rows produces an explicit device error telling the
  user to check that RMU's switch naming.
- Device report wording now uses `图上逻辑名称` instead of presenting the
  internal compatibility field as an XML p_NameString.

### RMU type two-stage recognition
- Rule 1 (authoritative):
  use cabinet Text/DText Y1/Y2/Y3/... and Q1/Q2/Q3/... .
  Each Y = one L; each Q = one T.
- Rule 2 (fallback only):
  if NO Y/Q text is recognized at all, use CBreakerDis.devref:
  `Load_Breaker => L`, `Circuit_Breaker => T`.
- When both rule outputs are available, they are ALWAYS cross-checked.
- A mismatch never overrides the text-derived type and does not by itself
  block a database-valid model association.

### Explicit type cross-check warning
- Added `柜型校验状态` and `柜型交叉校验说明` to RMU HTML/CSV reports.
- If text type and devref type differ:
  - status = WARN when no more severe RMU/device issue exists;
  - the report names the RMU (or rectangle XML ID if the RMU name cannot be
    resolved);
  - the report includes both type values;
  - the message asks the user to inspect Y/Q naming and switch devref template.
- Console prints the same targeted warning.

### Help/UI
- RMU help now documents one fixed device-name source only.
- RMU help documents the two-stage cabinet-type algorithm and mandatory
  cross-validation.
- Feeder trusted-RMU processing uses the same graphical-text-only RMU device
  naming behavior.

## [3.6.5] - 2026-08-13

### RMU type recognition: Y/Q text is absolutely authoritative
- RMU cabinet type is determined first from Text/DText located inside the RMU:
  - Y1/Y2/Y3/Y4/... => one L each
  - Q1/Q2/Q3/Q4/... => one T each
- Y/Q labels are naturally ordered as Y1,Y2,... then Q1,Q2,...
- As long as at least one Y/Q label is recognized, the text-derived type is
  the final type.
- `CBreakerDis.devref` is now only a fallback when NO Y/Q label can be
  recognized at all.
- When both text and devref are available, devref is only cross-check data and
  never overrides the text result.

### Smart RMU recognition
- Added global SMART/SMR recognition across the entire G drawing.
- Every exact SMART or SMR Text/DText marker is assigned to the nearest RMU.
- There is no maximum-distance cutoff, because SMART is commonly inside the
  cabinet while SMR may be outside.
- Either SMART or SMR makes the RMU smart.
- If both SMART and SMR belong to one RMU, it is still one smart RMU and the
  marker field records `SMART, SMR`.
- Feeder trusted-RMU diagnostics reuse the same smart metadata.

### RMU reports
- RMU HTML summary now includes:
  - cabinet type;
  - type source;
  - text/devref cross-check;
  - smart YES/NO;
  - SMART/SMR marker types;
  - database/device completeness.
- Added a new compact HTML `环网柜档案` table.

### New RMU profile CSV
- Every RMU validation/association report now creates:
  `report_环网柜档案.csv`.
- Exactly one row per RMU containing:
  - G file;
  - RMU sequence and rectangle XML ID;
  - RMU name;
  - RMU type and source;
  - smart status and SMART/SMR markers;
  - database record count;
  - whether the RMU database record is unique;
  - RMU ID;
  - G device count;
  - uniquely matched database device count;
  - whether RMU devices are complete;
  - validation status and explanation.
- `设备是否完整=YES` means the RMU itself is database-unique and every G
  device participating in validation uniquely resolves to a database device
  under the same RMU. Old/wrong G KeyID does not by itself make database
  inventory incomplete.

### UI and help
- Added `打开环网柜档案 CSV` result button.
- RMU and feeder help pages now document strict Y/Q priority, devref fallback,
  SMART/SMR global nearest-RMU assignment, and the RMU profile report.

### Regression
- Existing tests updated to the final field rule: partial Y/Q text still wins
  over devref.
- Added SMART+SMR nearest-RMU tests and RMU profile CSV/HTML tests.
- Actual `JED-CTL-AJWD-26.sln.pic.g` regression:
  - 37 structural RMUs detected;
  - 11 RMUs receive SMART markers;
  - RMU `25583` (Rect XML ID 2000567) => `2L1T`,
    source `TEXT_YQ`, labels `Y1,Y2,Q1`, devref cross-check `2L1T`.

## [3.6.4] - 2026-08-13

### RMU type recognition
- Added RMU cabinet type recognition such as `2L1T` and `3L1T`.
- Primary rule reads Y/Q Text or DText inside the RMU rectangle: each `Y*` is one L and each `Q*` is one T.
- Added devref cross-check/fallback: `Load_Breaker` -> L and `Circuit_Breaker` -> T.
- Complete Y/Q text is authoritative; devref is used when text is incomplete.
- Text/devref mismatch is reported but does not block existing RMU association eligibility.
- RMU summary HTML/CSV now exposes type, recognition source and consistency.
- Feeder trusted-RMU diagnostics now include the RMU type.
- Updated RMU and feeder module help pages with the new rules.

### Uploaded AJWD-26 regression
- Verified RMU `25583` (frame XML ID `2000567`) as `2L1T`.
- Its G XML contains Y1, Y2, Q1 and devrefs with two Load_Breaker plus one Circuit_Breaker; both rules agree.
- Across the uploaded file, 35 RMUs resolve to `2L1T` and 2 RMUs resolve to `3L1T`; text and devref results agree for all detected RMUs.

# Changelog

## [3.6.3] - 2026-08-13

- 同步更新 RMU 环网柜模型帮助：补充三类图元结构硬条件、数据库事实优先修复原则、环网柜筛选与仅执行勾选设备规则。
- 同步更新馈线模型帮助：明确不依赖馈线名称，使用可信 RMU + FEEDER_ID + 拓扑区域确定馈线归属。
- 补充 FeedLine 未关联、旧关联、设备重建、表号/域号错误以及 DUPLICATE_LINK 的可选择修复说明。
- 帮助页与 v3.6.x 当前实际校验/关联逻辑保持一致。


## [3.6.2] - 2026-08-13

### RMU structural hard rule
- RMU recognition now explicitly requires the candidate rectangle to contain all three core G object types: `CBreakerDis`, `ZhaiWaiJieDiDaoZha`, and `BusDis` (at least one of each).
- Missing any one of the three types means the rectangle is not an RMU candidate.
- The same structural rule is used by the standalone RMU module and by the feeder module when it discovers RMUs as topology references.
- Existing selected-direction/global Text/DText cabinet-name recognition remains unchanged.

### FeedLine selectable association table
- The feeder model now uses the same explicit-selection interaction as the RMU model.
- After feeder validation, the workspace shows `可关联馈线段选择（模型校验结果）`.
- Rows can be filtered by FEEDER_ID, FeedLine XML ID, target section name, or explanation text.
- Only database-safe `UNLINKED`, `RELINK`, or `DUPLICATE_LINK` rows are checkable.
- Execution processes only the FeedLine rows selected by the user; unselected FeedLines remain untouched.
- The table keeps a fixed 38 px row height and tooltip access to full long text.

### Duplicate FeedLine repair
- When multiple FeedLines use the same valid `dms_section_device`, ALL duplicated rows are now reported as `DUPLICATE_LINK` rather than treating the first row as PASS.
- Duplicate rows are repairable when the topology region has one confirmed FEEDER_ID and the database section pool is unique.
- If the user selects only one duplicated row, unselected duplicate rows reserve their current database section and the selected row is reassigned to another available section.
- If multiple duplicate rows are selected, they re-enter the region allocation pool together and are assigned in FeedLine top-to-bottom / left-to-right order from currently available sections.
- Execution refreshes the current `dms_section_device` pool before write-back and writes only selected XML IDs.

### HTML report
- Feeder summary and FeedLine detail tables continue to provide report-only checkboxes.
- Checking a report row keeps the entire row highlighted while horizontally scrolling; these HTML checkboxes never change model association behavior.

### Regression
- Added tests confirming that an RMU rectangle missing one of the three required G device types is rejected.
- Added tests confirming that all repeated FeedLine links are exposed as selectable duplicate-repair candidates.

# Changelog

All notable changes to Distribution Model Manager are documented here.



































## [3.6.0] - 2026-08-13

### Feeder model: RMU-topology architecture
- Replaced feeder-name/spatial-title association as the automatic feeder source.
- Single-feeder and merged overview G drawings now use one unified pipeline:
  `trusted RMU -> RMU.FEEDER_ID -> G topology component -> dms_section_device`.
- FeedLine ownership no longer depends on ABH-xx / AJWD-xx text.

### Trusted RMU reference rules
- An RMU can be used as a feeder reference only when:
  - its G RMU name resolves to exactly one dms_combined_device record;
  - RMU ID and FEEDER_ID are valid;
  - at least one existing RMU device KeyID can be verified;
  - every currently linked RMU device used as evidence resolves to its expected table/domain and belongs to that same RMU.
- The following RMUs are reported but ignored as feeder references:
  - no current model link;
  - database RMU name 0/multiple records;
  - missing FEEDER_ID;
  - existing incorrect/cross-RMU model links.

### Topology consistency guard
- G XML network objects are grouped by connection geometry using FeedLine, ConnectLine, Bus and major electrical switch objects.
- RMU frames bridge the network branches that physically enter the cabinet.
- A topology region with no trusted RMU is `NO_TRUSTED_RMU_REFERENCE` and cannot auto-associate.
- If trusted RMUs in one connected region expose different FEEDER_ID values, the whole region is blocked as `FEEDER_RMU_CONFLICT` and requires manual confirmation.
- No majority vote is used.
- Disconnected fragments independently confirmed to the same FEEDER_ID are consolidated into one allocation pool, preventing duplicate SECxxx assignment.

### FeedLine allocation
- Once one FEEDER_ID is confirmed, the validator queries the real rows from dms_section_device for that FEEDER_ID.
- Correct existing FeedLine links reserve their database section first.
- Wrong-feeder, wrong table/domain or duplicate old links become RELINK candidates.
- Unlinked + RELINK FeedLines are ordered top-to-bottom, then left-to-right.
- Remaining database sections are naturally ordered by actual SEC number and assigned from smallest to largest.
- Database section numbers are never generated by the application.
- Expected KeyID remains table 13503 / domain 1 and voltype remains dms_section_device.BV_ID.

### Feeder HTML report row markers
- Added a checkbox column to both `馈线汇总` and `馈线段明细` HTML tables.
- Checking a row keeps the entire row highlighted while horizontally scrolling.
- These checkboxes are report-only manual markers and do not participate in validation or write-back.
- Feeder summary now exposes trusted RMU count, ignored RMU count, trusted RMU names, trusted FEEDER_ID values and ignored-RMU reasons.

### UI
- Removed the meaningful distinction between single/multi feeder processing modes.
- Feeder page now shows the fixed mode `RMU 拓扑自动识别（固定）` because the same topology algorithm handles both drawing forms.
- Updated current-module help to document RMU trust, FEEDER_ID consistency and blocking rules.

### Tests
- Added topology tests covering:
  - two trusted RMUs with the same FEEDER_ID;
  - conflicting FEEDER_ID values blocking the whole connected region;
  - unlinked RMU ignored while a trusted peer still confirms the region;
  - existing correct section reservation + smallest remaining SEC allocation;
  - HTML checkbox/highlight markers.

## [3.5.1] - 2026-08-13

### Composite feeder title recognition fix
- Fixed a critical v3.5.0 design issue where a G feeder title had to be
  uniquely resolved in Oracle BEFORE it could become a spatial feeder anchor.
- G XML is now authoritative for feeder-title spatial detection:
  - `<Text ts="ABH-03">` and similar engineering titles are extracted first;
  - composite regions are built from the G titles even when the initial DB
    title lookup returns zero or multiple rows;
  - Oracle resolution now confirms the title after the region is established.
- This prevents a large merged drawing from incorrectly collapsing to:
  `AMBIGUOUS / 识别馈线区域=1`.

### Feeder title cleanup
- Added canonical feeder token extraction:
  - `ABH-03` -> `ABH-03`
  - `AJWD_07` -> `AJWD-07`
  - `BAY NO + ABH-17` -> `ABH-17`
- Clean standalone feeder titles have higher priority than nearby descriptive
  `BAY NO ...` annotations.
- A nearby low-quality annotation for the same feeder no longer creates an
  extra region.
- Two genuinely separate clean titles with the same feeder name are preserved
  and flagged as duplicate composite anchors instead of being silently merged.

### Existing-model reverse confirmation
- When G-title -> Oracle feeder-name lookup cannot uniquely resolve a region,
  the validator now uses existing linked FeedLine models as a second source:
  `KeyID -> dms_section_device -> feeder_id -> dms_feeder_device`.
- The fallback is accepted only when all resolvable linked FeedLines in the
  region point to one feeder and that feeder name is compatible with the G
  title.
- If linked FeedLines in one spatial region resolve to multiple feeder IDs,
  the region is reported as inconsistent and is not auto-associated.

### Feeder database display-name consistency
- `get_feeder_info()` now returns the same
  `station.name + feeder.name` display name used by
  `find_feeders_by_name_hint()`.
- This makes reverse KeyID ownership checks compatible with titles such as
  `ABH-03` versus database display names such as `JED NTH ABH 03`.

### Diagnostics
- Feeder validation console now logs:
  - raw G title candidate count;
  - cleaned G anchor count;
  - database-uniquely-resolved anchor count;
  - the actual cleaned G feeder-title list.

### Actual uploaded ABH composite regression
- The uploaded `JED-NTH-ABH.sln.pic.g` structure was inspected directly.
- Its XML contains 398 FeedLine objects and clean top feeder titles including
  ABH-03 through ABH-49.
- The corrected detector identifies 47 clean title anchors in this source
  layout instead of one unresolved region.
- The source drawing contains two clean `ABH-26` titles and no clean `ABH-27`
  title; both ABH-26 anchors are intentionally retained and reported as a
  duplicate-title data issue.

## [3.5.0] - 2026-08-13

### Feeder composite-drawing support
- Feeder model now supports three drawing modes in the desktop UI:
  - `AUTO` / 自动识别（推荐）;
  - `SINGLE` / 单馈线图;
  - `MULTI` / 多馈线组合图.
- AUTO mode detects a multi-feeder composite when two or more feeder-name anchors above/near Bus objects are uniquely confirmed by the Oracle feeder master data.
- Single-feeder behavior remains backward-compatible: Bus-near text first, then filename fallback.

### Multi-feeder recognition
- Long horizontal Bus objects no longer contribute only one nearest Text. All plausible engineering labels immediately above the Bus span are retained as feeder-name candidates.
- A top-band feeder-title scan is also used so feeder titles placed in the intentional gap between two Bus segments are not missed.
- Candidate labels are confirmed against `dms_feeder_device`; device numbers and common labels such as SMART/Q1/Y1/BUS are not accepted as feeder anchors.
- Feeder names continue to use punctuation-insensitive normalized matching, e.g. `ABH-06` -> `ABH06` and can match database display names such as `JED NTH ABH 06`.

### FeedLine region assignment
- Confirmed feeder anchors are sorted by X coordinate.
- Composite drawings are partitioned into feeder regions using the midpoint between adjacent anchors.
- Each `<FeedLine>` is assigned to the corresponding spatial feeder region before database validation.
- Every feeder region independently performs the existing section validation and assignment logic:
  - validate existing KeyID/table/domain/owner feeder;
  - reserve correctly/currently referenced database sections;
  - order unlinked FeedLine elements top-to-bottom then left-to-right;
  - allocate remaining `dms_section_device` rows in natural SEC sequence.
- Existing links are therefore checked against the feeder region in which the FeedLine is actually drawn.

### Topology consistency guard
- Added a lightweight endpoint-connectivity guard for FeedLine/ConnectLine geometry.
- Topology is deliberately secondary to spatial regions: future drawings may intentionally connect two feeder regions, so a cross-region connection is reported and never used to merge two feeders automatically.
- Feeder section reports expose topology component/cross-region metadata for troubleshooting.

### Safety / ambiguous composite handling
- If the same database feeder is detected at multiple independent composite anchors, both affected regions are blocked from automatic section allocation to prevent reusing the same database section sequence twice.
- If the user explicitly chooses MULTI mode but fewer than two uniquely confirmed feeder anchors can be found, the file is marked `AMBIGUOUS` and automatic association is blocked.
- Original G files remain unchanged; all write-back continues to target Workspace safety copies.

### Reports
- Feeder summary now includes drawing type, feeder-region sequence, and FeedLine assignment method.
- FeedLine detail now includes drawing type, region sequence, spatial/topology assignment information, and cross-region connectivity flags.

### Database fix
- Fixed `OracleClient.get_feeder_info()` so feeder master table 13500 is correctly resolved instead of referencing an undefined local variable.

### Validation
- Added regression coverage for automatic multi-feeder detection, spatial FeedLine partitioning, independent per-feeder section allocation, and duplicate feeder-anchor blocking.
- No smoke test added.

## [3.4.0] - 2026-08-13

### RMU execution performance
- Split RMU workflow into two explicit phases:
  - full model validation = full G/RMU/device analysis;
  - execute association = selected-device-only processing.
- Clicking `执行模型关联` no longer reruns full RMU validation for the whole G file.
- Execution only re-checks database facts for RMUs/devices explicitly selected in the in-app table.
- RMU queries and per-table device inventory queries are cached during one execution, so multiple selected devices in the same RMU do not repeat the same database query.
- G objects are written directly by `(tag + XML ID)`; the execution phase does not rediscover frames, labels or unrelated devices.

### Database refresh at execution time
- Selected devices receive a lightweight current-database re-check immediately before write-back:
  - RMU name is still unique;
  - CODE still uniquely matches the logical p_NameString inside that RMU;
  - device still belongs to that RMU;
  - BV_ID is present;
  - Expected KeyID still verifies against table/domain.
- If a previously validated device was deleted/re-created and its ID/BV_ID changed, execution refreshes the current ID/BV_ID/Expected KeyID and writes the new values.
- If database truth becomes ambiguous after validation, only that selected device is skipped; other selected valid devices continue.

### Operation-scoped report
- RMU association completion no longer generates another full validation report.
- The association report contains only RMUs and devices selected for this execution.
- RMU summary shows only selected RMUs.
- Device details show only selected devices and their execution result.
- Successful rows use `ASSOCIATION_WRITE_SUCCESS`.
- Devices skipped because database facts changed at execution time are reported as FAIL in this operation report only.
- The HTML title is now `RMU 模型关联执行报告` for operation-scoped RMU reports.

### Console
- Removed the post-write full-G validation loop and its many `无需关联` messages.
- Execution logs now focus on:
  - number of selected RMUs/devices;
  - selected RMU database re-check;
  - database target changes;
  - safety-copy write-back;
  - success / skip totals.

### Unchanged
- Original G files remain unchanged.
- Workspace safety-copy behavior is unchanged.
- RMU database-truth eligibility rules are unchanged.
- BV_ID -> voltype is unchanged.
- Feeder workflow remains unchanged.
- No smoke test added.

## [3.3.2] - 2026-08-13

### RMU selection table UI
- Kept the RMU-name live filter introduced in v3.3.1.
- Forced every row in the in-app selectable device-detail table to the same height: 38 px.
- Disabled cell word-wrapping in this table so long descriptions no longer expand individual rows.
- Long cell content is elided with `...`; the complete text remains available in the existing tooltip.
- The vertical header uses fixed section resize mode to prevent Qt from recalculating different row heights.

### Unchanged
- RMU validation and selective association logic are unchanged.
- Filtering remains display-only and never changes checkbox state or eligibility.
- Feeder behavior is unchanged.
- No smoke test added.

## [3.3.1] - 2026-08-13

### RMU selection table
- Added a fast RMU-name filter above the in-app selectable device-detail table.
- Supports partial matching such as `17613`, `RMU-42646`, or other RMU name fragments.
- Filtering is live while typing.
- Added a clear-button and a dedicated `清除筛选` action.
- The selection counter shows the number of currently visible rows when a filter is active.

### Safety
- Filtering is display-only.
- Hidden rows keep their checkbox state.
- Filtering never changes validation results, association eligibility, selected candidate keys, or write-back behavior.
- Clearing the filter restores all device rows.

### Unchanged
- Database-truth association rules remain unchanged from v3.3.0.
- Selective RMU association behavior is unchanged.
- Feeder behavior is unchanged.
- No smoke test added.

## [3.3.0] - 2026-08-12

### RMU selective association UI
- RMU model validation now also builds a read-only in-memory association candidate set; it still does not modify any G file.
- Added an in-app `可关联设备选择（模型校验结果）` table immediately below task progress.
- The table shows G-file RMU device detail rows with:
  - G file;
  - RMU sequence and name;
  - G object type;
  - logical p_NameString / selected device name;
  - current database CODE;
  - PASS / UNLINKED / RELINK / RMU_RELINK / FAIL / BLOCKED status;
  - current model state;
  - current target database device ID;
  - Expected KeyID;
  - processing reason.
- Only rows already validated as:
  `association_ready=YES` and `writeback_needed=YES`
  are checkable.
- PASS, FAIL and BLOCKED rows cannot accidentally be selected for write-back.
- Nothing is selected by default. The user must explicitly choose one or more devices.
- Added `全选可关联` and `清空选择`.

### Selective write-back
- `执行模型关联` now processes only explicitly checked RMU device rows.
- Users can select:
  - one device;
  - multiple devices in one RMU;
  - devices across multiple RMUs / G files.
- Only G files containing checked devices are copied into the current Workspace `g_output`.
- The final validation report is generated from those processed safety-copy G files.
- Device eligibility is never re-decided by the checkbox UI; the RMU validator remains the only authority.

### Database-truth rule retained
- Current database truth remains authoritative.
- A unique RMU + unique CODE/p_NameString match + correct RMU ownership + valid Expected KeyID/BV_ID is selectable.
- Old wrong KeyID/domain/device ID or an old cross-RMU link remains correctable through RELINK / RMU_RELINK.
- Database ambiguity remains a hard blocker.

### Unchanged
- Original G files are never modified.
- BV_ID -> voltype write-back is unchanged.
- Feeder module behavior is unchanged.
- No smoke test was added.

## [3.2.0] - 2026-08-12

### RMU association strategy
- Changed RMU association authority from the old G KeyID to the CURRENT database truth.
- A device is association-eligible when:
  - RMU name resolves to exactly one database RMU;
  - the G logical `p_NameString` / selected name uniquely matches one CODE inside that RMU;
  - CODE equals the logical `p_NameString`;
  - the matched current database device belongs to the same RMU;
  - Expected KeyID is valid;
  - BV_ID is available when write-back is needed.
- Device-level failures remain isolated: one missing/duplicate CODE does not block other valid devices in the same unique RMU.

### Correctable model states
- Added `RELINK` (orange):
  - old device ID changed;
  - old device record was deleted and recreated;
  - current KeyID is stale or unresolvable;
  - current table/domain is wrong;
  - current KeyID differs from the new Expected KeyID.
  These cases are no longer red FAIL when the current database target is uniquely valid.
- Added `RMU_RELINK` (purple):
  - the existing G KeyID currently points to another RMU;
  - the current unique RMU still contains one valid CODE/p_NameString target.
  The tool may overwrite the old association and link to the correct current RMU.
- Existing correct models remain green PASS.
- Unlinked but valid devices remain yellow WARN.

### Device recreation / ID changes
- If a previously linked database device was deleted and recreated with a new ID,
  the old G KeyID no longer blocks association.
- The current RMU + CODE/p_NameString match is resolved again and a new Expected KeyID,
  BV_ID/voltype and model attributes are written to the Workspace copy.

### HTML report usability
- Added a left-side selection checkbox to RMU summary and device detail rows.
- Checking a row keeps the whole row outlined in blue while horizontally scrolling,
  reducing the chance of reading the wrong KeyID/Domain/BV_ID/description row.
- Updated status legend for PASS / UNLINKED / RELINK / RMU_RELINK / BLOCKED / FAIL.

### Unchanged hard blockers
- RMU database name has 0 or multiple records.
- Current-RMU CODE match has 0 or multiple records.
- CODE does not equal the logical p_NameString.
- The current target database device does not belong to the current RMU.
- Expected KeyID validation fails.
- Required BV_ID is missing for write-back.
- RMU feeder information remains completely excluded from RMU validation.

## [3.1.4] - 2026-08-12

### Fixed
- Fixed application startup failure:
  `AttributeError: 'MainWindow' object has no attribute 'show_current_module_help'`.
- `_current_module_help_html()` and `show_current_module_help()` are now proper
  `MainWindow` class methods instead of accidentally nested local functions
  inside `_update_module_stack_height()`.
- No RMU, Feeder, database, KeyID, BV_ID, report, or write-back business logic
  was changed.

## [3.1.3] - 2026-08-12

### Feeder UI
- Feeder Table/Domain spin controls now use exactly the same dark-green up/down button style as the RMU module.
- Removed the user-editable feeder master table row from the Feeder settings page.
- The Feeder settings page now exposes only:
  - `13503 / dms_section_device`
  - Domain `1`
- The internal feeder master table remains fixed at `13500` and is no longer a user-facing setting.

### Workspace module help
- Added a dedicated `当前模型帮助` button directly in the Model Workspace task area.
- The help content changes automatically with the selected model type.
- Feeder identification rules and FeedLine association rules were removed from the main Feeder settings page and moved into Feeder model help.
- Added dedicated RMU model help in the same Model Workspace button.
- Help is displayed in a separate scrollable dialog so it does not consume normal workspace configuration height.

### Unchanged
- RMU validation and association business rules are unchanged.
- Feeder validation and association business rules are unchanged.
- BV_ID -> voltype write-back remains unchanged from v3.1.2.
- Original G files remain unchanged; write-back continues only on Workspace safety copies.

## [3.1.2] - 2026-08-12

### Model write-back
- RMU `CBreakerDis`, `ZhaiWaiJieDiDaoZha`, and `BusDis` now write `voltype` from the matched database device `BV_ID`.
- FeedLine now writes `voltype` from `dms_section_device.BV_ID`.
- Removed the old RMU write-back constant `voltype=0`.
- FeedLine section queries now include `BV_ID`.
- FeedLine detail reports now show current and target `BV_ID`.
- Association preview messages show the exact `voltype` that will be written.

### Safety
- An unlinked RMU device with an empty database `BV_ID` is blocked only for that device.
- An unlinked FeedLine with an empty database `BV_ID` is blocked only for that FeedLine.
- No new automatic model association is allowed to write an empty or zero-placeholder `voltype`.

### Unchanged
- KeyID calculation rules are unchanged.
- RMU and feeder ownership validation rules are unchanged.
- Original G files remain unchanged; write-back still operates only on Workspace safety copies.

## [3.1.1] - 2026-08-11

### UI
- Fixed RMU / Feeder module switching geometry.
- Feeder settings now use the same expanding width policy as RMU settings.
- Feeder configuration changed to a full-width two-column layout:
  feeder recognition rules on the left and database table/domain settings on the right.
- FeedLine association rules now span the full configuration width below the two columns.
- Module switching now releases the previous page's fixed height before changing the stacked page.
- The newly selected module is re-laid out using the actual workspace width before calculating its natural height.
- Only the outer workspace scroll area remains responsible for page scrolling; no local module scrollbar is introduced.

### Unchanged
- RMU validation/association business rules are unchanged.
- Feeder validation/association business rules are unchanged.
- Original G files remain read-only and all write-back continues to target Workspace safety copies.

## [3.1.0] - 2026-08-11

### Added
- Enabled the independent Feeder Model module.
- Added single-feeder name resolution from nearest Text around `<Bus>`, with filename fallback.
- Added punctuation-insensitive feeder name containment lookup against `dms_feeder_device` (13500).
- Added `<FeedLine>` model validation.
- Added `dms_section_device` (13503) / Domain 1 Expected KeyID generation and Oracle verification.
- Added validation for existing FeedLine KeyIDs and actual feeder ownership.
- Added automatic assignment for unlinked FeedLines using remaining database section records.
- Added top-to-bottom / left-to-right ordering for unlinked G FeedLine objects.
- Added natural database section ordering using SEC001, SEC002, SEC003...
- Added safe FeedLine write-back to Workspace copies only:
  `app=6500000`, `p_ReportType=1`, `state=20`, `keyid=Expected KeyID`.
- Added dedicated Feeder Summary and FeedLine Detail HTML/CSV reports.

### Safety
- Existing wrong FeedLine links are reported but are not silently overwritten.
- Existing correctly linked database sections are reserved before assigning unlinked FeedLines.
- Original G files remain unchanged.

### RMU
- RMU module continues to perform zero feeder validation. The new feeder logic exists only in the independent Feeder Model module.

## [3.0.27] - 2026-08-10

### Association
- Device-level failures no longer set the whole unique RMU to association-ineligible.
- Missing/duplicate CODE blocks only the affected G element.
- CODE/p_NameString mismatch blocks only the affected G element.
- Wrong RMU ownership or wrong existing KeyID blocks only the affected G element when the RMU itself is unique.
- Other valid devices in the same RMU remain eligible for write-back.
- RMU NAME 0/multiple remains a whole-RMU blocker.

### Reporting
- Added separate RMU-level and device-level blocker columns.
- Unique RMUs with partial device errors are reported as WARN while remaining association-eligible.

### Unchanged
- No feeder validation.
- BusDis remains Table ID 13506 / Domain 1.

## [3.0.26] - 2026-08-10

### Validation
- Made database-device RMU ownership an explicit hard rule instead of relying only on `combined_id`-scoped queries.
- Added one-to-one validation for logical `p_NameString` values inside each G-file RMU.
- Added one-to-one validation so one database device ID cannot be consumed by multiple G elements.
- Missing CODE remains a hard FAIL for the corresponding G element and blocks automatic association.
- Duplicate CODE remains a hard FAIL.
- For non-unique RMU names with existing manual KeyIDs, CODE uniqueness is now re-queried inside the actual owner RMU before accepting the manual link.
- Existing manual links across multiple same-name `combined_id` values remain a hard `RMU_LINK` error.
- Existing manual links to another RMU NAME remain a hard `RMU_LINK` error.

### Unchanged
- Unrelated extra database devices are ignored.
- No feeder validation is performed.
- BusDis remains Table ID `13506`, Domain `1`.

## [3.0.25] - 2026-08-10

### Reporting
- Removed RMU-summary columns `CODE`, `GRAPH_NAME`, `COMBINED_TYPE`, and `RUN_STATE` from HTML and CSV.

### Validation
- Added cross-device consistency validation for existing manual KeyIDs when an RMU NAME is not unique.
- Existing linked devices inside one G-file RMU must all resolve to the same actual `combined_id`.
- Multiple same-name RMU IDs used by devices inside one G RMU are now a hard `RMU_LINK` error.
- Existing KeyID resolving to another RMU NAME remains a hard `RMU_LINK` error.
- RMU NAME uniqueness, device CODE uniqueness, CODE/p_NameString equality, Expected KeyID, and actual RMU ownership remain the core checks.

### Removed
- No feeder validation or feeder reporting is reintroduced.

## [3.0.24] - 2026-08-10

### Changed
- Removed all feeder-based validation from the RMU module.
- G filename feeder hints are no longer parsed or used.
- RMU `feeder_id` is no longer resolved through `dms_feeder_device`.
- Device `feeder_id` is no longer queried or compared.
- Removed `FEEDER` / `FEEDER_MISMATCH` from RMU validation and HTML status legend.
- Removed feeder-related columns from RMU summary and device-detail reports.

### Validation
- RMU association now depends only on RMU uniqueness, CODE uniqueness,
  logical p_NameString/CODE equality, Expected KeyID correctness, and existing
  model RMU ownership.
- Existing KeyID pointing to another RMU remains a hard `RMU_LINK` error.

### Unchanged
- BusDis remains Table ID `13506`, Domain `1`.
- Original G files remain unchanged; association writes only Workspace copies.

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
