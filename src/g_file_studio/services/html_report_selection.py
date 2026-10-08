from __future__ import annotations

from g_file_studio.services.report_i18n import report_is_english


def selection_style() -> str:
    """Shared HTML report styles for row selection used only for visual review."""
    return (
        ".report-select-col{width:46px;min-width:46px;text-align:center!important;position:sticky;left:0;z-index:3;}"
        "th.report-select-col{background:#dce9e4!important;}"
        "td.report-select-col{background:inherit;}"
        ".report-select{width:17px;height:17px;cursor:pointer;vertical-align:middle;}"
        "tr.report-row-selected td{outline:2px solid rgba(37,99,235,.35);outline-offset:-2px;}"
        "tr.report-row-selected td:not(.report-select-col){box-shadow:inset 0 0 0 9999px rgba(59,130,246,.10);}"
        ".report-selection-bar{display:flex;align-items:center;gap:12px;margin:10px 0;color:#475569;font-size:13px;}"
        ".report-selection-count{font-weight:600;color:#1d4ed8;}"
    )


def selection_bar() -> str:
    if report_is_english():
        help_text = "Review aid: select one or multiple rows; selected rows are highlighted."
        count_text = "Selected 0 rows"
    else:
        help_text = "查看辅助：可单选/多选行，勾选后整行高亮。"
        count_text = "已选择 0 行"
    return (
        '<div class="report-selection-bar">'
        f'<span>{help_text}</span>'
        f'<span class="report-selection-count" id="reportSelectionCount">{count_text}</span>'
        '</div>'
    )


def selection_header() -> str:
    title = "Select/Clear All" if report_is_english() else "全选/取消全选"
    aria = "Select all" if report_is_english() else "全选"
    return (
        f'<th class="report-select-col" title="{title}">'
        f'<input id="reportSelectAll" class="report-select" type="checkbox" aria-label="{aria}">'
        '</th>'
    )


def selection_cell() -> str:
    aria = "Select this row" if report_is_english() else "选择此行"
    return (
        '<td class="report-select-col">'
        f'<input class="report-select report-row-select" type="checkbox" aria-label="{aria}">'
        '</td>'
    )


def selection_script() -> str:
    label_expr = "'Selected '+checked+' rows'" if report_is_english() else "'已选择 '+checked+' 行'"
    return rf'''<script>
(function(){{
  function updateCount(){{
    var checked=document.querySelectorAll('.report-row-select:checked').length;
    var label=document.getElementById('reportSelectionCount');
    if(label){{label.textContent={label_expr};}}
    var all=document.getElementById('reportSelectAll');
    var boxes=Array.from(document.querySelectorAll('.report-row-select'));
    if(all){{
      all.checked=boxes.length>0 && checked===boxes.length;
      all.indeterminate=checked>0 && checked<boxes.length;
    }}
  }}
  function setRowState(box){{
    var row=box.closest('tr');
    if(row){{row.classList.toggle('report-row-selected', box.checked);}}
  }}
  document.querySelectorAll('.report-row-select').forEach(function(box){{
    box.addEventListener('change', function(){{setRowState(box);updateCount();}});
  }});
  var all=document.getElementById('reportSelectAll');
  if(all){{
    all.addEventListener('change', function(){{
      document.querySelectorAll('.report-row-select').forEach(function(box){{
        box.checked=all.checked; setRowState(box);
      }});
      updateCount();
    }});
  }}
  updateCount();
}})();
</script>'''
