from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPalette
from PySide6.QtWidgets import QAbstractItemView, QAbstractScrollArea, QHeaderView, QTableWidget


@dataclass(frozen=True)
class _DenseTableProfile:
    headers: tuple[str, ...]
    minimum_widths: tuple[int, ...]
    maximum_widths: tuple[int | None, ...]
    minimum_row_height: int = 36
    minimum_visible_rows: int | None = None


# Canonical source labels are Chinese because feature pages keep Chinese as their
# source-language strings and the i18n presentation layer translates at runtime.
_DENSE_TABLE_PROFILES: tuple[_DenseTableProfile, ...] = (
    _DenseTableProfile(
        headers=("状态", "元素类型", "ID 起始前缀", "总位数", "合法示例", "当前规则", "备注"),
        minimum_widths=(92, 150, 118, 86, 145, 260, 280),
        maximum_widths=(120, 240, 150, 100, 220, 380, 560),
        minimum_row_height=38,
        minimum_visible_rows=6,
    ),
    _DenseTableProfile(
        headers=("现场", "Profile 名称", "版本", "状态", "SMART LBS", "SMART CB", "SMART 接地刀闸", "NORMAL LBS", "NORMAL CB", "NORMAL 接地刀闸", "样本", "置信度", "Profile 状态"),
        minimum_widths=(120, 155, 76, 96, 185, 180, 220, 185, 180, 220, 68, 86, 130),
        maximum_widths=(190, 240, 90, 120, 280, 280, 320, 280, 280, 320, 82, 100, 170),
        minimum_row_height=38,
    ),
    _DenseTableProfile(
        headers=("RMU 类型", "设备角色", "标准图元", "置信度", "状态"),
        minimum_widths=(96, 150, 560, 88, 96),
        maximum_widths=(120, 190, 980, 105, 120),
        minimum_row_height=46,
    ),
    _DenseTableProfile(
        headers=("适用范围", "标准名称", "版本", "状态", "内置 RMU 标准", "自定义设备图元", "样本", "置信度", "标准状态"),
        minimum_widths=(120, 155, 76, 96, 125, 130, 68, 86, 125),
        maximum_widths=(190, 240, 90, 120, 180, 200, 82, 100, 170),
        minimum_row_height=38,
    ),
    _DenseTableProfile(
        headers=("检查范围", "设备角色", "XML 元素", "标准图元文件", "主体 ID", "w×h", "AlignCenter", "Pins", "匹配属性", "当前/旧图元匹配值", "标准来源", "状态"),
        minimum_widths=(92, 138, 168, 300, 210, 82, 112, 210, 110, 240, 96, 132),
        maximum_widths=(118, 200, 245, 430, 320, 108, 155, 360, 145, 430, 125, 190),
        minimum_row_height=40,
    ),
)


class _ResponsiveTableEventFilter(QObject):
    """Keep a table's presentation in sync with its viewport and data."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if isinstance(watched, QTableWidget):
            if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
                schedule_fit_responsive_table(watched)
        return False


def _responsive_text_width(table: QTableWidget, value: object) -> int:
    text = str(value or "")
    if not text:
        return 0
    return QFontMetrics(table.font()).horizontalAdvance(text)


def fit_responsive_table(table: QTableWidget, *, sample_rows: int = 240) -> None:
    """Fit visible table columns without hiding any field behind an ellipsis.

    A table may be wider than its viewport when it has many or long columns.  That
    is intentional: the horizontal scrollbar exposes the complete schema and
    complete values instead of shrinking columns until the fields become unreadable.
    Only a bounded sample is measured so a large remote file list cannot freeze the
    UI while calculating widths.
    """
    if _profile_for(table) is not None:
        # Known dense tables have deliberate per-column bounds and minimum row
        # heights. Keep their schema-specific policy authoritative.
        fit_known_dense_table(table)
        return
    if table.columnCount() <= 0:
        return

    header = table.horizontalHeader()
    metrics = QFontMetrics(table.font())
    widths: list[int] = []
    row_count = table.rowCount()
    sample_indexes = list(range(min(row_count, sample_rows)))
    if row_count > sample_rows:
        sample_indexes.extend(range(max(sample_rows, row_count - 12), row_count))

    for column in range(table.columnCount()):
        header_item = table.horizontalHeaderItem(column)
        header_text = header_item.text() if header_item is not None else ""
        width = max(56, metrics.horizontalAdvance(header_text) + 24)
        for row in sample_indexes:
            cell = table.item(row, column)
            if cell is not None:
                width = max(width, _responsive_text_width(table, cell.text()) + 24)
            cell_widget = table.cellWidget(row, column)
            if cell_widget is not None:
                width = max(width, cell_widget.sizeHint().width() + 12)
        # A pathological value should not make the whole page unusable.  The
        # complete value remains available through the horizontal scrollbar and
        # the normal Qt item tooltip (set by the feature page where appropriate).
        widths.append(min(width, 1200))

    viewport_width = max(0, table.viewport().width() - 4)
    total_width = sum(widths)
    if viewport_width > total_width and widths:
        extra = viewport_width - total_width
        base = extra // len(widths)
        remainder = extra % len(widths)
        widths = [width + base + (1 if index < remainder else 0) for index, width in enumerate(widths)]

    for column, width in enumerate(widths):
        table.setColumnWidth(column, width)


def schedule_fit_responsive_table(table: QTableWidget) -> None:
    """Coalesce resize/data notifications into one inexpensive table relayout."""
    if not table or table.columnCount() <= 0:
        return
    if bool(table.property("_responsive_table_fit_pending")):
        return
    table.setProperty("_responsive_table_fit_pending", True)

    def _fit() -> None:
        if not table:
            table.setProperty("_responsive_table_fit_pending", False)
            return
        table.setProperty("_responsive_table_fit_pending", False)
        fit_responsive_table(table)

    QTimer.singleShot(0, _fit)


GRAPHICS_TABLE_SELECTION_QSS = (
    "QTableWidget { selection-background-color:#DDF4EB; selection-color:#123B32; }"
    "QTableWidget::item:selected, QTableView::item:selected { background:#DDF4EB; color:#123B32; "
    "border-top:1px solid #79BBA5; border-bottom:1px solid #79BBA5; }"
    "QTableWidget::item:selected:!active, QTableView::item:selected:!active { "
    "background:#E8F7F2; color:#123B32; }"
)


def apply_graphics_table_selection_style(table: QTableWidget) -> None:
    """Use one readable light-mint selection style across Graphics Workspace.

    The merged DMM runs with the Windows native style, and top-level dialogs can
    otherwise repaint selected cells with the native dark-blue Highlight palette
    even when their page already has QSS.  Set both QSS *and* the active/inactive
    QPalette roles so embedded pages, lazy dialogs and focus changes all keep the
    same pale mint selection used by the feeder-order table.  This is presentation
    only and does not change selection semantics or processing data.
    """
    palette = table.palette()
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        palette.setColor(group, QPalette.ColorRole.Highlight, QColor("#DDF4EB"))
        palette.setColor(group, QPalette.ColorRole.HighlightedText, QColor("#123B32"))
    table.setPalette(palette)

    existing = table.styleSheet().rstrip()
    if GRAPHICS_TABLE_SELECTION_QSS not in existing:
        table.setStyleSheet((existing + "\n" if existing else "") + GRAPHICS_TABLE_SELECTION_QSS)
    table.setProperty("_graphics_selection_styled", True)


def configure_responsive_table(table: QTableWidget) -> None:
    """Apply the common responsive behavior to every application table.

    This function is deliberately presentation-only. It does not change data,
    selection, editability, sorting, or any processing behavior.
    """
    apply_graphics_table_selection_style(table)
    if bool(table.property("_responsive_table_configured")):
        schedule_fit_responsive_table(table)
        return

    table.setProperty("_responsive_table_configured", True)
    table.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setTextElideMode(Qt.TextElideMode.ElideNone)
    table.setWordWrap(False)

    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    header.setSectionsMovable(False)
    header.setMinimumSectionSize(56)
    header.setTextElideMode(Qt.TextElideMode.ElideNone)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    # Keep the filter alive for the lifetime of the table. Qt does not own Python
    # QObject wrappers strongly enough for an unreferenced event filter.
    filter_object = _ResponsiveTableEventFilter(table)
    table.installEventFilter(filter_object)
    table._responsive_table_filter_object = filter_object  # type: ignore[attr-defined]

    model = table.model()
    model.rowsInserted.connect(lambda *_args: schedule_fit_responsive_table(table))
    model.dataChanged.connect(lambda *_args: schedule_fit_responsive_table(table))
    schedule_fit_responsive_table(table)


def _canonical_headers(table: QTableWidget) -> tuple[str, ...]:
    result: list[str] = []
    for column in range(table.columnCount()):
        item = table.horizontalHeaderItem(column)
        if item is None:
            result.append("")
            continue
        # The language manager stores the canonical source text in Qt.UserRole.
        source = item.data(int(Qt.ItemDataRole.UserRole))
        result.append(str(source) if source is not None else item.text())
    return tuple(result)


def _profile_for(table: QTableWidget) -> _DenseTableProfile | None:
    headers = _canonical_headers(table)
    for profile in _DENSE_TABLE_PROFILES:
        if headers == profile.headers:
            return profile
    return None


def configure_known_dense_table(table: QTableWidget) -> bool:
    """Apply readable dense-table behavior to known engineering tables.

    This is intentionally presentation-only. It does not alter table data,
    selection, editability, sorting, or any feature/business logic.
    """
    profile = _profile_for(table)
    if profile is None:
        return False

    # Keep the schema-specific bounds below, while sharing the same resize/data
    # notifications as every other table in the application.
    configure_responsive_table(table)

    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    header.setSectionsMovable(False)
    header.setMinimumSectionSize(48)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setTextElideMode(Qt.TextElideMode.ElideRight)

    # Give every dense table its own explicit left/right scrollbar.  The page-level
    # vertical scrollbar remains independent, so users do not need to drag the
    # whole page horizontally just to inspect a long devref or note.
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    table.setTextElideMode(Qt.TextElideMode.ElideRight)

    # The ID rule template is an operational reference table and three visible
    # rows are too cramped for normal use.  Reserve enough vertical room for
    # its profile-defined number of rows while keeping the table flexible: it
    # may still grow when the page has more space, and scrolling remains intact.
    if profile.minimum_visible_rows:
        header_height = max(table.horizontalHeader().sizeHint().height(), 30)
        scrollbar_height = max(table.horizontalScrollBar().sizeHint().height(), 16)
        frame_height = table.frameWidth() * 2
        viewport_margins = 6
        table.setMinimumHeight(
            header_height
            + profile.minimum_visible_rows * profile.minimum_row_height
            + scrollbar_height
            + frame_height
            + viewport_margins
        )

    fit_known_dense_table(table)
    return True


def fit_known_dense_table(table: QTableWidget) -> bool:
    profile = _profile_for(table)
    if profile is None:
        return False

    # ResizeToContents is useful for short engineering values, but long devrefs and
    # notes can become thousands of pixels wide. Fit first, then clamp each column
    # to a readable range. Users can still drag headers manually afterwards.
    table.resizeColumnsToContents()
    for column in range(table.columnCount()):
        width = table.columnWidth(column)
        if column < len(profile.minimum_widths):
            width = max(width, profile.minimum_widths[column])
        if column < len(profile.maximum_widths):
            maximum = profile.maximum_widths[column]
            if maximum is not None:
                width = min(width, maximum)
        table.setColumnWidth(column, width)

    # QTableWidget does not automatically reserve enough vertical space for a
    # cellWidget.  With the application stylesheet a QComboBox needs more height
    # than the default table row; otherwise its text/frame is visibly clipped.
    # Keep this entirely in the presentation helper so feature pages and business
    # logic remain untouched.
    for row in range(table.rowCount()):
        row_height = profile.minimum_row_height
        for column in range(table.columnCount()):
            cell_widget = table.cellWidget(row, column)
            if cell_widget is None:
                continue
            row_height = max(
                row_height,
                cell_widget.sizeHint().height() + 8,
                cell_widget.minimumSizeHint().height() + 8,
            )
        table.setRowHeight(row, row_height)
    return True


def schedule_fit_known_dense_table(table: QTableWidget) -> None:
    """Coalesce multiple cell updates into one post-update column fit."""
    if _profile_for(table) is None:
        return
    if bool(table.property("_dense_table_fit_pending")):
        return
    table.setProperty("_dense_table_fit_pending", True)

    def _fit() -> None:
        table.setProperty("_dense_table_fit_pending", False)
        fit_known_dense_table(table)

    QTimer.singleShot(0, _fit)
