from .database import *

def side_start():
    return "right" if i18n.rtl else "left"


def side_end():
    return "left" if i18n.rtl else "right"


def text_anchor():
    return "e" if i18n.rtl else "w"


def _autohide_scrollbar(scrollbar):
    """Return a yscrollcommand that hides a scrollbar when its range fits."""
    try:
        pack_options = scrollbar.pack_info()
    except tk.TclError:
        pack_options = {"side": "right", "fill": "y"}

    state = {"visible": True}

    def update(first, last):
        try:
            scrollbar.set(first, last)
            needed = not (float(first) <= 0.0 and float(last) >= 1.0)
            if needed and not state["visible"]:
                scrollbar.pack(**pack_options)
                state["visible"] = True
            elif not needed and state["visible"]:
                scrollbar.pack_forget()
                state["visible"] = False
        except (tk.TclError, ValueError, TypeError):
            pass

    return update


def _database_error_boundary(method):
    """مرز نهایی: هیچ sqlite3.Error از متدهای Database به رابط کاربر نشت نمی‌کند."""
    from functools import wraps

    @wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except sqlite3.Error as exc:
            _raise_database_error(exc)
    return wrapped


# حتی مسیرهای پشتیبان‌گیری/بازیابی که اتصال موقت مستقل می‌سازند نیز کد خطای یکسان دارند.
for _db_method_name, _db_member in list(Database.__dict__.items()):
    if isinstance(_db_member, staticmethod):
        setattr(Database, _db_method_name, staticmethod(_database_error_boundary(_db_member.__func__)))
    elif callable(_db_member) and hasattr(_db_member, "__code__"):
        setattr(Database, _db_method_name, _database_error_boundary(_db_member))


class MoneyEntry(ttk.Entry):
    """ورودی مبلغ با جداکننده‌ی هزارگان که هنگام تایپ خودکار فرمت می‌شود."""

    _SKIP_KEYS = {"Left", "Right", "Home", "End", "Shift_L", "Shift_R", "Control_L", "Control_R", "Tab"}

    def __init__(self, master=None, textvariable=None, **kwargs):
        self._busy = False
        self._var = textvariable or tk.StringVar()
        kwargs.setdefault("justify", "right" if i18n.rtl else "left")
        super().__init__(master, textvariable=self._var, **kwargs)
        self.bind("<KeyRelease>", self._on_key)

    def _on_key(self, event=None):
        if self._busy or (event is not None and event.keysym in self._SKIP_KEYS):
            return
        current = self.get()
        digits = "".join(ch for ch in normalize_digits(current) if ch.isdigit())
        formatted = f"{int(digits):,}" if digits else ""
        if formatted == current:
            return
        try:
            cursor = self.index(tk.INSERT)
        except tk.TclError:
            cursor = len(current)
        before = sum(ch.isdigit() for ch in normalize_digits(current)[:cursor])
        self._busy = True
        try:
            self.delete(0, tk.END)
            self.insert(0, formatted)
        finally:
            self._busy = False
        position, seen = (0 if before <= 0 else len(formatted)), 0
        if before > 0:
            for index, ch in enumerate(formatted):
                if ch.isdigit():
                    seen += 1
                    if seen == before:
                        position = index + 1
                        break
        self.icursor(position)


class DataTable(ttk.Frame):
    """
    جدول با جستجو، ترتیب ستون‌ها و عرض‌ها (با کشیدن سربرگ‌ها) و ترتیب سطرها (با کشیدن سطر) که
    همه در تنظیمات ذخیره می‌شوند.
    columns : [(id, عنوان فارسی, عرض)]
    rows_fn : تابعی که لیست (iid، مقادیر، تگ) برمی‌گرداند
    """

    def __init__(self, parent, app, key, columns, rows_fn, on_open=None, row_key=None,
                 footer_fn=None, height=12, searchable=True, sort_options=None):
        super().__init__(parent)
        self.app, self.db, self.key = app, app.db, key
        self.columns, self.rows_fn = columns, rows_fn
        self.ids = [c[0] for c in columns]
        self.on_open, self.row_key, self.footer_fn = on_open, row_key, footer_fn
        self.sort_options = list(sort_options or [])
        self.sort_scope = row_key or key
        self.search_var = tk.StringVar()
        self.sort_var = tk.StringVar()
        self.active_sort = self.db.get(f"ui_sort_{self.sort_scope}") or "manual"
        self._drag = {}
        start, end = side_start(), side_end()

        if searchable or self.sort_options:
            bar = ttk.Frame(self)
            bar.pack(fill="x", pady=(0, 6))
            if searchable:
                ttk.Label(bar, text="🔍 " + T("جستجو و فیلتر")).pack(side=start, padx=4)
                ttk.Entry(bar, textvariable=self.search_var, width=27,
                          justify="right" if i18n.rtl else "left").pack(side=start, padx=4)
                ttk.Button(bar, text=T("پاکسازی"), command=lambda: self.search_var.set("")).pack(side=start, padx=4)
                self.search_var.trace_add("write", lambda *_: self._render())
            if self.sort_options:
                modes = [("manual", T("ترتیب دستی"))] + [(o[0], T(o[1])) for o in self.sort_options]
                self._sort_labels = {mode: label for mode, label in modes}
                if self.active_sort not in self._sort_labels:
                    self.active_sort = "manual"
                self.sort_var.set(self._sort_labels[self.active_sort])
                ttk.Label(bar, text=T("مرتب‌سازی:")).pack(side=start, padx=(12, 3))
                self.sort_combo = ttk.Combobox(bar, textvariable=self.sort_var,
                    values=[label for _, label in modes], state="readonly", width=25)
                self.sort_combo.pack(side=start, padx=3)
                ttk.Button(bar, text=T("اعمال"), command=self.apply_sort).pack(side=start, padx=3)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(body, columns=self.ids, displaycolumns=self._load_order(),
                                 show="headings", selectmode="browse", height=height)
        widths = self._load_widths()
        self._base_widths = {cid: widths.get(cid, width) for cid, _title, width in columns}
        self._resize_pending = False
        for cid, title, width in columns:
            self.tree.heading(cid, text=T(title))
            self.tree.column(cid, width=self._base_widths[cid], minwidth=30, anchor="center")
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        scroll.pack(side=end, fill="y")
        self.tree.pack(side=start, fill="both", expand=True)
        self.tree.configure(yscrollcommand=_autohide_scrollbar(scroll))
        colors = app.colors
        self.tree.tag_configure("odd", background=colors["stripe"])
        self.tree.tag_configure("muted", foreground=colors["muted"])
        self.tree.tag_configure("warn", foreground=colors["warn"])

        self.footer = ttk.Label(self, text="", style="Footer.TLabel", anchor=text_anchor())
        self.footer.pack(fill="x", pady=(6, 0))

        self.tree.bind("<ButtonPress-1>", self._on_press, add="+")
        self.tree.bind("<B1-Motion>", self._on_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.tree.bind("<Double-1>", self._on_double, add="+")
        # با تغییر اندازه پنجره، عرض ستون‌ها متناسب با فضای جدول تنظیم می‌شود.
        self.tree.bind("<Configure>", self._on_tree_configure, add="+")
        self.refresh()

    # ---- ذخیره و بازیابی چیدمان ----
    def _json_setting(self, name, default):
        try:
            value = json.loads(self.db.get(name, "") or "null")
        except (TypeError, ValueError):
            return default
        return value if isinstance(value, type(default)) else default

    def _load_order(self):
        saved = [c for c in self._json_setting(f"ui_cols_{self.key}", []) if c in self.ids]
        default = list(reversed(self.ids)) if i18n.rtl else list(self.ids)
        return saved + [c for c in default if c not in saved]

    def _load_widths(self):
        data = self._json_setting(f"ui_widths_{self.key}", {})
        return {c: int(w) for c, w in data.items() if c in self.ids and str(w).isdigit()}

    def _on_tree_configure(self, _event=None):
        if self._resize_pending:
            return
        self._resize_pending = True
        self.after_idle(self._apply_responsive_widths)

    def _apply_responsive_widths(self):
        self._resize_pending = False
        if not self.tree.winfo_exists():
            return
        shown = list(self.tree["displaycolumns"])
        if not shown or shown == ["#all"]:
            shown = list(self.ids)
        total = sum(max(30, int(self._base_widths.get(c, 100))) for c in shown)
        available = max(1, self.tree.winfo_width() - 4)
        scale = min(1.0, available / total) if total else 1.0
        for cid in shown:
            base = max(30, int(self._base_widths.get(cid, 100)))
            width = max(30, int(base * scale))
            if int(self.tree.column(cid, "width")) != width:
                self.tree.column(cid, width=width)

    def _save_widths(self):
        # عرض ذخیره‌شده باید عرض اصلی کاربر باشد، نه عرض موقتِ کوچک‌شده.
        shown = list(self.tree["displaycolumns"])
        if not shown or shown == ["#all"]:
            shown = list(self.ids)
        total = sum(max(30, int(self._base_widths.get(c, 100))) for c in shown)
        available = max(1, self.tree.winfo_width() - 4)
        scale = min(1.0, available / total) if total else 1.0
        if scale > 0:
            for cid in shown:
                actual = int(self.tree.column(cid, "width"))
                self._base_widths[cid] = max(30, int(round(actual / scale)))
        current = dict(self._base_widths)
        if current != self._load_widths():
            self.db.set(f"ui_widths_{self.key}", json.dumps(current))

    # ---- داده ----
    def refresh(self):
        self._rows = list(self.rows_fn())
        self._render()

    def apply_sort(self):
        label = self.sort_var.get()
        mode = next((mode for mode, text in self._sort_labels.items() if text == label), "manual")
        self.active_sort = mode
        self.db.set(f"ui_sort_{self.sort_scope}", mode)
        self._render()

    def _ordered_rows(self):
        if self.active_sort == "manual" or not self.sort_options:
            if not self.row_key:
                return list(self._rows)
            saved = [str(x) for x in self._json_setting(f"ui_rows_{self.row_key}", [])]
            position = {iid: i for i, iid in enumerate(saved)}
            return sorted(self._rows, key=lambda r: position.get(str(r[0]), len(saved) + 1))
        option = next((o for o in self.sort_options if o[0] == self.active_sort), None)
        if not option:
            return list(self._rows)
        _, _, column, kind, reverse = option
        index = self.ids.index(column)
        def value(row):
            raw = row[1][index] if index < len(row[1]) else ""
            if kind == "amount":
                try: return parse_money(raw)
                except (TypeError, ValueError): return 0
            if kind == "date":
                parsed = parse_shamsi(raw)
                return parsed or (0, 0, 0)
            if kind == "unit":
                return natural_key(raw)
            return normalize_digits(raw).strip().lower()
        return sorted(self._rows, key=value, reverse=reverse)

    def _render(self):
        query = normalize_digits(self.search_var.get()).strip().lower()
        self.tree.delete(*self.tree.get_children())
        shown = 0
        for iid, values, tag in self._ordered_rows():
            if query and query not in normalize_digits(" ".join(str(v) for v in values)).lower():
                continue
            tags = (("odd",) if shown % 2 else ()) + ((tag,) if tag else ())
            self.tree.insert("", "end", iid=str(iid), values=tuple(values), tags=tags)
            shown += 1
        self.footer.configure(text=self.footer_fn() if self.footer_fn else "")

    def selected(self):
        selection = self.tree.selection()
        return selection[0] if selection else None

    # ---- کشیدن سربرگ و سطر ----
    def _on_press(self, event):
        self._drag = {}
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            column = self.tree.identify_column(event.x)
            shown = list(self.tree["displaycolumns"])
            index = int(column[1:]) - 1 if column.startswith("#") else -1
            if 0 <= index < len(shown):
                self._drag = {"kind": "col", "col": shown[index]}
        elif region == "cell" and self.row_key and not self.search_var.get().strip():
            item = self.tree.identify_row(event.y)
            if item:
                self._drag = {"kind": "row", "item": item, "moved": False}

    def _on_motion(self, event):
        drag = self._drag
        if drag.get("kind") == "col":
            if self.tree.identify_region(event.x, event.y) != "heading":
                return
            target = self.tree.identify_column(event.x)
            shown = list(self.tree["displaycolumns"])
            if not target.startswith("#"):
                return
            new_index = int(target[1:]) - 1
            if 0 <= new_index < len(shown) and drag["col"] in shown:
                old_index = shown.index(drag["col"])
                if old_index != new_index:
                    shown.insert(new_index, shown.pop(old_index))
                    self.tree["displaycolumns"] = shown
        elif drag.get("kind") == "row":
            target = self.tree.identify_row(event.y)
            if target and target != drag["item"]:
                self.tree.move(drag["item"], "", self.tree.index(target))
                drag["moved"] = True

    def _on_release(self, _event):
        drag = self._drag
        if drag.get("kind") == "col":
            self.db.set(f"ui_cols_{self.key}", json.dumps(list(self.tree["displaycolumns"])))
        elif drag.get("kind") == "row" and drag.get("moved"):
            self.db.set(f"ui_rows_{self.row_key}", json.dumps(list(self.tree.get_children(""))))
            self.active_sort = "manual"
            self.db.set(f"ui_sort_{self.sort_scope}", "manual")
            if self.sort_options:
                self.sort_var.set(self._sort_labels.get("manual", "ترتیب دستی"))
        self._drag = {}
        # ذخیره عرض ستون پس از پایان کامل پردازش رویداد Treeview؛
        # در غیر این صورت ممکن است عرض پیش از تغییر اندازه ثبت شود.
        try:
            self.tree.after_idle(self._save_widths)
        except tk.TclError:
            pass

    def _on_double(self, event):
        if self.on_open and self.tree.identify_region(event.x, event.y) == "cell":
            self.on_open()


class FormDialog(tk.Toplevel):
    """
    فرم گفت‌وگویی عمومی. هر فیلد یک dict است:
      key, label, kind (text|money|date|choice|radio|check), required, default,
      choices=[(مقدار, عنوان نمایشی)], show_if=(کلید, مقدار), positive (برای مبلغ)
    نتیجه (self.result) یک dict از مقادیر یا None (انصراف) است.
    """

    def __init__(self, app, title, fields, validate=None, on_change=None, save_text="ذخیره", parent=None):
        # app مالک تنظیمات/رنگ‌هاست؛ parent پنجره‌ای است که دیالوگ باید روی آن باز شود.
        super().__init__(parent or app)
        self.app, self.fields, self.validate, self.on_change = app, fields, validate, on_change
        self.result = None
        self.vars, self.labels, self.widgets, self.maps, self.touched = {}, {}, {}, {}, set()
        self._ready = False
        self.title(T(title))
        self.configure(bg=app.colors["bg"])
        self.transient(parent or app)
        self.resizable(False, False)

        rtl = i18n.rtl
        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        label_col, widget_col = (1, 0) if rtl else (0, 1)
        body.columnconfigure(widget_col, weight=1)
        justify = "right" if rtl else "left"

        for row, f in enumerate(fields):
            key, kind = f["key"], f.get("kind", "text")
            label = ttk.Label(body, text=T(f["label"]) + (" *" if f.get("required") else ""))
            label.grid(row=row, column=label_col, sticky=text_anchor(), padx=(0, 12) if not rtl else (12, 0), pady=6)
            default = f.get("default")
            if kind in ("choice", "radio"):
                pairs = list(f["choices"])
                self.maps[key] = pairs
                labels = [p[1] for p in pairs]
                if kind == "radio":
                    initial = next((str(p[0]) for p in pairs if str(p[0]) == str(default)),
                                   str(pairs[0][0]) if pairs else "")
                    var = tk.StringVar(value=initial)
                    widget = ttk.Frame(body)
                    for value, text in pairs:
                        ttk.Radiobutton(widget, text=text, value=str(value), variable=var).pack(
                            side=side_start(), padx=6)
                else:
                    initial = next((p[1] for p in pairs if p[0] == default), labels[0] if labels else "")
                    var = tk.StringVar(value=initial)
                    widget = ttk.Combobox(body, textvariable=var, values=labels, state="readonly", width=32,
                                          justify=justify)
            elif kind == "check":
                var = tk.BooleanVar(value=bool(default))
                widget = ttk.Checkbutton(body, text=T(f.get("text", "")), variable=var)
            elif kind == "money":
                var = tk.StringVar(value=money(default) if default not in (None, "") else "")
                widget = MoneyEntry(body, textvariable=var, width=34)
            else:
                var = tk.StringVar(value="" if default is None else str(default))
                widget = ttk.Entry(body, textvariable=var, width=36, justify=justify)
            if kind in ("text", "money", "date"):
                widget.bind("<Key>", lambda _e, k=key: self.touched.add(k), add="+")
            widget.grid(row=row, column=widget_col, sticky="ew", pady=6)
            if kind in ("choice", "radio", "check"):
                var.trace_add("write", lambda *_: self._changed())
            self.vars[key], self.labels[key], self.widgets[key] = var, label, widget

        buttons = ttk.Frame(body)
        buttons.grid(row=len(fields), column=0, columnspan=2, pady=(16, 0))
        ttk.Button(buttons, text=T(save_text), style="Accent.TButton", command=self.submit).pack(side=side_start(), padx=6)
        ttk.Button(buttons, text=T("انصراف"), command=self.destroy).pack(side=side_start(), padx=6)

        self.bind("<Return>", lambda _e: self.submit())
        self.bind("<Escape>", lambda _e: self.destroy())
        self._update_visibility()
        first = next((self.widgets[f["key"]] for f in fields if f.get("kind", "text") in ("text", "money", "date")), None)
        if first is not None:
            first.focus_set()
        self._ready = True
        if on_change:
            on_change(self)

        self.update_idletasks()
        dialog_parent = parent or app
        x = dialog_parent.winfo_rootx() + max(0, (dialog_parent.winfo_width() - self.winfo_reqwidth()) // 2)
        y = dialog_parent.winfo_rooty() + max(0, (dialog_parent.winfo_height() - self.winfo_reqheight()) // 3)
        self.geometry(f"+{x}+{y}")
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.wait_window(self)

    # ---- مقدارها ----
    def value(self, key):
        spec = next(f for f in self.fields if f["key"] == key)
        kind = spec.get("kind", "text")
        var = self.vars[key]
        if kind == "radio":
            selected = var.get()
            return next((p[0] for p in self.maps[key] if str(p[0]) == selected), None)
        if kind == "choice":
            label = var.get()
            return next((p[0] for p in self.maps[key] if p[1] == label), None)
        if kind == "check":
            return bool(var.get())
        return var.get().strip()

    get = value

    def set(self, key, value):
        spec = next(f for f in self.fields if f["key"] == key)
        kind = spec.get("kind", "text")
        if kind == "radio":
            if any(str(p[0]) == str(value) for p in self.maps[key]):
                self.vars[key].set(str(value))
        elif kind == "choice":
            label = next((p[1] for p in self.maps[key] if p[0] == value), None)
            if label is not None:
                self.vars[key].set(label)
        elif kind == "check":
            self.vars[key].set(bool(value))
        elif kind == "money":
            self.vars[key].set(money(value) if value not in (None, "") else "")
        else:
            self.vars[key].set("" if value is None else str(value))

    def _visible(self, spec):
        cond = spec.get("show_if")
        return not cond or self.value(cond[0]) == cond[1]

    def _update_visibility(self):
        for f in self.fields:
            visible = self._visible(f)
            for widget in (self.labels[f["key"]], self.widgets[f["key"]]):
                widget.grid() if visible else widget.grid_remove()

    def _changed(self):
        if not self._ready:
            return
        self._update_visibility()
        if self.on_change:
            self.on_change(self)

    def _fail(self, message, key=None):
        messagebox.showerror(T("خطا"), message, parent=self)
        if key is not None:
            try:
                self.widgets[key].focus_set()
            except tk.TclError:
                pass

    def submit(self):
        out = {}
        for f in self.fields:
            key, kind = f["key"], f.get("kind", "text")
            # مخفی بودن فیلد فقط نمایش آن را تغییر می‌دهد؛ مقدارش نباید با ذخیره فرم پاک شود.
            raw = self.value(key)
            if kind in ("choice", "radio"):
                if raw is None and f.get("required"):
                    return self._fail(T("فیلدهای الزامی را کامل کنید."), key)
                out[key] = raw
            elif kind == "check":
                out[key] = raw
            elif kind == "money":
                if raw == "" and f.get("required"):
                    return self._fail(T("فیلدهای الزامی را کامل کنید."), key)
                try:
                    amount = parse_money(raw)
                except ValueError as exc:
                    message = translate_error(exc) if str(exc) in ERROR_MESSAGES else T("مبلغ باید عددی باشد.")
                    return self._fail(T(message), key)
                positive_if = f.get("positive_if")
                must_be_positive = f.get("positive", False) or (
                    positive_if and self.value(positive_if[0]) == positive_if[1])
                if must_be_positive and amount <= 0:
                    return self._fail(T("مبلغ باید بیشتر از صفر باشد."), key)
                out[key] = amount
            elif kind == "date":
                if raw == "":
                    if f.get("required"):
                        return self._fail(T("فیلدهای الزامی را کامل کنید."), key)
                    out[key] = ""
                    continue
                parsed = parse_shamsi(raw)
                if not parsed:
                    return self._fail(T("تاریخ نامعتبر است. نمونه: {}", "1405/02/15"), key)
                out[key] = f"{parsed[0]:04d}/{parsed[1]:02d}/{parsed[2]:02d}"
            else:
                if f.get("required") and not raw:
                    return self._fail(T("فیلدهای الزامی را کامل کنید."), key)
                out[key] = raw
        if self.validate:
            message = self.validate(out)
            if message:
                return self._fail(message)
        self.result = out
        self.destroy()


# ----------------------------------------------------------------------
#  ساخت PDF (همیشه فارسی و راست‌به‌چپ)
# ----------------------------------------------------------------------

__all__ = [name for name in globals() if not name.startswith('__')]
