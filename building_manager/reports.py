from .widgets import *

class PdfKit:
    HEADER_BG = "#dce8f2"
    MIN_CELL_FONT = 8.0
    BASE_CELL_FONT = 10.5
    MAX_CELL_FONT = 12.5
    CELL_PAD_X = 12

    def __init__(self, rtl_fn):
        self.rtl = rtl_fn
        # متن فارسی باید همگی از همان فونت اصلی ثبت‌شده استفاده کند تا خانواده‌ی قلم مخلوط نشود.
        base = dict(fontName=PDF_FONT)
        # اندازه‌های پایه نقطه شروع‌اند؛ اندازه نهایی عنوان‌ها و سلول‌ها با فضای واقعی تنظیم می‌شود.
        self.s_title = ParagraphStyle("bm_title", fontSize=20, leading=27, alignment=1, spaceAfter=5, **base)
        self.s_sub = ParagraphStyle("bm_sub", fontSize=12, leading=17, alignment=1, textColor=rl_colors.grey, **base)
        self.s_h = ParagraphStyle("bm_h", fontSize=15, leading=21, alignment=2, spaceBefore=12, spaceAfter=7, **base)
        self.s_text = ParagraphStyle("bm_text", fontSize=12, leading=17, alignment=2, **base)
        self.s_cell = ParagraphStyle("bm_cell", fontSize=self.BASE_CELL_FONT, leading=15, alignment=1, **base)

    def _text_width(self, text, font_size=None, font_name=None):
        return pdfmetrics.stringWidth(
            self.rtl("" if text is None else str(text)),
            font_name or self.s_cell.fontName,
            font_size or self.BASE_CELL_FONT,
        )

    def _cell_font_size(self, text, width, *, minimum=None, maximum=None):
        """فونت را متناسب با عرض واقعی سلول انتخاب می‌کند؛ کوچک‌سازی فقط تا حد خوانا مجاز است."""
        minimum = self.MIN_CELL_FONT if minimum is None else minimum
        maximum = self.MAX_CELL_FONT if maximum is None else maximum
        usable = max(1, width - self.CELL_PAD_X)
        measured = self._text_width(text, self.BASE_CELL_FONT)
        if measured <= usable:
            # از فضای آزاد برای خواناتر شدن متن استفاده می‌کنیم، ولی رشد فونت محدود است.
            return min(maximum, max(self.BASE_CELL_FONT, self.BASE_CELL_FONT * usable / max(measured, 1)))
        return max(minimum, min(self.BASE_CELL_FONT, self.BASE_CELL_FONT * usable / max(measured, 1)))

    def _column_font_sizes(self, rows, widths):
        """یک اندازه فونت برای تمام سلول‌های هر ستون؛ بر اساس بلندترین کلمه."""
        sizes = []
        for col, width in enumerate(widths):
            longest = 0.0
            for row in rows:
                value = row[col] if col < len(row) and row[col] is not None else ""
                for word in re.split(r"\s+", str(value).strip()):
                    if word:
                        longest = max(longest, self._text_width(word, self.BASE_CELL_FONT))
            usable = max(1.0, width - self.CELL_PAD_X)
            size = self.BASE_CELL_FONT
            if longest > usable:
                size = self.BASE_CELL_FONT * usable / longest
            # با حداقل فونت تعریف‌شده در کلاس هماهنگ می‌مانیم تا متن PDF
            # به اندازه‌های بسیار ریز و ناخوانا (مثلاً ۵pt) سقوط نکند.
            sizes.append(max(self.MIN_CELL_FONT, min(self.BASE_CELL_FONT, size)))
        return sizes

    def _paragraph(self, text, width, *, style=None, unbroken=False, bold=False, font_size=None):
        """متن را فقط بین کلمات می‌شکند و هر خط فارسی را جداگانه راست‌به‌چپ می‌کند."""
        raw = "" if text is None else str(text)  # متن سلول‌های PDF، از جمله نام حساب، باید دقیقاً حفظ شود.
        base_style = style or self.s_cell
        font_name = base_style.fontName
        size = font_size if font_size is not None else self._cell_font_size(raw, width)
        usable = max(1.0, width - self.CELL_PAD_X)

        # شکستن دستی متن منطقی پیش از اعمال الگوریتم دوجهته؛ این کار ترتیب خطوط فارسی را حفظ می‌کند.
        logical_lines = []
        for paragraph in raw.splitlines() or [""]:
            words = paragraph.split()
            if not words:
                logical_lines.append("")
                continue
            line = words[0]
            for word in words[1:]:
                candidate = line + " " + word
                if self._text_width(candidate, size, font_name) <= usable:
                    line = candidate
                else:
                    logical_lines.append(line)
                    line = word
            logical_lines.append(line)

        rendered = []
        for line in logical_lines:
            shaped = self.rtl(line) if line else ""
            rendered.append(html.escape(shaped))
        display = "<br/>".join(rendered)
        cell_style = ParagraphStyle(
            "bm_dynamic_cell", parent=base_style, fontName=font_name,
            fontSize=size, leading=size * 1.35,
            splitLongWords=0, wordWrap=None,
        )
        return Paragraph(display, cell_style)

    def para(self, text, style=None):
        base_style = style or self.s_text
        display = self.rtl(T(text))
        measured = pdfmetrics.stringWidth(display, base_style.fontName, base_style.fontSize)
        usable_width = 794.0
        if measured > usable_width:
            size = max(8.0, base_style.fontSize * usable_width / measured)
        else:
            size = min(base_style.fontSize * 1.18, base_style.fontSize * usable_width / max(measured, 1))
        fitted_style = ParagraphStyle(
            "bm_dynamic_paragraph", parent=base_style, fontSize=size,
            leading=size * (base_style.leading / base_style.fontSize),
        )
        return Paragraph(display, fitted_style)

    def title(self, text):
        return self.para(text, self.s_title)

    def sub(self, text):
        return self.para(text, self.s_sub)

    def heading(self, text):
        return self.para(text, self.s_h)

    def space(self, height=10):
        return Spacer(1, height)

    def section(self, title, table):
        """عنوان و جدول را کنار هم نگه می‌دارد؛ جدول‌های بلند همچنان بین صفحات می‌شکنند."""
        return KeepTogether([self.heading(T(title)), table])

    def _fit_column_widths(self, headers, rows, width_budget):
        """عرض ستون‌ها را از روی طول واقعی داده‌ها تعیین می‌کند، نه عرض‌های ثابت قبلی."""
        count = len(headers) if headers else (len(rows[0]) if rows else 0)
        if count <= 0:
            return []
        font_name = self.s_cell.fontName
        natural = []
        minimums = []
        for col in range(count):
            values = []
            if headers:
                values.append(headers[col] if col < len(headers) else "")
            for row in rows:
                values.append(row[col] if col < len(row) else "")
            # اندازه‌گیری با فونت پایه؛ فضای خالی/None فقط به اندازه سربرگ سهم می‌گیرد.
            max_width = max((self._text_width(v, self.BASE_CELL_FONT, font_name) for v in values), default=0)
            header_width = self._text_width(headers[col], self.BASE_CELL_FONT, font_name) if headers else 0
            natural.append(max_width + self.CELL_PAD_X)
            minimums.append(max(24, header_width + self.CELL_PAD_X))

        # اگر مجموع حداقل‌ها از بودجه بیشتر باشد، همه ستون‌ها به نسبت حداقل لازم کوچک می‌شوند.
        min_total = sum(minimums)
        if min_total >= width_budget:
            scale = width_budget / max(min_total, 1)
            # مجموع عرض‌ها دقیقاً داخل بودجه می‌ماند؛ کف ثابت ۱۲pt می‌توانست جدول را بیرون بزند.
            return [max(1.0, value * scale) for value in minimums]

        # ستون‌های دارای متن بلند سهم بیشتری می‌گیرند؛ ستون توضیحات خالی فقط عرض سربرگ را می‌گیرد.
        weights = [max(1, n - m) for n, m in zip(natural, minimums)]
        remaining = width_budget - min_total
        weight_total = sum(weights)
        widths = [m + remaining * w / weight_total for m, w in zip(minimums, weights)]
        return widths

    def table(self, headers, rows, widths=None):
        """جدول راست‌به‌چپ؛ فونت هر ستون یکسان و شکست متن فقط بین کلمات است."""
        headers = [T(h) for h in headers] if headers else None
        rows = [list(row) for row in rows]
        count = len(headers) if headers else (len(rows[0]) if rows else 0)
        if count == 0:
            return Table([[]])
        # عرض‌های صریح هر ستون، اولویت اصلی‌اند؛ فقط اگر مجموعشان از عرض A4 افقی
        # بیشتر شود، همه به یک نسبت کوچک می‌شوند. در غیر این صورت الگوریتم حق
        # بازتوزیع عرض‌ها بر اساس طول داده‌ها را ندارد.
        page_budget = 794.0  # A4 افقی با حاشیه‌های ۲۴pt
        if widths and len(widths) == count and all(float(w) > 0 for w in widths):
            requested = [float(w) for w in widths]
            total_requested = sum(requested)
            scale = min(1.0, page_budget / total_requested)
            logical_widths = [w * scale for w in requested]
        else:
            logical_widths = self._fit_column_widths(headers, rows, page_budget)
        all_rows = ([headers] if headers else []) + rows
        column_sizes = self._column_font_sizes(all_rows, logical_widths)

        fitted_data = []
        for row in all_rows:
            fitted_row = []
            for index in range(count):
                raw = row[index] if index < len(row) else ""
                normalized = normalize_digits("" if raw is None else str(raw)).strip()
                is_date = bool(re.fullmatch(r"\d{4}[/.-]\d{1,2}[/.-]\d{1,2}", normalized))
                is_phone = bool(re.fullmatch(r"[+]?\d[\d\s().-]{7,}\d", normalized))
                # هیچ کاراکتر جهت‌دهی نامرئی به خروجی PDF اضافه نمی‌کنیم.
                # تاریخ و تلفن بدون LRM پردازش می‌شوند تا علامت‌های اضافی چاپ نشوند.
                value = str(raw) if (is_date or is_phone) else raw
                value = str(value).replace("\u200e", "").replace("\u200f", "")
                fitted_row.append(self._paragraph(
                    value, logical_widths[index], unbroken=(is_date or is_phone),
                    font_size=column_sizes[index],
                ))
            fitted_data.append(list(reversed(fitted_row)))

        table = Table(fitted_data, colWidths=list(reversed(logical_widths)), repeatRows=1 if headers else 0)
        style = [
            ("GRID", (0, 0), (-1, -1), 0.4, rl_colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if headers:
            style.append(("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor(self.HEADER_BG)))
        else:
            style.append(("BACKGROUND", (-1, 0), (-1, -1), rl_colors.HexColor("#f2f2f2")))
        table.setStyle(TableStyle(style))
        return table

    def build(self, target, story, pagesize=None, title=""):
        """ساخت و ذخیره PDF؛ این متد توسط ReportsMixin برای تمام گزارش‌ها فراخوانی می‌شود."""
        doc = SimpleDocTemplate(
            os.fspath(target),
            pagesize=pagesize or A4,
            rightMargin=24,
            leftMargin=24,
            topMargin=28,
            bottomMargin=28,
            title=title or "گزارش ساختمان",
        )
        doc.build(story)

    def summary_table(self, rows, pagesize):
        page_width, page_height = pagesize
        available_width = page_width - 48
        logical_rows = [list(row) for row in rows]
        logical_widths = self._fit_column_widths(None, logical_rows, available_width)
        column_sizes = self._column_font_sizes(logical_rows, logical_widths)
        data = []
        for row in logical_rows:
            fitted_row = []
            for index, value in enumerate(row):
                width = logical_widths[index] if index < len(logical_widths) else available_width / 2
                size = column_sizes[index] if index < len(column_sizes) else self.BASE_CELL_FONT
                fitted_row.append(self._paragraph(value, width, font_size=size))
            data.append(list(reversed(fitted_row)))

        table = Table(data, colWidths=list(reversed(logical_widths)))
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.6, rl_colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (-1, 0), (-1, -1), rl_colors.HexColor("#f2f2f2")),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table


# ----------------------------------------------------------------------
#  رنگ‌ها و گزارش‌ها
# ----------------------------------------------------------------------
PALETTES = {
    "light": {
        "bg": "#f0f0f0", "surface": "#f7f7f7", "card": "#ffffff", "input": "#ffffff",
        "fg": "#171717", "muted": "#666666", "border": "#c9c9c9", "accent": "#202020",
        "accent_fg": "#ffffff", "select_bg": "#dedede", "select_fg": "#111111", "stripe": "#f3f3f3",
        "warn": "#333333", "good": "#555555", "side_bg": "#e8e8e8", "side_fg": "#222222",
        "side_active": "#d0d0d0",
    },
    "dark": {
        "bg": "#171717", "surface": "#222222", "card": "#2b2b2b", "input": "#242424",
        "fg": "#f0f0f0", "muted": "#aaaaaa", "border": "#4a4a4a", "accent": "#eeeeee",
        "accent_fg": "#111111", "select_bg": "#4a4a4a", "select_fg": "#ffffff", "stripe": "#252525",
        "warn": "#f0f0f0", "good": "#cccccc", "side_bg": "#202020", "side_fg": "#eeeeee",
        "side_active": "#444444",
    },
}


def open_file(path):
    """فایل خروجی را بدون عبور دادن مسیر کاربر از shell باز می‌کند."""
    try:
        path = os.path.abspath(os.fspath(path))
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, TypeError, ValueError):
        # باز نشدن برنامه‌ی نمایش‌دهنده نباید عملیات ذخیره‌ی گزارش را ناموفق جلوه دهد.
        return


class ReportsMixin:
    """گزارش‌های PDF و خروجی Excel. (متن PDFها همیشه فارسی است.)"""

    def prepare_pdf(self):
        if not _load_reportlab():
            self.error("برای گزارش PDF نصب کنید:\npip install reportlab")
            return None
        # هر یک از ابزارهای شکل‌دهی در صورت نصب بودن مستقل از دیگری به کار گرفته می‌شود.
        # آزمون دستی: PDF فارسی را با هر دو وابستگی و سپس با حذف یکی از آن‌ها تولید کنید.
        try:
            import arabic_reshaper
        except ImportError as exc:
            arabic_reshaper = None
            AppLogger.warning(f"arabic-reshaper unavailable: {exc}")
        try:
            from bidi.algorithm import get_display
        except ImportError as exc:
            get_display = None
            AppLogger.warning(f"python-bidi unavailable: {exc}")

        def rtl_fn(value):
            text = "" if value is None else str(value)
            if arabic_reshaper is not None:
                text = arabic_reshaper.reshape(text)
            if get_display is not None:
                text = get_display(text, base_dir="R")
            return text
        if not register_pdf_font():
            self.error("فونت مناسب برای PDF پیدا نشد. فایل Vazirmatn.ttf را در پوشه‌ی fonts قرار دهید.")
            return None
        return PdfKit(rtl_fn)

    def ask_save(self, ext, initialfile, label):
        return filedialog.asksaveasfilename(parent=self, defaultextension=ext, initialfile=initialfile,
                                            filetypes=[(label, "*" + ext)])

    def default_export_sort_mode(self, table_kind):
        # پرداختی‌ها به‌صورت پیش‌فرض بر اساس شماره واحد؛ سایر جدول‌های تاریخ‌دار جدیدترین ابتدا.
        if any(field == "unit_asc" for field, _label in EXPORT_SORT_FIELDS.get(table_kind, [])):
            return "unit_asc"
        supports_date = any(field in ("date_asc", "date_desc")
                            for field, _label in EXPORT_SORT_FIELDS.get(table_kind, []))
        return "date_desc" if supports_date else "default"

    def export_sort_mode(self, output_kind, table_kind):
        saved = self.db.get(f"export_sort_{output_kind}_{table_kind}")
        if not saved or saved == "default":
            return self.default_export_sort_mode(table_kind)
        allowed = {field for field, _label in EXPORT_SORT_FIELDS.get(table_kind, [])}
        return saved if saved in allowed else self.default_export_sort_mode(table_kind)

    def sort_export_records(self, records, output_kind, table_kind, field_getter):
        mode = self.export_sort_mode(output_kind, table_kind)
        if mode == "default":
            return list(records)
        reverse = mode.endswith("_desc")
        field = mode.rsplit("_", 1)[0]
        def key(record):
            raw = field_getter(record, field)
            if field in ("amount", "balance"):
                try: return int(raw or 0)
                except (TypeError, ValueError): return 0
            if field == "date":
                parsed = parse_shamsi(raw)
                if parsed:
                    return parsed
                try: return (int(raw), 0, 0)
                except (TypeError, ValueError): return (0, 0, 0)
            if field == "unit":
                return natural_key(raw)
            return normalize_digits(raw).strip().lower()
        return sorted(records, key=key, reverse=reverse)

    def finish_report(self, kit, target, story, pagesize=None, title="", done="گزارش ایجاد شد.", done_args=()):
        try:
            kit.build(target, story, pagesize=pagesize, title=title)
        except ValueError as exc:
            return self.error(translate_error(exc))
        except Exception as exc:
            return self.error("ساخت یا ذخیره PDF ناموفق بود:\n{}", exc)
        self.info(done, *done_args)

    def header_block(self, kit, title):
        manager = self.db.get("manager")
        block = [kit.title(title), kit.sub(self.db.get("building_name"))]
        if manager:
            block.append(kit.sub(f"مدیر ساختمان: {manager}"))
        block.append(kit.space(10))
        return block

    # ---- سطرهای مشترک ----
    def payment_pdf_row(self, p, with_month=False):
        kind = p["payment_type"] if p["payment_type"] in (KIND_CHARGE, KIND_CONTRIB) else KIND_CHARGE
        st = self.db.statement(kind, p["year"], p["month"], p["unit_id"])
        unit = self.db.unit(p["unit_id"])
        row = [f"واحد {p['unit_number']}" if p["unit_number"] else "-", self.db.payer_name(unit, kind), T(p["payment_type"]),
               money(p["amount"]), money(st["share"]), money(st["prev_debt"]), money(st["prev_credit"]),
               money(st["payable"]), money(st["balance"]), p["paid_at"], p["notes"] or ""]
        return ([month_name(p["month"])] + row) if with_month else row

    def expense_pdf_row(self, e, with_month=False):
        acc = self.db.accounts()
        label = acc["pdf"][1] if (acc["multi"] and e["account"] == 2) else acc["pdf"][0]
        row = [label, e["paid_at"], e["category"] or "", money(e["amount"]), e["title"], e["notes"] or ""]
        return ([month_name(e["month"])] + row) if with_month else row

    def income_pdf_row(self, item, with_month=False):
        acc = self.db.accounts()
        account_name = acc["pdf"][1] if (acc["multi"] and item["account"] == 2) else acc["pdf"][0]
        row = [account_name, item["received_at"], money(item["amount"]), item["title"],
               item["notes"] or "", item["source"] or T("سایر")]
        return ([month_name(item["month"])] + row) if with_month else row

    PAYMENT_HEADERS = ["واحد", "نام", "نوع", "واریزی", "حق‌السهم", "بدهکاری ماه‌های قبل",
                       "بستانکاری ماه‌های قبل", "قابل واریز", "مانده حساب", "تاریخ", "توضیحات"]
    EXPENSE_HEADERS = ["نوع هزینه", "تاریخ", "دسته‌بندی", "مبلغ", "عنوان", "توضیحات"]
    INCOME_HEADERS = ["حساب مقصد", "تاریخ", "مبلغ", "عنوان", "توضیحات", "منبع درآمد"]

    def summary_rows(self, ov, acc):
        n1, n2 = acc["pdf"]
        o, e = ov["balances"]["open"], ov["balances"]["end"]
        rows = [(f"موجودی ابتدا {n1}", o[0])]
        if acc["multi"]:
            rows.append((f"موجودی ابتدا {n2}", o[1]))
        rows += [("شارژ مصرفی تعیین‌شده", ov["charge_assessed"]), (f"دریافتی شارژ مصرفی ({n1})", ov["charge_received"])]
        if acc["multi"]:
            rows += [(f"{n2} تعیین‌شده", ov["contrib_assessed"]), (f"دریافتی {n2}", ov["contrib_received"])]
        elif ov["contrib_assessed"] or ov["contrib_received"]:
            rows += [(f"{n2} تعیین‌شده", ov["contrib_assessed"]),
                     (f"دریافتی {n2} (حساب تجمیعی)", ov["contrib_received"])]
        rows.append((f"درآمدهای متفرقه ({n1})", ov["income1"]))
        if acc["multi"]:
            rows.append((f"درآمدهای متفرقه ({n2})", ov["income2"]))
        rows.append((f"هزینه‌ها از {n1}", ov["expense1"]))
        if acc["multi"]:
            rows.append((f"هزینه‌ها از {n2}", ov["expense2"]))
        rows.append((f"موجودی پایان {n1}", e[0]))
        if acc["multi"]:
            rows += [(f"موجودی پایان {n2}", e[1]), ("مجموع موجودی پایان", e[0] + e[1])]
        return rows

    # ---- گزارش ماهانه ----
    def pdf_month_report(self):
        kit = self.prepare_pdf()
        if kit is None:
            return
        y, m = self.year, self.month
        target = self.ask_save(".pdf", f"گزارش-{MONTHS[m - 1]}-{y}.pdf", "PDF")
        if not target:
            return
        acc = self.db.accounts()
        ov = self.db.overview(y, m)
        story = self.header_block(kit, f"گزارش مالی {MONTHS[m - 1]} {y}")
        summary = self.sort_export_records(self.summary_rows(ov, acc), "pdf_month", "summary",
            lambda item, f: {"amount": item[1], "label": item[0]}.get(f, ""))
        summary_page = landscape(A4)
        story.append(kit.section("خلاصه مالی", kit.summary_table(
            [(f"{money(v)} تومان", k) for k, v in summary], summary_page)))
        story.append(PageBreak())
        expense_records = self.sort_export_records(self.db.expenses(y, m), "pdf_month", "expenses",
            lambda e, f: {"amount": e["amount"], "date": e["paid_at"], "category": e["category"] or "",
                          "title": e["title"], "type": e["account"]}.get(f, ""))
        expenses = [self.expense_pdf_row(e) for e in expense_records]
        story.append(kit.section("هزینه‌ها", kit.table(self.EXPENSE_HEADERS, expenses or [["-"] * 6], [110, 70, 90, 80, 200, 235])))
        payment_records = list(self.db.payments(y, m))
        payment_records = self.sort_export_records(payment_records, "pdf_month", "payments",
            lambda p, f: {"unit": p["unit_number"] or "", "amount": p["amount"], "date": p["paid_at"],
                          "name": self.db.payer_name(self.db.unit(p["unit_id"]), p["payment_type"]),
                          "type": p["payment_type"]}.get(f, ""))
        payments = [self.payment_pdf_row(p) for p in payment_records]
        story.append(kit.section("دریافتی‌ها (شارژ مصرفی و شارژ مالکانه)", kit.table(self.PAYMENT_HEADERS, payments or [["-"] * 11],
                               [50, 95, 50, 65, 65, 70, 70, 65, 60, 80, 110])))
        # درآمدهای متفرقه در صفحه‌ای جدا و به‌عنوان آخرین بخش PDF قرار می‌گیرد.
        story.append(PageBreak())
        income_records = self.sort_export_records(self.db.incomes(y, m), "pdf_month", "incomes",
            lambda item, f: {"amount": item["amount"], "date": item["received_at"],
                             "title": item["title"], "type": item["account"]}.get(f, ""))
        incomes = [self.income_pdf_row(item) for item in income_records]
        story.append(kit.section("درآمدهای متفرقه", kit.table(self.INCOME_HEADERS, incomes or [["-"] * 6],
                                                               [110, 70, 90, 80, 200, 235])))
        self.finish_report(kit, target, story, pagesize=landscape(A4), title=f"گزارش {MONTHS[m - 1]} {y}")

    # ---- گزارش PDF چندماهه ----
    def pdf_multi_month_report(self):
        dialog = tk.Toplevel(self)
        dialog.title(T("انتخاب ماه‌های گزارش"))
        dialog.transient(self)
        dialog.resizable(False, False)
        selected = {m: tk.BooleanVar(value=False) for m in range(1, 13)}
        year_var = tk.StringVar(value=str(self.year))
        body = ttk.Frame(dialog, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=T("سال گزارش") + ":").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        year_spin = ttk.Spinbox(body, from_=1300, to=1600, textvariable=year_var, width=9, justify="center")
        year_spin.grid(row=0, column=1, sticky="w", padx=6, pady=6)
        months_box = ttk.LabelFrame(body, text=T("انتخاب ماه‌های گزارش"), padding=10)
        months_box.grid(row=1, column=0, columnspan=2, sticky="ew", pady=8)
        for m in range(1, 13):
            r, c = divmod(m - 1, 3)
            if i18n.rtl:
                c = 2 - c
            ttk.Checkbutton(months_box, text=T(MONTHS[m - 1]), variable=selected[m]).grid(
                row=r, column=c, sticky="w", padx=12, pady=5)
        actions = ttk.Frame(body)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        def set_all(value):
            for var in selected.values():
                var.set(value)
        ttk.Button(actions, text=T("انتخاب همه"), command=lambda: set_all(True)).pack(side=side_start(), padx=4)
        ttk.Button(actions, text=T("لغو انتخاب همه"), command=lambda: set_all(False)).pack(side=side_start(), padx=4)
        result = {}
        def accept():
            try:
                year = int(normalize_digits(year_var.get()))
            except ValueError:
                messagebox.showerror(T("خطا"), T("سال یا ماه معتبر نیست."), parent=dialog)
                return
            if not 1300 <= year <= 1600:
                messagebox.showerror(T("خطا"), T("سال یا ماه معتبر نیست."), parent=dialog)
                return
            months = [m for m, var in selected.items() if var.get()]
            if not months:
                messagebox.showwarning(T("توجه"), T("حداقل یک ماه را انتخاب کنید."), parent=dialog)
                return
            result.update(year=year, months=months)
            dialog.destroy()
        ttk.Button(actions, text=T("تأیید"), style="Accent.TButton", command=accept).pack(side=side_start(), padx=4)
        ttk.Button(actions, text=T("انصراف"), command=dialog.destroy).pack(side=side_start(), padx=4)
        dialog.bind("<Return>", lambda _e: accept())
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        dialog.update_idletasks()
        dialog.geometry(f"+{self.winfo_rootx() + max(0, (self.winfo_width()-dialog.winfo_reqwidth())//2)}+{self.winfo_rooty() + max(0, (self.winfo_height()-dialog.winfo_reqheight())//3)}")
        dialog.grab_set()
        self.wait_window(dialog)
        if not result:
            return

        kit = self.prepare_pdf()
        if kit is None:
            return
        year, months = result["year"], result["months"]
        month_labels = [month_name(m) for m in months]
        target = self.ask_save(".pdf", f"گزارش-مالی-{'-'.join(MONTHS[m-1] for m in months)}-{year}.pdf", "PDF")
        if not target:
            return
        acc = self.db.accounts()
        n1, n2 = acc["pdf"]
        flows = {m: self.db.flow(year, m) for m in months}
        totals = [sum(flows[m][i] for m in months) for i in range(6)]
        opening = self.db.balances(year, months[0])["open"]
        closing = self.db.balances(year, months[-1])["end"]
        rows = [(f"موجودی ابتدای دوره {n1}", opening[0])]
        if acc["multi"]:
            rows.append((f"موجودی ابتدای دوره {n2}", opening[1]))
        rows.append(("دریافتی شارژ مصرفی", totals[0]))
        if acc["multi"]:
            rows.append((f"دریافتی {n2}", totals[1]))
        elif totals[1]:
            rows.append((f"دریافتی {n2} (حساب تجمیعی)", totals[1]))
        rows.append((f"درآمدهای متفرقه ({n1})", totals[4]))
        if acc["multi"]:
            rows.append((f"درآمدهای متفرقه ({n2})", totals[5]))
        rows.append((f"هزینه‌ها از {n1}", totals[2]))
        if acc["multi"]:
            rows.append((f"هزینه‌ها از {n2}", totals[3]))
        rows.append((f"موجودی پایان دوره {n1}", closing[0]))
        if acc["multi"]:
            rows += [(f"موجودی پایان دوره {n2}", closing[1]), ("مجموع موجودی پایان دوره", closing[0] + closing[1])]

        period = "، ".join(month_labels)
        story = self.header_block(kit, f"گزارش مالی ماه‌های {period} {year}")
        rows = self.sort_export_records(rows, "pdf_multi", "summary",
            lambda item, f: {"amount": item[1], "label": item[0]}.get(f, ""))
        story.append(kit.section("خلاصه مالی دوره", kit.summary_table(
            [(f"{money(v)} تومان", k) for k, v in rows], landscape(A4))))
        story.append(PageBreak())

        monthly_records = []
        for m in months:
            f, b = flows[m], self.db.balances(year, m)["end"]
            monthly_records.append({"month": m, "values": [month_name(m), money(f[0]), money(f[1]),
                money(f[4] + f[5]), money(f[2] + f[3]), money(b[0] + b[1])]})
        monthly_records = self.sort_export_records(monthly_records, "pdf_multi", "trend",
            lambda item, f: {"date": item["month"], "amount": parse_money(item["values"][5])}.get(f, ""))
        story.append(kit.section("روند ماهانه", kit.table(
            ["ماه", "دریافتی شارژ مصرفی", f"دریافتی {n2}", "درآمد متفرقه", "هزینه‌ها", "موجودی پایان ماه"],
            [item["values"] for item in monthly_records], [90, 125, 125, 130, 140, 150])))

        placeholders = ",".join("?" for _ in months)
        params = (year, *months)
        categories_raw = self.db.q(
            f"SELECT category, SUM(amount) AS total FROM expenses WHERE year=? AND month IN ({placeholders}) GROUP BY category ORDER BY total DESC, category", params)
        category_records = self.sort_export_records(categories_raw, "pdf_multi", "categories",
            lambda item, f: {"amount": item["total"], "category": item["category"] or "-"}.get(f, ""))
        if category_records:
            story.append(kit.section("هزینه‌ها بر اساس دسته‌بندی", kit.table(
                ["دسته‌بندی", "مجموع"], [[r["category"] or "-", money(r["total"])] for r in category_records], [250, 150])))

        payments = self.db.q(
            f"SELECT p.*, u.number AS unit_number FROM payments p LEFT JOIN units u ON u.id=p.unit_id WHERE p.year=? AND p.month IN ({placeholders}) ORDER BY p.month, p.id", params)
        payment_groups = []
        for m in months:
            group = [p for p in payments if int(p["month"]) == m]
            group = self.sort_export_records(group, "pdf_multi", "payments",
                lambda p, f: {"unit": p["unit_number"] or "", "amount": p["amount"], "date": p["paid_at"],
                    "name": self.db.payer_name(self.db.unit(p["unit_id"]), p["payment_type"]), "type": p["payment_type"]}.get(f, ""))
            payment_groups.extend(group)
        story.append(kit.section("دریافتی‌های دوره", kit.table(["ماه"] + self.PAYMENT_HEADERS,
            [self.payment_pdf_row(p, with_month=True) for p in payment_groups] or [["-"] * 12],
            [55, 45, 90, 45, 62, 62, 65, 65, 62, 62, 58, 114])))

        expenses = self.db.q(
            f"SELECT * FROM expenses WHERE year=? AND month IN ({placeholders}) ORDER BY month, paid_at, id", params)
        expense_groups = []
        for m in months:
            group = [e for e in expenses if int(e["month"]) == m]
            group = self.sort_export_records(group, "pdf_multi", "expenses",
                lambda e, f: {"amount": e["amount"], "date": e["paid_at"], "category": e["category"] or "",
                    "title": e["title"], "type": e["account"]}.get(f, ""))
            expense_groups.extend(group)
        story.append(kit.section("هزینه‌های دوره", kit.table(["ماه"] + self.EXPENSE_HEADERS,
            [self.expense_pdf_row(e, True) for e in expense_groups] or [["-"] * 7],
            [60, 110, 65, 90, 80, 170, 210])))

        incomes = self.db.q(
            f"SELECT * FROM incomes WHERE year=? AND month IN ({placeholders}) ORDER BY month, received_at, id", params)
        income_groups = []
        for m in months:
            group = [item for item in incomes if int(item["month"]) == m]
            group = self.sort_export_records(group, "pdf_multi", "incomes",
                lambda item, f: {"amount": item["amount"], "date": item["received_at"],
                    "title": item["title"], "type": item["account"]}.get(f, ""))
            income_groups.extend(group)
        story.append(PageBreak())
        story.append(kit.section("درآمدهای متفرقه دوره", kit.table(["ماه"] + self.INCOME_HEADERS,
            [self.income_pdf_row(item, True) for item in income_groups] or [["-"] * 7],
            [60, 110, 65, 90, 80, 170, 210])))
        self.finish_report(kit, target, story, pagesize=landscape(A4),
            title=f"گزارش ماه‌های {period} {year}",
            done="گزارش مالی ماه‌های انتخاب‌شده سال {} با موفقیت ایجاد شد.", done_args=(year,))

    # ---- گزارش سالانه ----
    def pdf_annual_report(self):
        kit = self.prepare_pdf()
        if kit is None:
            return
        year = self.year
        target = self.ask_save(".pdf", f"گزارش-مالی-سال-{year}.pdf", "PDF")
        if not target:
            return
        acc = self.db.accounts()
        n1, n2 = acc["pdf"]
        flows = [self.db.flow(year, m) for m in range(1, 13)]
        totals = [sum(f[i] for f in flows) for i in range(6)]
        opening, closing = self.db.balances(year, 1)["open"], self.db.balances(year, 12)["end"]

        rows = [(f"موجودی ابتدای سال {n1}", opening[0])]
        if acc["multi"]:
            rows.append((f"موجودی ابتدای سال {n2}", opening[1]))
        rows.append(("دریافتی شارژ مصرفی", totals[0]))
        if acc["multi"]:
            rows.append((f"دریافتی {n2}", totals[1]))
        elif totals[1] or self.db.total_assessed(KIND_CONTRIB, year, 12):
            rows.append((f"دریافتی {n2} (حساب تجمیعی)", totals[1]))
        rows.append((f"درآمدهای متفرقه ({n1})", totals[4]))
        if acc["multi"]:
            rows.append((f"درآمدهای متفرقه ({n2})", totals[5]))
        rows.append((f"هزینه‌ها از {n1}", totals[2]))
        if acc["multi"]:
            rows.append((f"هزینه‌ها از {n2}", totals[3]))
        rows.append((f"موجودی پایان سال {n1}", closing[0]))
        if acc["multi"]:
            rows += [(f"موجودی پایان سال {n2}", closing[1]), ("مجموع موجودی پایان سال", closing[0] + closing[1])]

        story = self.header_block(kit, f"گزارش مالی سال {year}")
        rows = self.sort_export_records(rows, "pdf_annual", "summary",
            lambda item, f: {"amount": item[1], "label": item[0]}.get(f, ""))
        summary_page = landscape(A4)
        story.append(kit.section("خلاصه مالی سال", kit.summary_table(
            [(f"{money(v)} تومان", k) for k, v in rows], summary_page)))
        story.append(PageBreak())

        monthly_records = []
        for m in range(1, 13):
            f, b = flows[m - 1], self.db.balances(year, m)["end"]
            monthly_records.append({"month": m, "values": [MONTHS[m - 1], money(f[0]), money(f[1]),
                                      money(f[4] + f[5]), money(f[2] + f[3]), money(b[0] + b[1])]})
        monthly_records = self.sort_export_records(monthly_records, "pdf_annual", "trend",
            lambda item, f: {"date": item["month"], "amount": parse_money(item["values"][5])}.get(f, ""))
        monthly = [item["values"] for item in monthly_records]
        story.append(kit.section("روند ماهانه", kit.table(["ماه", "دریافتی شارژ مصرفی", f"دریافتی {n2}", "درآمد متفرقه", "هزینه‌ها", "موجودی پایان ماه"],
                            monthly, [90, 125, 125, 130, 140, 150])))
        category_records = self.sort_export_records(self.db.expense_by_category(year), "pdf_annual", "categories",
            lambda item, f: {"amount": item["total"], "category": item["category"] or "-"}.get(f, ""))
        categories = [[r["category"] or "-", money(r["total"])] for r in category_records]
        if categories:
            story.append(kit.section("هزینه‌ها بر اساس دسته‌بندی", kit.table(["دسته‌بندی", "مجموع"], categories, [250, 150])))

        payments = self.db.q("SELECT p.*, u.number AS unit_number FROM payments p LEFT JOIN units u ON u.id=p.unit_id "
                             "WHERE p.year=? ORDER BY p.month, p.id", (year,))
        # تمام تراکنش‌ها حتی در حالت تک‌حسابی در ریزگزارش باقی می‌مانند.
        payments = self.sort_export_records(payments, "pdf_annual", "payments",
            lambda p, f: {"unit": p["unit_number"] or "", "amount": p["amount"], "date": p["paid_at"],
                          "name": self.db.payer_name(self.db.unit(p["unit_id"]), p["payment_type"]),
                          "type": p["payment_type"]}.get(f, ""))
        # ماه همیشه معیار اصلی گروه‌بندی است؛ مرتب‌سازی انتخابی فقط داخل هر ماه اعمال می‌شود.
        payments.sort(key=lambda p: int(p["month"]))
        prow = [self.payment_pdf_row(p, with_month=True) for p in payments]
        story.append(kit.section("دریافتی‌های سال", kit.table(["ماه"] + self.PAYMENT_HEADERS, prow or [["-"] * 12],
                            [55, 45, 90, 45, 62, 62, 65, 65, 62, 62, 58, 114])))
        expenses = self.db.q("SELECT * FROM expenses WHERE year=? ORDER BY month, paid_at, id", (year,))
        expenses = self.sort_export_records(expenses, "pdf_annual", "expenses",
            lambda e, f: {"amount": e["amount"], "date": e["paid_at"], "category": e["category"] or "",
                          "title": e["title"], "type": e["account"]}.get(f, ""))
        story.append(kit.section("هزینه‌های سال", kit.table(["ماه"] + self.EXPENSE_HEADERS,
                            [self.expense_pdf_row(e, True) for e in expenses] or [["-"] * 7],
                            [60, 110, 65, 90, 80, 170, 210])))
        # درآمدهای متفرقه باید در آخرین صفحه‌ی گزارش سالانه باشند.
        story.append(PageBreak())
        annual_incomes = self.db.q("SELECT * FROM incomes WHERE year=? ORDER BY month, received_at, id", (year,))
        annual_incomes = self.sort_export_records(annual_incomes, "pdf_annual", "incomes",
            lambda item, f: {"amount": item["amount"], "date": item["received_at"],
                             "title": item["title"], "type": item["account"]}.get(f, ""))
        story.append(kit.section("درآمدهای متفرقه سال", kit.table(["ماه"] + self.INCOME_HEADERS,
            [self.income_pdf_row(item, True) for item in annual_incomes] or [["-"] * 7],
            [60, 110, 65, 90, 80, 170, 210])))
        self.finish_report(kit, target, story, pagesize=landscape(A4), title=f"گزارش سال {year}",
                           done="گزارش مالی سال {} با موفقیت ایجاد شد.", done_args=(year,))

    # ---- رسید پرداخت ----
    def pdf_receipt(self, payment_id):
        p = self.db.payment(payment_id)
        if p is None:
            return self.error("پرداخت پیدا نشد.")
        kit = self.prepare_pdf()
        if kit is None:
            return
        unit = self.db.unit(p["unit_id"])
        kind = p["payment_type"] if p["payment_type"] in (KIND_CHARGE, KIND_CONTRIB) else KIND_CHARGE
        st = self.db.statement(kind, p["year"], p["month"], p["unit_id"])
        number = unit["number"] if unit else "-"
        target = self.ask_save(".pdf", f"رسید-واحد-{number}-{p['id']}.pdf", "PDF")
        if not target:
            return
        acc = self.db.accounts()
        card = acc["names"][1] if (kind == KIND_CONTRIB and acc["multi"]) else acc["names"][0]
        details = [
            ("شماره رسید", str(p["id"])), ("تاریخ پرداخت", p["paid_at"]),
            ("دوره", f"{MONTHS[p['month'] - 1]} {p['year']}"), ("واحد", f"واحد {number}"),
            ("پرداخت‌کننده", self.db.payer_name(unit, kind) or "-"), ("نوع پرداخت", T(p["payment_type"])),
            ("واریز شده به", card),
            ("مبلغ پرداختی", f"{money(p['amount'])} تومان"), ("حق‌السهم این ماه", f"{money(st['share'])} تومان"),
            ("بدهکاری ماه‌های قبل", f"{money(st['prev_debt'])} تومان"),
            ("بستانکاری ماه‌های قبل", f"{money(st['prev_credit'])} تومان"),
            ("قابل واریز", f"{money(st['payable'])} تومان"), ("مانده حساب", f"{money(st['balance'])} تومان"),
            ("توضیحات", p["notes"] or "-"),
        ]
        # عنوان‌های رسید مستقیماً و بدون جایگزینی واژه‌ای استفاده می‌شوند.
        story = self.header_block(kit, "رسید پرداخت")
        story += [kit.table(None, [(v, k) for k, v in details], [210, 140]), kit.space(36),
                  kit.para("مهر و امضای مدیر ساختمان"), kit.space(30)]
        self.finish_report(kit, target, story, pagesize=A5, title="رسید پرداخت", done="رسید ایجاد شد.")

    # ---- لیست بدهکاران ----
    def debtor_rows(self, kind):
        rows = []
        for u in self.db.units():
            st = self.db.statement(kind, self.year, self.month, u["id"])
            if st["balance"] > 0:
                rows.append((u, st))
        return rows

    def pdf_debtors(self, kind):
        kit = self.prepare_pdf()
        if kit is None:
            return
        y, m = self.year, self.month
        target = self.ask_save(".pdf", f"بدهکاران-{MONTHS[m - 1]}-{y}.pdf", "PDF")
        if not target:
            return
        debtors = self.sort_export_records(self.debtor_rows(kind), "pdf_debtors", "debtors",
            lambda pair, f: {"unit": pair[0]["number"], "amount": pair[1]["balance"],
                             "name": self.db.payer_name(pair[0], kind), "balance": pair[1]["balance"]}.get(f, ""))
        rows = [[f"واحد {u['number']}", self.db.payer_name(u, kind), self.db.payer_phone(u, kind),
                 money(st["paid"]), money(st["share"]), money(st["prev_debt"]),
                 money(st["prev_credit"]), money(st["payable"]), money(st["balance"])]
                for u, st in debtors]
        total = sum(st["balance"] for _, st in debtors)
        account_names = self.db.accounts()["names"]
        what = account_names[0] if kind == KIND_CHARGE else account_names[1]
        debtor_table = kit.table(["واحد", "نام", "تلفن", "واریزی", "حق‌السهم", "بدهکاری ماه‌های قبل",
                                  "بستانکاری ماه‌های قبل", "قابل واریز", "مانده حساب"],
                                 rows or [["-"] * 9], [35, 82, 72, 57, 57, 67, 67, 62, 62])
        story = [KeepTogether(self.header_block(kit, f"لیست بدهکاران {what} — {MONTHS[m - 1]} {y}") + [debtor_table]),
                 kit.space(10), kit.para(f"جمع مانده: {money(total)} تومان")]
        self.finish_report(kit, target, story, pagesize=A4, title="لیست بدهکاران")

    # ---- Excel ----
    def excel_month(self):
        if not _load_openpyxl():
            return self.error("برای خروجی Excel نصب کنید:\npip install openpyxl")
        year, month = self.year, self.month
        target = self.ask_save(".xlsx", f"گزارش-{MONTHS[month - 1]}-{year}.xlsx", "Excel")
        if not target:
            return
        acc = self.db.accounts()
        wb = Workbook()
        summary_ws = wb.active
        summary_ws.title = "خلاصه مالی"
        summary_ws.append(["شرح", "مبلغ (تومان)"])
        overview = self.db.overview(year, month)
        for label, amount in self.summary_rows(overview, acc):
            summary_ws.append([label, amount])

        ws_payments = wb.create_sheet("دریافتی‌ها")
        ws_payments.append(self.PAYMENT_HEADERS)
        payments = self.db.payments(year, month)
        payments = self.sort_export_records(
            payments, "excel_month", "payments",
            lambda p, f: {"unit": p["unit_number"] or "", "amount": p["amount"],
                          "date": p["paid_at"], "name": self.db.payer_name(self.db.unit(p["unit_id"]), p["payment_type"]),
                          "type": p["payment_type"]}.get(f, ""))
        for payment in payments:
            row = self.payment_pdf_row(payment)
            ws_payments.append(row[:3] + [parse_money(v) if 3 <= i <= 8 else v
                                          for i, v in enumerate(row[3:], 3)])

        ws_expenses = wb.create_sheet("هزینه‌ها")
        ws_expenses.append(self.EXPENSE_HEADERS)
        expenses = self.sort_export_records(
            self.db.expenses(year, month), "excel_month", "expenses",
            lambda e, f: {"amount": e["amount"], "date": e["paid_at"],
                          "category": e["category"] or "", "title": e["title"],
                          "type": e["account"]}.get(f, ""))
        for expense in expenses:
            row = self.expense_pdf_row(expense)
            row[3] = expense["amount"]
            ws_expenses.append(row)

        ws_incomes = wb.create_sheet("درآمدهای متفرقه")
        ws_incomes.append(self.INCOME_HEADERS)
        incomes = self.sort_export_records(
            self.db.incomes(year, month), "excel_month", "incomes",
            lambda item, f: {"amount": item["amount"], "date": item["received_at"],
                             "title": item["title"], "type": item["account"]}.get(f, ""))
        for item in incomes:
            row = self.income_pdf_row(item)
            row[2] = item["amount"]
            ws_incomes.append(row)

        for sheet in wb.worksheets:
            # سرستون‌های Excel بدون جایگزینی واژه‌ای حفظ می‌شوند.
            sheet.sheet_view.rightToLeft = True
            for cell in sheet[1]:
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal="center")
            for column in sheet.columns:
                width = max((len(str(cell.value)) for cell in column if cell.value is not None), default=8)
                sheet.column_dimensions[column[0].column_letter].width = min(40, width + 4)
        try:
            wb.save(target)
        except OSError as exc:
            return self.error("ذخیره‌ی فایل انجام نشد:\n{}", exc)
        self.info("فایل Excel ایجاد شد.")

    def excel_annual(self):
        if not _load_openpyxl():
            return self.error("برای خروجی Excel نصب کنید:\npip install openpyxl")
        year = self.year
        target = self.ask_save(".xlsx", f"گزارش-سال-{year}.xlsx", "Excel")
        if not target:
            return
        acc = self.db.accounts()
        wb = Workbook()
        ws = wb.active
        ws.title = "خلاصه ماهانه"
        ws.append(["ماه", "دریافتی شارژ مصرفی", f"دریافتی {acc['pdf'][1]}", "درآمد متفرقه", "هزینه‌ها", "موجودی پایان ماه"])
        monthly_excel = []
        for m in range(1, 13):
            f, b = self.db.flow(year, m), self.db.balances(year, m)["end"]
            monthly_excel.append({"month": m, "values": [MONTHS[m - 1], f[0], f[1], f[4] + f[5], f[2] + f[3], b[0] + b[1]]})
        monthly_excel = self.sort_export_records(monthly_excel, "excel_annual", "monthly_summary",
            lambda item, f: {"date": item["month"]}.get(f, ""))
        for item in monthly_excel:
            ws.append(item["values"])
        ws2 = wb.create_sheet("دریافتی‌ها")
        ws2.append(["ماه"] + self.PAYMENT_HEADERS)
        excel_payments = self.db.q("SELECT p.*, u.number AS unit_number FROM payments p LEFT JOIN units u ON u.id=p.unit_id "
                                   "WHERE p.year=? ORDER BY p.month, p.id", (year,))
        # تمام تراکنش‌ها حتی در حالت تک‌حسابی در ریزگزارش باقی می‌مانند.
        excel_payments = self.sort_export_records(excel_payments, "excel_annual", "payments",
            lambda p, f: {"unit": p["unit_number"] or "", "amount": p["amount"], "date": p["paid_at"],
                          "name": self.db.payer_name(self.db.unit(p["unit_id"]), p["payment_type"]),
                          "type": p["payment_type"]}.get(f, ""))
        # در خروجی سالانه Excel نیز ماه معیار اصلی است و مرتب‌سازی درون هر ماه انجام می‌شود.
        excel_payments.sort(key=lambda p: int(p["month"]))
        for p in excel_payments:
            row = self.payment_pdf_row(p, with_month=True)
            ws2.append(row[:4] + [parse_money(v) if 4 <= i <= 9 else v for i, v in enumerate(row[4:], 4)])
        ws3 = wb.create_sheet("هزینه‌ها")
        ws3.append(["ماه"] + self.EXPENSE_HEADERS)
        excel_expenses = self.db.q("SELECT * FROM expenses WHERE year=? ORDER BY month, paid_at, id", (year,))
        excel_expenses = self.sort_export_records(excel_expenses, "excel_annual", "expenses",
            lambda e, f: {"amount": e["amount"], "date": e["paid_at"], "category": e["category"] or "",
                          "title": e["title"], "type": e["account"]}.get(f, ""))
        for e in excel_expenses:
            row = self.expense_pdf_row(e, True)
            row[4] = e["amount"]
            ws3.append(row)
        ws4 = wb.create_sheet("درآمدهای متفرقه")
        ws4.append(["ماه"] + self.INCOME_HEADERS)
        excel_incomes = self.db.q("SELECT * FROM incomes WHERE year=? ORDER BY month, received_at, id", (year,))
        excel_incomes = self.sort_export_records(excel_incomes, "excel_annual", "incomes",
            lambda item, f: {"amount": item["amount"], "date": item["received_at"],
                             "title": item["title"], "type": item["account"]}.get(f, ""))
        for item in excel_incomes:
            row = self.income_pdf_row(item, True)
            row[3] = item["amount"]
            ws4.append(row)
        for sheet in wb.worksheets:
            # سرستون‌های Excel بدون جایگزینی واژه‌ای حفظ می‌شوند.
            sheet.sheet_view.rightToLeft = True
            for cell in sheet[1]:
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal="center")
            for column in sheet.columns:
                width = max((len(str(c.value)) for c in column if c.value is not None), default=8)
                sheet.column_dimensions[column[0].column_letter].width = min(40, width + 4)
        try:
            wb.save(target)
        except OSError as exc:
            return self.error("ذخیره‌ی فایل انجام نشد:\n{}", exc)
        self.info("فایل Excel ایجاد شد.")


# ----------------------------------------------------------------------
#  پنجره‌ی اصلی
# ----------------------------------------------------------------------
NAV = [("dashboard", "صفحه اصلی"), ("month", "ثبت ماهانه"), ("units", "مدیریت واحدها"),
       ("debtors", "بدهکاران"), ("settings", "تنظیمات")]



__all__ = [name for name in globals() if not name.startswith('__')]
