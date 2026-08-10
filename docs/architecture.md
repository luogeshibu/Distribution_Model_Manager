# Architecture

The project follows a layered `src/` package layout.

```text
src/dmm/
├─ application/
│  ├─ job_worker.py
│  ├─ registry.py
│  └─ modules/
│     ├─ base.py
│     ├─ rmu.py
│     └─ feeder.py
│
├─ config/
│  ├─ constants.py
│  ├─ defaults.py
│  └─ settings.py
│
├─ domain/
│  ├─ gfile/
│  │  └─ parser.py
│  └─ rmu/
│     └─ validator.py
│
├─ infrastructure/
│  ├─ database/
│  │  └─ oracle.py
│  ├─ filesystem/
│  │  └─ workspace.py
│  ├─ gfile/
│  │  └─ writeback.py
│  └─ reporting/
│     └─ writer.py
│
├─ ui/
│  ├─ main_window.py
│  ├─ registry.py
│  └─ widgets/
│     ├─ rmu_settings.py
│     └─ feeder_settings.py
│
└─ resources/
   ├─ app_logo.ico
   ├─ app_logo.png
   ├─ spin_up.png
   └─ spin_down.png
```

## Responsibilities

- `ui`: PySide6-only presentation and user-input collection.
- `application`: use-case orchestration; no widget creation and no UI imports.
- `domain`: G-file/RMU recognition and validation rules.
- `infrastructure`: Oracle access, report output, workspace lifecycle, and G-file safe write-back.
- `config`: app identity, algorithm constants, defaults, and runtime settings persistence.
- `resources`: static icons bundled with the application.

## Dependency rule

Core processing does not import PySide6 widgets.

```text
UI ────────> Application ────────> Domain
 │                 │                 │
 │                 └──────> Infrastructure
 └────────────────────────> Config
```

`workspace/` is runtime-only and is never source-controlled.
