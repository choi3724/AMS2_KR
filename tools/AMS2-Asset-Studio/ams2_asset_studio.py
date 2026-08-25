#!/usr/bin/env python3
"""AMS2 Font / Layout / Text Studio (safe copy editor)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from asset_core import (
    bgui_rows,
    build_single_font,
    edit_bgui_copy,
    edit_tdb_copy,
    load_module,
    tdb_rows,
)


HERE = Path(__file__).resolve().parent
WORK = HERE.parent
DEFAULT_RELEASE = Path(r"E:\AMS2_Korean_Work\releases\AMS2-Korean-Closed-Beta-0.6.2-Hotfix-Pretendard\payload\direct")
DEFAULT_BGUI_TOOL = HERE / "vendor" / "ams2_bgui_editor.py"
DEFAULT_TDB_TOOL = HERE / "vendor" / "ams2_tdb_editor.py"
DEFAULT_FONT_TOOL = HERE / "vendor" / "build_unified_ui_fonts.py"
DEFAULT_DDS_BUILDER = HERE / "vendor" / "ams2_korean_font_builder.py"
DEFAULT_PRETENDARD = HERE / "assets" / "Pretendard-Medium.otf"


class Studio(ttk.Frame):
    def __init__(self, root: tk.Tk):
        super().__init__(root, padding=10)
        self.root = root
        self.pack(fill="both", expand=True)
        self.bgui_data: list[dict] = []
        self.tdb_data: list[dict] = []
        self.bgui_pending: dict[int, dict] = {}
        self.tdb_pending: dict[int, str] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="AMS2 Font / Layout / Text Studio", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Label(header, text="입력 파일은 수정하지 않으며 새 파일만 생성합니다.", foreground="#a33").pack(side="right")
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        font_tab = ttk.Frame(notebook, padding=10)
        bgui_tab = ttk.Frame(notebook, padding=10)
        tdb_tab = ttk.Frame(notebook, padding=10)
        notebook.add(font_tab, text="폰트 생성")
        notebook.add(bgui_tab, text="BGUI 레이아웃/폰트")
        notebook.add(tdb_tab, text="TDB 텍스트")
        self._build_font_tab(font_tab)
        self._build_bgui_tab(bgui_tab)
        self._build_tdb_tab(tdb_tab)
        self.status = tk.StringVar(value="준비")
        ttk.Label(self, textvariable=self.status, anchor="w").pack(fill="x", pady=(8, 0))

    @staticmethod
    def _entry_row(parent, row, label, variable, browse=None, width=78):
        ttk.Label(parent, text=label, width=19).grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.grid(row=row, column=1, sticky="ew", pady=3)
        if browse:
            ttk.Button(parent, text="찾기", command=browse).grid(row=row, column=2, padx=(6, 0), pady=3)
        return entry

    def _build_font_tab(self, tab) -> None:
        tab.columnconfigure(1, weight=1)
        self.font_source = tk.StringVar(value=str(DEFAULT_PRETENDARD))
        self.font_base = tk.StringVar(value=str(DEFAULT_RELEASE / "GUI" / "kr09_font_heading_bold.bfont"))
        self.font_dds = tk.StringVar(value=str(DEFAULT_RELEASE / "GUI" / "kr09_font_heading_bold_00.dds"))
        self.font_output = tk.StringVar(value=str(HERE / "output" / "new_font"))
        self.font_alias = tk.StringVar(value="kr_custom_font")
        self.font_size = tk.StringVar(value="24")
        self.font_scale_x = tk.StringVar(value="1.0")
        self.font_scale_y = tk.StringVar(value="1.0")
        self.font_offset_x = tk.StringVar(value="0")
        self.font_offset_y = tk.StringVar(value="0")
        self.font_line_height = tk.StringVar(value="0")
        self.font_baseline = tk.StringVar(value="-1")
        self.font_builder = tk.StringVar(value=str(DEFAULT_FONT_TOOL))
        self.dds_builder = tk.StringVar(value=str(DEFAULT_DDS_BUILDER))

        self._entry_row(tab, 0, "원본 TTF/OTF", self.font_source, lambda: self._pick_file(self.font_source, [("Font", "*.ttf *.otf")]))
        self._entry_row(tab, 1, "기준 BFONT", self.font_base, lambda: self._pick_file(self.font_base, [("BFONT", "*.bfont")]))
        self._entry_row(tab, 2, "기준 DDS 00", self.font_dds, lambda: self._pick_file(self.font_dds, [("DDS", "*.dds")]))
        self._entry_row(tab, 3, "출력 폴더(새 폴더)", self.font_output, lambda: self._pick_dir(self.font_output))
        self._entry_row(tab, 4, "새 폰트 alias", self.font_alias)

        controls = ttk.LabelFrame(tab, text="글리프/라인 조절", padding=8)
        controls.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 6))
        fields = [
            ("픽셀 크기", self.font_size), ("가로 배율", self.font_scale_x), ("세로 배율", self.font_scale_y),
            ("X bearing 이동", self.font_offset_x), ("Y glyph 이동", self.font_offset_y),
            ("Line height (0=기준)", self.font_line_height), ("Baseline (-1=자동)", self.font_baseline),
        ]
        for index, (label, variable) in enumerate(fields):
            ttk.Label(controls, text=label).grid(row=index // 4, column=(index % 4) * 2, sticky="w", padx=(0, 4), pady=3)
            ttk.Entry(controls, textvariable=variable, width=10).grid(row=index // 4, column=(index % 4) * 2 + 1, sticky="w", padx=(0, 16), pady=3)

        ttk.Label(tab, text="추가 문자(기준 BFONT에 없는 글리프)").grid(row=6, column=0, sticky="nw", pady=3)
        self.extra_chars = tk.Text(tab, height=4, wrap="word")
        self.extra_chars.grid(row=6, column=1, columnspan=2, sticky="ew", pady=3)
        advanced = ttk.LabelFrame(tab, text="고급: 기존 검증 도구 경로", padding=8)
        advanced.grid(row=7, column=0, columnspan=3, sticky="ew", pady=6)
        advanced.columnconfigure(1, weight=1)
        self._entry_row(advanced, 0, "통합 폰트 모듈", self.font_builder, lambda: self._pick_file(self.font_builder, [("Python", "*.py")]), 70)
        self._entry_row(advanced, 1, "DDS/BFONT parser", self.dds_builder, lambda: self._pick_file(self.dds_builder, [("Python", "*.py")]), 70)
        ttk.Button(tab, text="BFONT/DDS 생성", command=self._start_font_build).grid(row=8, column=1, sticky="e", pady=(10, 0))

    def _build_bgui_tab(self, tab) -> None:
        top = ttk.Frame(tab)
        top.pack(fill="x")
        self.bgui_path = tk.StringVar(value=str(DEFAULT_RELEASE / "GUI" / "menu_mainmenu_1_6.bgui"))
        ttk.Entry(top, textvariable=self.bgui_path).pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="BGUI 열기", command=self._open_bgui).pack(side="left", padx=(6, 0))
        self.bgui_filter = tk.StringVar()
        ttk.Entry(top, textvariable=self.bgui_filter, width=26).pack(side="left", padx=(10, 0))
        ttk.Button(top, text="필터", command=self._refresh_bgui_tree).pack(side="left", padx=(4, 0))

        columns = ("ordinal", "object", "reference", "font", "x", "y", "w", "h")
        self.bgui_tree = ttk.Treeview(tab, columns=columns, show="headings", selectmode="extended")
        widths = (65, 80, 330, 260, 65, 65, 65, 65)
        for column, width in zip(columns, widths):
            self.bgui_tree.heading(column, text=column)
            self.bgui_tree.column(column, width=width, anchor="w")
        ybar = ttk.Scrollbar(tab, orient="vertical", command=self.bgui_tree.yview)
        self.bgui_tree.configure(yscrollcommand=ybar.set)
        self.bgui_tree.pack(side="left", fill="both", expand=True, pady=(8, 0))
        ybar.pack(side="left", fill="y", pady=(8, 0))
        self.bgui_tree.bind("<<TreeviewSelect>>", self._bgui_selected)

        editor = ttk.LabelFrame(tab, text="선택 Text 편집", padding=8)
        editor.pack(side="right", fill="y", padx=(8, 0), pady=(8, 0))
        self.bgui_font = tk.StringVar()
        self.bgui_x = tk.StringVar()
        self.bgui_y = tk.StringVar()
        self.bgui_w = tk.StringVar()
        self.bgui_h = tk.StringVar()
        for row, (label, variable) in enumerate((
            ("폰트 경로", self.bgui_font), ("X", self.bgui_x), ("Y", self.bgui_y),
            ("폭", self.bgui_w), ("높이", self.bgui_h),
        )):
            ttk.Label(editor, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(editor, textvariable=variable, width=34).grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Label(editor, text="여러 행 선택 시 빈 칸은 기존 값 유지", foreground="#666").grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 8))
        ttk.Button(editor, text="선택 항목에 적용", command=self._apply_bgui_pending).grid(row=6, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(editor, text="새 BGUI로 저장", command=self._save_bgui).grid(row=7, column=0, columnspan=2, sticky="ew", pady=3)
        self.bgui_pending_label = ttk.Label(editor, text="대기 변경: 0")
        self.bgui_pending_label.grid(row=8, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_tdb_tab(self, tab) -> None:
        top = ttk.Frame(tab)
        top.pack(fill="x")
        self.tdb_path = tk.StringVar(value=str(DEFAULT_RELEASE / "text" / "game.tdb"))
        ttk.Entry(top, textvariable=self.tdb_path).pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="TDB 열기", command=self._open_tdb).pack(side="left", padx=(6, 0))
        self.tdb_filter = tk.StringVar()
        ttk.Entry(top, textvariable=self.tdb_filter, width=26).pack(side="left", padx=(10, 0))
        ttk.Button(top, text="필터", command=self._refresh_tdb_tree).pack(side="left", padx=(4, 0))

        columns = ("index", "group", "key", "english", "korean")
        self.tdb_tree = ttk.Treeview(tab, columns=columns, show="headings", selectmode="browse")
        widths = (65, 120, 300, 300, 300)
        for column, width in zip(columns, widths):
            self.tdb_tree.heading(column, text=column)
            self.tdb_tree.column(column, width=width, anchor="w")
        ybar = ttk.Scrollbar(tab, orient="vertical", command=self.tdb_tree.yview)
        self.tdb_tree.configure(yscrollcommand=ybar.set)
        self.tdb_tree.pack(fill="both", expand=True, pady=(8, 0))
        ybar.place(in_=self.tdb_tree, relx=1.0, rely=0, relheight=1.0, anchor="ne")
        self.tdb_tree.bind("<<TreeviewSelect>>", self._tdb_selected)

        editor = ttk.LabelFrame(tab, text="선택 문구", padding=8)
        editor.pack(fill="x", pady=(8, 0))
        self.tdb_key = tk.StringVar()
        ttk.Label(editor, textvariable=self.tdb_key, foreground="#555").pack(anchor="w")
        panes = ttk.Frame(editor)
        panes.pack(fill="x", pady=4)
        self.tdb_english = tk.Text(panes, height=4, wrap="word", state="disabled")
        self.tdb_korean = tk.Text(panes, height=4, wrap="word")
        self.tdb_english.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.tdb_korean.pack(side="left", fill="both", expand=True, padx=(4, 0))
        buttons = ttk.Frame(editor)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="한국어 변경 적용", command=self._apply_tdb_pending).pack(side="right")
        ttk.Button(buttons, text="새 TDB로 저장", command=self._save_tdb).pack(side="right", padx=(0, 6))
        self.tdb_pending_label = ttk.Label(buttons, text="대기 변경: 0")
        self.tdb_pending_label.pack(side="left")

    def _pick_file(self, variable, filetypes):
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            variable.set(path)

    def _pick_dir(self, variable):
        path = filedialog.askdirectory()
        if path:
            variable.set(path)

    def _set_status(self, message):
        self.status.set(message)
        self.root.update_idletasks()

    def _start_font_build(self):
        self._set_status("폰트를 생성하는 중입니다...")
        threading.Thread(target=self._font_build_worker, daemon=True).start()

    def _font_build_worker(self):
        try:
            result = build_single_font(
                Path(self.font_source.get()), Path(self.font_base.get()), Path(self.font_dds.get()),
                Path(self.font_output.get()), self.font_alias.get().strip(), int(self.font_size.get()),
                float(self.font_scale_x.get()), float(self.font_scale_y.get()), int(self.font_offset_x.get()),
                int(self.font_offset_y.get()), int(self.font_line_height.get()), int(self.font_baseline.get()),
                self.extra_chars.get("1.0", "end-1c"), Path(self.font_builder.get()), Path(self.dds_builder.get()),
            )
            self.root.after(0, lambda: self._operation_ok(f"폰트 생성 완료: {result['alias']} / {result['atlas']['count']} pages"))
        except Exception as exc:
            self.root.after(0, lambda: self._operation_error(str(exc)))

    def _operation_ok(self, message):
        self._set_status(message)
        messagebox.showinfo("완료", message)

    def _operation_error(self, message):
        self._set_status(f"오류: {message}")
        messagebox.showerror("작업 실패", message)

    def _open_bgui(self):
        try:
            self._set_status("BGUI를 분석하는 중입니다...")
            self.bgui_data = bgui_rows(Path(self.bgui_path.get()), DEFAULT_BGUI_TOOL)
            self.bgui_pending.clear()
            self._refresh_bgui_tree()
            self._set_status(f"BGUI Text {len(self.bgui_data):,}개 로드")
        except Exception as exc:
            self._operation_error(str(exc))

    def _refresh_bgui_tree(self):
        self.bgui_tree.delete(*self.bgui_tree.get_children())
        needle = self.bgui_filter.get().casefold().strip()
        for row in self.bgui_data:
            haystack = f"{row['ordinal']} {row['object_id']} {row['text_reference']} {row['font']}".casefold()
            if needle and needle not in haystack:
                continue
            ordinal = row["ordinal"]
            values = (ordinal, row["object_id"], row["text_reference"], row["font"], row["x"], row["y"], row["width"], row["height"])
            self.bgui_tree.insert("", "end", iid=str(ordinal), values=values, tags=("pending",) if ordinal in self.bgui_pending else ())
        self.bgui_tree.tag_configure("pending", background="#fff1b8")

    def _bgui_selected(self, _event=None):
        selected = self.bgui_tree.selection()
        if len(selected) != 1:
            for variable in (self.bgui_font, self.bgui_x, self.bgui_y, self.bgui_w, self.bgui_h):
                variable.set("")
            return
        row = self.bgui_data[int(selected[0])]
        pending = self.bgui_pending.get(row["ordinal"], {})
        self.bgui_font.set(str(pending.get("font", row["font"])))
        self.bgui_x.set(str(pending.get("x", row["x"])))
        self.bgui_y.set(str(pending.get("y", row["y"])))
        self.bgui_w.set(str(pending.get("width", row["width"])))
        self.bgui_h.set(str(pending.get("height", row["height"])))

    def _apply_bgui_pending(self):
        selected = [int(value) for value in self.bgui_tree.selection()]
        if not selected:
            return self._operation_error("편집할 Text 행을 선택하십시오.")
        fields = {
            "font": self.bgui_font.get().strip(), "x": self.bgui_x.get().strip(), "y": self.bgui_y.get().strip(),
            "width": self.bgui_w.get().strip(), "height": self.bgui_h.get().strip(),
        }
        try:
            for ordinal in selected:
                edit = dict(self.bgui_pending.get(ordinal, {}))
                if fields["font"]:
                    edit["font"] = fields["font"]
                for key in ("x", "y", "width", "height"):
                    if fields[key]:
                        edit[key] = float(fields[key])
                self.bgui_pending[ordinal] = edit
            self.bgui_pending_label.configure(text=f"대기 변경: {len(self.bgui_pending)}")
            self._refresh_bgui_tree()
            self._set_status(f"BGUI 변경 {len(selected)}개를 대기 목록에 추가")
        except ValueError:
            self._operation_error("좌표와 크기는 숫자로 입력하십시오.")

    def _save_bgui(self):
        if not self.bgui_pending:
            return self._operation_error("저장할 BGUI 변경이 없습니다.")
        output = filedialog.asksaveasfilename(defaultextension=".bgui", filetypes=[("BGUI", "*.bgui")])
        if not output:
            return
        try:
            result = edit_bgui_copy(Path(self.bgui_path.get()), Path(output), DEFAULT_BGUI_TOOL, self.bgui_pending)
            self._operation_ok(f"새 BGUI 저장 완료: {result['output']}")
        except Exception as exc:
            self._operation_error(str(exc))

    def _open_tdb(self):
        try:
            self._set_status("TDB를 분석하는 중입니다...")
            self.tdb_data = tdb_rows(Path(self.tdb_path.get()), DEFAULT_TDB_TOOL)
            self.tdb_pending.clear()
            self._refresh_tdb_tree()
            self._set_status(f"TDB {len(self.tdb_data):,}개 key 로드")
        except Exception as exc:
            self._operation_error(str(exc))

    def _refresh_tdb_tree(self):
        self.tdb_tree.delete(*self.tdb_tree.get_children())
        needle = self.tdb_filter.get().casefold().strip()
        for row in self.tdb_data:
            korean = self.tdb_pending.get(row["index"], row["korean"])
            haystack = f"{row['index']} {row['group']} {row['key']} {row['english']} {korean}".casefold()
            if needle and needle not in haystack:
                continue
            self.tdb_tree.insert("", "end", iid=str(row["index"]), values=(row["index"], row["group"], row["key"], row["english"], korean), tags=("pending",) if row["index"] in self.tdb_pending else ())
        self.tdb_tree.tag_configure("pending", background="#fff1b8")

    def _tdb_selected(self, _event=None):
        selected = self.tdb_tree.selection()
        if not selected:
            return
        row = self.tdb_data[int(selected[0])]
        self.tdb_key.set(f"{row['index']} | {row['group']} | {row['key']}")
        self.tdb_english.configure(state="normal")
        self.tdb_english.delete("1.0", "end")
        self.tdb_english.insert("1.0", row["english"])
        self.tdb_english.configure(state="disabled")
        self.tdb_korean.delete("1.0", "end")
        self.tdb_korean.insert("1.0", self.tdb_pending.get(row["index"], row["korean"]))

    def _apply_tdb_pending(self):
        selected = self.tdb_tree.selection()
        if not selected:
            return self._operation_error("편집할 TDB 행을 선택하십시오.")
        index = int(selected[0])
        self.tdb_pending[index] = self.tdb_korean.get("1.0", "end-1c")
        self.tdb_pending_label.configure(text=f"대기 변경: {len(self.tdb_pending)}")
        self._refresh_tdb_tree()
        self.tdb_tree.selection_set(str(index))
        self._set_status(f"TDB index {index} 변경을 대기 목록에 추가")

    def _save_tdb(self):
        if not self.tdb_pending:
            return self._operation_error("저장할 TDB 변경이 없습니다.")
        output = filedialog.asksaveasfilename(defaultextension=".tdb", filetypes=[("TDB", "*.tdb")])
        if not output:
            return
        try:
            result = edit_tdb_copy(Path(self.tdb_path.get()), Path(output), DEFAULT_TDB_TOOL, self.tdb_pending)
            self._operation_ok(f"새 TDB 저장 완료: {result['output']}")
        except Exception as exc:
            self._operation_error(str(exc))


def self_test() -> int:
    checks = {}
    try:
        load_module(DEFAULT_BGUI_TOOL, "ams2_studio_selftest_bgui")
        checks["bgui_module"] = True
        load_module(DEFAULT_TDB_TOOL, "ams2_studio_selftest_tdb")
        checks["tdb_module"] = True
        load_module(DEFAULT_FONT_TOOL, "ams2_studio_selftest_font")
        checks["font_module"] = True
        load_module(DEFAULT_DDS_BUILDER, "ams2_studio_selftest_dds")
        checks["dds_module"] = True
        sample_bgui = DEFAULT_RELEASE / "GUI" / "menu_mainmenu_1_6.bgui"
        sample_tdb = DEFAULT_RELEASE / "text" / "game.tdb"
        checks["bgui_text_records"] = len(bgui_rows(sample_bgui, DEFAULT_BGUI_TOOL))
        checks["tdb_records"] = len(tdb_rows(sample_tdb, DEFAULT_TDB_TOOL))
        result = {"status": "PASS", "checks": checks}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "checks": checks, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    root = tk.Tk()
    root.title("AMS2 Font / Layout / Text Studio")
    root.geometry("1500x900")
    root.minsize(1100, 700)
    Studio(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
