# v4.2.23 - Full G-file report rendering

- Replaced the simplified line-only/abstract topology SVG with a full G-file redraw for both before and after reports.
- The renderer now preserves the source G canvas and object placement and renders line geometry, Text/DText, RMU rectangles, visible poke blocks, status icons, switch/ground/protection symbols, NOP image placeholders, transformer/PT/capacitor symbols and drawing-frame content.
- The before report is rendered from the untouched original in-memory XML before any repair. Problem markers are then overlaid directly at detected break coordinates.
- The after report is rendered from the repaired in-memory G and highlights repaired line objects and repaired locations in green.
- Each rendered SVG object contains source metadata in a tooltip so the report can be traced back to G element id/name/devref/key_name/link/node_area.
- External *.icn.g symbol internals are not embedded in business G files; those icons therefore use deterministic vector surrogates inside their exact source bounding box and rotation instead of inventing topology placement.
- Jeddah connectivity decisions remain unchanged and still do not use feeder/NOP/Bus/database logic.
- Added focused regression coverage that verifies non-line G content survives in both before and after diagrams.

# v4.2.21 - Batch reports + before/after topology problem visualization

- Kept v4.2.20 multi-G processing: each G produces an independent report and batch runs produce one total HTML/CSV summary.
- Added `jeddah_topology_before.svg` and `jeddah_topology_after.svg` for every successfully processed G.
- The before SVG directly marks detected break positions with numbered red (auto-fix) or orange (review-only) markers; numbers match the per-file detail table.
- The after SVG shows repaired positions in green and review-only positions in orange.
- Per-file HTML embeds both topology views with zoom, Ctrl+wheel zoom, scroll, and full-screen controls.
- Batch summary adds direct links to each before/problem-position topology view and after topology view.
- Diagram generation reuses lightweight geometry snapshots from the existing parse; there is no feeder/NOP/Bus-name/database work.

# v4.2.20 - Jeddah batch topology continuity reports

- Whole-graph topology connection check/repair now supports multiple G files from a local directory or SSH snapshot.
- Each G file is processed independently and receives its own HTML/CSV report and safe topology-fixed G copy when repairs are made.
- Batch runs additionally generate `jeddah_topology_batch_summary.html` and `.csv` with per-file status, counts, repair totals, timing, report links, and fixed-G links.
- A malformed/failed G file no longer aborts the remaining batch; it is recorded as FAILED in the summary and processing continues.
- Batch progress is mapped across all files so the UI progresses monotonically from 0 to 100 instead of restarting per file.
- Jeddah topology rules remain connectivity-only: no feeder ownership, NOP recognition, Bus feeder-name lookup, or database access.

# v4.2.19 - Jeddah topology continuity check / repair

- Replaced the Jeddah Graphics Workspace whole-graph feeder-ownership workflow with a **pure G-file topology continuity** workflow. This page no longer identifies feeder ownership, NOP, Bus feeder names, or queries Oracle/model databases.
- Added fast local endpoint indexing for ConnectLine/FeedLine continuity checking; the large feeder-propagation/RMU/NOP/SVG report pipeline is no longer executed from the Jeddah page.
- Auto-repairs unique ConnectLine↔FeedLine local breaks up to 25G by orthogonally extending FeedLine and adding reciprocal `link` / `node_area` references.
- Also repairs only tiny (≤3G), collinear ConnectLine↔ConnectLine splits. Larger ConnectLine gaps are intentionally ignored so normal open-switch/symbol contact gaps (commonly ~18G) are never bridged.
- Source G is never overwritten. Output is a validated `*.topology-fixed.sln.pic.g` plus compact HTML/CSV repair details.
- Retains the v4.2.19 spatial-index performance improvements in the legacy Makkah-derived topology helpers for compatibility/regression coverage.

# v4.2.18 - Jeddah whole-graph feeder topology

- Added `整图馈线拓扑分析` under Graphics Workspace.
- Copied the Makkah whole-graph topology engine and its graph/NOP/RMU/safe-repair dependencies into an isolated graphics-cleanup package so existing Jeddah model-association rules remain untouched.
- Added Jeddah no-frame main-network source recognition: `Bus` + unique feeder name directly above it.
- Added Jeddah NOP visual recognition for white `N.O.P` Text inside a red ellipse/background while retaining Makkah red-text NOP recognition.
- Source G remains read-only; output is HTML/CSV/SVG plus an optional validated `*.topology-fixed.sln.pic.g` safety copy.

# v4.2.17 - Remove Jeddah batch FeedLine solid-style step

- Removed the former fixed Jeddah graphics-batch step that changed every `<FeedLine>` to `ls=1`.
- Jeddah graphics batch now preserves each FeedLine `ls` value exactly as supplied by the input G file.
- Removed the step from UI workflow text, help, runtime logs, reports, counters, and English translation paths; later workflow steps were renumbered.
- Standalone line-style/basic-processing capabilities are unchanged.

# v4.2.16 - Jeddah graphics batch large-run performance

- Optimized only **Graphics Workspace → Jeddah Graphics Batch Processing**; standalone graphics processors and DMM model-association modules keep their existing business rules.
- Added an isolated buffered task/log panel for Jeddah batch runs so thousands of per-file worker messages no longer trigger a full QText/i18n rebuild for every line.
- Reused authoritative RMU identification inside one unchanged XML state: pre-SMR and post-SMR recognition are each computed once and shared with the Jeddah SMART/NORMAL audits, channel-status cleanup, duplicate-SMART cleanup and profile application.
- Combined the RMU cabinet-name standardization pass with the following Jeddah visual pass in memory, removing one complete parse/write/read round-trip per G file.
- Intermediate Jeddah stage files are written atomically without redundant pretty-indent + immediate self-parse; the next processing stage remains the validation parse boundary.
- Margin adjustment skips the redundant full ID normalization pass because the preceding dedicated ID stage has just normalized the files and margin movement creates no new IDs. Drawing-frame addition still performs normal ID enforcement after adding template elements.
- Added per-stage and total elapsed-time statistics to help diagnose large site batches.
- Added v4.2.16 regression tests for in-memory name-standard equivalence, cached RMU-identification reuse, isolated high-volume logging and redundant-ID-pass prevention.

# v4.2.15 - Multi-model batch stability and responsiveness

- Optimized only the **Multi-Model Association** orchestration path; independent RMU / Pole Switch / Pole Transformer / Fuse / Master Station / Feeder module business rules are unchanged.
- Moved batch SSH stable-snapshot download, SHA256 calculation, final stat sweep and redownload checks off the Qt GUI thread into the batch validation worker.
- Moved post-confirmation validation-bundle filtering/deep-copy work off the GUI thread into the batch association worker.
- Batched batch-worker log signals to reduce Qt event-queue pressure on very large jobs.
- Optimized the batch candidate confirmation table by disabling sorting, signals and repainting during bulk population.
- Fixed cumulative path rebasing for report-driven modules: `reports[*].g_file` now follows the cumulative stage file. This specifically prevents the final Feeder stage from losing its topology-region report lookup after earlier modules have already produced cumulative G copies.
- Added visible per-file progress while publishing final cumulative safe G copies.
- Added regression coverage for cumulative report path rebasing, background SSH preparation, background candidate filtering, and final publish progress.

## Safety invariant

All individual model modules still use their existing validation, Oracle recheck and `apply_association` implementations. v4.2.15 changes only the batch scheduler / cumulative-path plumbing / UI responsiveness around those modules.
