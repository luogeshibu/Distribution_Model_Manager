# Jeddah v4.2.3 Graphics Integration

## Locked baselines

- Model association: `Distribution_Model_Manager-v4.1.111`
- Graphics processing: `GFileStudio-v2.18.257`
- Integration/UI reference only: `Distribution_Model_Manager-jazan-v4.1.131`

Jazan site-specific model/database rules are not copied into the Jeddah model modules.

## Application layout

The DMM main window owns the application. `GraphicsWorkspaceWidget` is a first-level page and lazy-loads the existing GFileStudio business pages inside the same Qt process. This avoids launching a second EXE or nesting another QMainWindow.

## Safety boundaries

1. DMM model write-back continues to use the existing Workspace safe-copy flow.
2. Embedded GFileStudio modules keep their original source-file safety rules and managed run folders.
3. Startup is local-only; a graphics page is constructed only when selected.
4. DMM settings are projected locally into GFileStudio settings without making a connection.
5. Existing standalone GFileStudio AppData is intentionally reused so ID rules, any previously cached symbol files and operator preferences survive the merge.
6. Main DMM `图元管理` is the only visible symbol-management workflow. Its saved element catalog is locally projected into the graphics cache; Graphics Workspace no longer exposes a second server-symbol-sync page.
7. The projection is local-only and does not open SSH. Server symbol files remain read-only.

## Graphics modules included

- Small-element cleanup
- ID check/repair
- RMU processing
- Poke processing
- Basic processing
- Feeder G merge
- Margin adjustment
- Drawing frame
- Orthogonalization
- Jeddah feeder batch
- Transformer-OH + fuse replacement
- RMU EFI protection symbol addition

## Build

`build_exe.ps1` now packages both `dmm` and `g_file_studio` and includes the GFileStudio `resources` directory.


## v4.2.3 central configuration convergence

The merged application uses one DMM central repository for Admin ownership and embedded graphics central actions. `id_rules.json` is stored beside DMM `instance.json`, `database.json`, `file_server.json`, and `element_marks.json`. Main Element Management remains the only visible symbol/classification manager; graphics consumes its locally bridged catalog.
