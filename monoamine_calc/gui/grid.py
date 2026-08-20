"""A small reusable editable table widget built on ttk.Treeview.

tkinter has no built-in editable grid, so this implements just enough of
one for the Constants tab: double-click to edit a text/float cell via a
floating Entry, single-click to toggle a boolean cell, and per-cell
validation that tags the row pink and reports errors until fixed.

Also provides `populate_readonly_tree`, a tiny helper used by the Data and
Results tabs to show a read-only preview of a DataFrame.
"""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Callable

import pandas as pd


@dataclass
class Column:
    key: str
    header: str
    width: int = 100
    kind: str = "text"       # "text" | "float" | "bool" | "readonly"
    anchor: str = "w"


class EditableTable(ttk.Frame):
    """A grid of rows, each a dict keyed by Column.key, with inline editing."""

    INVALID_TAG = "invalid"

    def __init__(self, parent, columns: list[Column], height: int = 8,
                 on_change: Callable[[], None] | None = None):
        super().__init__(parent)
        self.columns = columns
        self.on_change = on_change
        self._values: dict[str, dict[str, Any]] = {}
        self._row_order: list[str] = []
        self._errors: dict[tuple[str, str], str] = {}
        self._editor: tk.Entry | None = None

        self.tree = ttk.Treeview(
            self, columns=[c.key for c in columns], show="headings", height=height
        )
        for c in columns:
            self.tree.heading(c.key, text=c.header)
            self.tree.column(c.key, width=c.width, anchor=c.anchor)
        self.tree.tag_configure(self.INVALID_TAG, background="#ffd6d6")

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-1>", self._on_click)

    # -- public API -----------------------------------------------------

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self._destroy_editor()
        self.tree.delete(*self.tree.get_children())
        self._values.clear()
        self._row_order.clear()
        self._errors.clear()
        for i, row in enumerate(rows):
            iid = str(i)
            self._row_order.append(iid)
            self._values[iid] = dict(row)
            values = [self._format(row.get(c.key), c.kind) for c in self.columns]
            self.tree.insert("", "end", iid=iid, values=values)

    def get_rows(self) -> list[dict[str, Any]]:
        return [dict(self._values[iid]) for iid in self._row_order]

    def has_errors(self) -> bool:
        return bool(self._errors)

    def get_errors(self) -> list[str]:
        return list(self._errors.values())

    # -- formatting -------------------------------------------------------

    @staticmethod
    def _format(value: Any, kind: str) -> str:
        if kind == "bool":
            return "Yes" if value else "No"
        if value is None:
            return ""
        if kind == "float":
            try:
                return f"{float(value):g}"
            except (TypeError, ValueError):
                return str(value)
        return str(value)

    def _col_index(self, colid: str) -> int:
        return int(colid.replace("#", "")) - 1

    # -- editing ------------------------------------------------------------

    def _on_click(self, event: tk.Event) -> None:
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        iid = self.tree.identify_row(event.y)
        colid = self.tree.identify_column(event.x)
        if not iid or not colid:
            return
        col = self.columns[self._col_index(colid)]
        if col.kind != "bool":
            return
        current = bool(self._values[iid].get(col.key))
        self._values[iid][col.key] = not current
        self._refresh_cell(iid, col)
        self._notify_change()

    def _on_double_click(self, event: tk.Event) -> None:
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        iid = self.tree.identify_row(event.y)
        colid = self.tree.identify_column(event.x)
        if not iid or not colid:
            return
        col = self.columns[self._col_index(colid)]
        if col.kind not in ("text", "float"):
            return

        bbox = self.tree.bbox(iid, colid)
        if not bbox:
            return
        x, y, w, h = bbox
        current = self._values[iid].get(col.key)
        text = "" if current is None else str(current)

        self._destroy_editor()
        entry = tk.Entry(self.tree)
        entry.insert(0, text)
        entry.select_range(0, "end")
        entry.focus_set()
        entry.place(x=x, y=y, width=w, height=h)
        self._editor = entry

        def commit(_event=None):
            self._commit_edit(iid, col, entry.get())
            self._destroy_editor()

        def cancel(_event=None):
            self._destroy_editor()

        entry.bind("<Return>", commit)
        entry.bind("<KP_Enter>", commit)
        entry.bind("<Escape>", cancel)
        entry.bind("<FocusOut>", commit)

    def _destroy_editor(self) -> None:
        if self._editor is not None:
            editor, self._editor = self._editor, None
            editor.destroy()

    def _commit_edit(self, iid: str, col: Column, raw_text: str) -> None:
        key = (iid, col.key)
        text = raw_text.strip()
        if col.kind == "float":
            if text == "":
                self._values[iid][col.key] = None
                self._errors.pop(key, None)
            else:
                try:
                    self._values[iid][col.key] = float(text.replace(",", "."))
                    self._errors.pop(key, None)
                except ValueError:
                    self._errors[key] = (
                        f"Row {int(iid) + 1}, {col.header}: '{raw_text}' is not a number."
                    )
        else:  # text
            self._values[iid][col.key] = text or None
            self._errors.pop(key, None)

        self._refresh_cell(iid, col)
        self._refresh_row_tag(iid)
        self._notify_change()

    def _refresh_cell(self, iid: str, col: Column) -> None:
        values = list(self.tree.item(iid, "values"))
        idx = next(i for i, c in enumerate(self.columns) if c.key == col.key)
        values[idx] = self._format(self._values[iid].get(col.key), col.kind)
        self.tree.item(iid, values=values)
        self._refresh_row_tag(iid)

    def _refresh_row_tag(self, iid: str) -> None:
        row_has_error = any(k == iid for k, _c in self._errors)
        self.tree.item(iid, tags=(self.INVALID_TAG,) if row_has_error else ())

    def _notify_change(self) -> None:
        if self.on_change is not None:
            self.on_change()


def populate_readonly_tree(tree: ttk.Treeview, df: pd.DataFrame, decimals: int | None = None) -> None:
    """Reset `tree`'s columns/rows to show `df` read-only."""
    tree.delete(*tree.get_children())
    tree["columns"] = list(df.columns)
    tree["show"] = "headings"
    for col in df.columns:
        tree.heading(col, text=str(col))
        width = max(70, min(140, 10 * len(str(col)) + 20))
        tree.column(col, width=width, anchor="center")

    for _, row in df.iterrows():
        display = []
        for col in df.columns:
            v = row[col]
            if isinstance(v, float):
                if pd.isna(v):
                    display.append("")
                elif decimals is not None:
                    display.append(f"{v:.{decimals}f}")
                else:
                    display.append(f"{v:g}")
            else:
                display.append("" if v is None else str(v))
        tree.insert("", "end", values=display)
