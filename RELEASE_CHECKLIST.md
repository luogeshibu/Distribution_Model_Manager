## v4.2.23 Full G-file before/after rendering

- [x] Before SVG is rendered from the untouched original G, not a simplified topology model.
- [x] After SVG is rendered from the repaired complete G.
- [x] Text/DText, line geometry, RMU frames, visible poke boxes, status icons, switch/ground/protection symbols, NOP images and drawing-frame content are retained.
- [x] Problem positions remain visible on the before view with numbered red/orange overlays.
- [x] Repaired positions remain visible on the after view with green overlays and repaired-line highlighting.
- [x] Source G metadata is available on SVG object hover.
- [x] Connectivity logic remains feeder/NOP/Bus/database independent.
- [x] Focused v4.2.23 renderer/repair tests pass.

## v4.2.22 Jeddah batch topology visual reports

- [x] Multi-G directory/SSH input processes each G independently.
- [x] Every successful G produces its own HTML/CSV report.
- [x] Every successful G produces a before-topology SVG and after-topology SVG.
- [x] Before topology view visibly marks every detected problem position with a numbered red/orange marker.
- [x] After topology view marks repaired positions green and review-only positions orange.
- [x] Per-file HTML embeds both topology views with zoom/full-screen controls.
- [x] Batch total HTML contains links to per-file report, before/problem topology, after topology, and repaired G.
- [x] One failed G does not abort the rest of a batch.
- [x] Jeddah remains connectivity-only: no feeder/NOP/Bus/database logic.
- [x] Focused v4.2.22 tests pass.

## v4.2.20 Jeddah batch topology continuity repair

- [x] Directory/SSH input can contain multiple G files; no single-file-only ValueError.
- [x] Every G is processed independently with its own HTML/CSV and optional topology-fixed G output.
- [x] Batch run generates a total HTML/CSV summary with links to each per-file report/output.
- [x] One failed G is recorded and skipped without stopping later files.
- [x] Overall progress is monotonic across all files.
- [x] Single-file mode retains the compact v4.2.19 output layout and report names.
- [x] Connectivity rules remain unchanged: no feeder/NOP/Bus/database analysis.
- [ ] Run focused v4.2.20 tests and full regression suite before field release.
