from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    log = Signal(str)
    progress = Signal(int)
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class FunctionWorker(QRunnable):
    def __init__(self, function: Callable[..., Any]) -> None:
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function(
                log=self.signals.log.emit,
                progress=self.signals.progress.emit,
            )
            self.signals.result.emit(result)
        except Exception as exc:
            details = traceback.format_exc()
            self.signals.error.emit(f"{exc}\n\n---TRACEBACK---\n{details}")
        finally:
            self.signals.finished.emit()
