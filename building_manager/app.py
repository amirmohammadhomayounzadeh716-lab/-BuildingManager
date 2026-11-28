from .reports import *

class App(tk.Tk, ReportsMixin):
    def __init__(self):
        super().__init__()
        self.db = Database()
        i18n.set_language(self.db.get("language"))
        self.year, self.month = current_shamsi_year(), current_shamsi_month()
        self.page, self.tab = "dashboard", "summary"
        self.show_inactive = tk.BooleanVar(value=False)
        self.debt_kind = KIND_CHARGE
        self.font_family = self._pick_font()
        self.geometry("1280x800")
        # اجازه‌ی کوچک شدن پنجره روی نمایشگرهای کوچک؛ دسترسی به محتوا با اسکرول سراسری
        self.minsize(720, 480)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.reload_preferences(first=True)

    def _show_import_warning(self):
        # کد خطا باید از ERROR_MESSAGES خوانده شود، نه از جدول ترجمه‌ی متن‌های UI.
        # آزمون دستی: translate_error("json-import-failed") باید قالب فارسی شامل {} را برگرداند.
        detail = self.db.import_error
        if not detail:
            return
        self.db.import_error = None
        messagebox.showwarning(
            T("هشدار"),
            translate_error("json-import-failed").format(detail),
            parent=self,
        )

    # ------------------------------------------------------------------
    #  ظاهر و چیدمان کلی
    # ------------------------------------------------------------------
    def _pick_font(self):
        available = set(tkfont.families(self))
        for name in ("Vazirmatn", "Tahoma", "Segoe UI", "DejaVu Sans", "Arial"):
            if name in available:
                return name
        return "Helvetica"

    def reload_preferences(self, first=False):
        """زبان، تم و اندازه‌ی قلم را از تنظیمات می‌خواند و کل پنجره را دوباره می‌سازد."""
        i18n.set_language(self.db.get("language"))
        # تغییر زبان در تنظیمات باید فونت پیش‌فرض را نیز هم‌زمان به‌روزرسانی کند.
        self.font_family = self._pick_font()
        self.apply_theme()
        self.title(T("مدیریت ساختمان"))
        self.build_menu()
        self.build_shell()
        self.render()

    def apply_theme(self):
        large = self.db.get("font_size") == "large"
        self.colors = c = dict(PALETTES["dark" if self.db.get("appearance") == "dark" else "light"])
        base = 11 if large else 9
        fam = self.font_family
        s = self.style
        self.configure(bg=c["bg"])
        s.configure(".", background=c["bg"], foreground=c["fg"], font=(fam, base), bordercolor=c["border"],
                    lightcolor=c["border"], darkcolor=c["border"], troughcolor=c["bg"], focuscolor=c["accent"])
        s.configure("TFrame", background=c["bg"])
        s.configure("Card.TFrame", background=c["card"], relief="solid", borderwidth=1)
        s.configure("Side.TFrame", background=c["side_bg"])
        s.configure("TLabel", background=c["bg"], foreground=c["fg"])
        s.configure("Bold.TLabel", font=(fam, base, "bold"))
        s.configure("Header.TLabel", font=(fam, base + 7, "bold"))
        s.configure("Footer.TLabel", foreground=c["muted"], font=(fam, base, "bold"))
        s.configure("Muted.TLabel", foreground=c["muted"])
        s.configure("CardTitle.TLabel", background=c["card"], foreground=c["muted"])
        s.configure("Value.TLabel", background=c["card"], foreground=c["fg"], font=(fam, base + 3, "bold"))
        s.configure("ValueWarn.TLabel", background=c["card"], foreground=c["warn"], font=(fam, base + 3, "bold"))
        s.configure("ValueGood.TLabel", background=c["card"], foreground=c["good"], font=(fam, base + 3, "bold"))
        s.configure("CardText.TLabel", background=c["card"], foreground=c["fg"])
        s.configure("SideTitle.TLabel", background=c["side_bg"], foreground=c["side_fg"], font=(fam, base + 3, "bold"))
        s.configure("SideSub.TLabel", background=c["side_bg"], foreground=c["side_fg"], font=(fam, base - 1))
        s.configure("TButton", background=c["card"], foreground=c["fg"], padding=(8, 4), borderwidth=1)
        s.map("TButton", background=[("active", c["select_bg"]), ("pressed", c["select_bg"])],
              foreground=[("disabled", c["muted"])])
        s.configure("Accent.TButton", background=c["accent"], foreground=c["accent_fg"], padding=(9, 4))
        s.map("Accent.TButton", background=[("active", c["side_active"])], foreground=[("active", "#ffffff")])
        s.configure("Nav.TButton", background=c["side_bg"], foreground=c["side_fg"], borderwidth=0,
                    padding=(11, 8), anchor="center", font=(fam, base + 1))
        s.map("Nav.TButton", background=[("active", c["side_active"])], foreground=[("active", "#ffffff")])
        s.configure("NavActive.TButton", background=c["side_active"], foreground="#ffffff", borderwidth=0,
                    padding=(11, 8), anchor="center", font=(fam, base + 1, "bold"))
        s.configure("TEntry", fieldbackground=c["input"], foreground=c["fg"], insertcolor=c["fg"], padding=3)
        s.configure("TCombobox", fieldbackground=c["input"], background=c["card"], foreground=c["fg"],
                    arrowcolor=c["fg"], padding=3)
        s.map("TCombobox", fieldbackground=[("readonly", c["input"])], foreground=[("readonly", c["fg"])],
              selectbackground=[("readonly", c["input"])], selectforeground=[("readonly", c["fg"])])
        s.configure("TSpinbox", fieldbackground=c["input"], foreground=c["fg"], arrowcolor=c["fg"], padding=3)
        s.configure("TCheckbutton", background=c["bg"], foreground=c["fg"])
        s.configure("TRadiobutton", background=c["bg"], foreground=c["fg"])
        s.configure("TLabelframe", background=c["bg"], bordercolor=c["border"])
        s.configure("TLabelframe.Label", background=c["bg"], foreground=c["fg"], font=(fam, base, "bold"))
        s.configure("TNotebook", background=c["bg"], bordercolor=c["border"])
        s.configure("TNotebook.Tab", background=c["card"], foreground=c["fg"], padding=(11, 6))
        s.map("TNotebook.Tab", background=[("selected", c["surface"]), ("active", c["select_bg"])])
        s.configure("Treeview", background=c["surface"], fieldbackground=c["surface"], foreground=c["fg"],
                    rowheight=34 if large else 28, font=(fam, base))
        s.map("Treeview", background=[("selected", c["select_bg"])], foreground=[("selected", c["select_fg"])])
        s.configure("Treeview.Heading", background=c["card"], foreground=c["fg"], font=(fam, base, "bold"), padding=5)
        s.map("Treeview.Heading", background=[("active", c["select_bg"])])
        s.configure("TScrollbar", background=c["card"], arrowcolor=c["fg"], troughcolor=c["bg"])
        # لیست بازشوی کمبوباکس‌ها
        self.option_add("*TCombobox*Listbox.background", c["input"])
        self.option_add("*TCombobox*Listbox.foreground", c["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", c["select_bg"])
        self.option_add("*TCombobox*Listbox.selectForeground", c["select_fg"])
        self.option_add("*TCombobox*Listbox.font", "{%s} %d" % (fam, base))

    def build_menu(self):
        c = self.colors
        opts = dict(bg=c["surface"], fg=c["fg"], activebackground=c["select_bg"], activeforeground=c["select_fg"])
        menu = tk.Menu(self, tearoff=False, **opts)
        file_menu = tk.Menu(menu, tearoff=False, **opts)
        file_menu.add_command(label=T("پشتیبان‌گیری"), command=self.do_backup)
        file_menu.add_command(label=T("بازیابی پشتیبان"), command=self.do_restore)
        file_menu.add_separator()
        file_menu.add_command(label=T("خروج"), command=self.on_close)
        menu.add_cascade(label=T("پرونده"), menu=file_menu)
        menu.add_command(label=T("دسته‌بندی‌ها"), command=self.manage_categories)
        menu.add_command(label=T("تنظیمات"), command=lambda: self.show("settings"))
        help_menu = tk.Menu(menu, tearoff=False, **opts)
        help_menu.add_command(label=T("راهنمای استفاده"), command=lambda: self.show("help"))
        help_menu.add_separator()
        help_menu.add_command(label=T("گزارش خطاها"), command=self.show_error_log)
        menu.add_cascade(label=T("راهنما"), menu=help_menu)
        self.config(menu=menu)

    def build_shell(self):
        for child in self.winfo_children():
            if not isinstance(child, tk.Menu):
                child.destroy()
        top = ttk.Frame(self, style="TFrame")
        top.pack(side="top", fill="x", padx=12, pady=(10, 4))
        ttk.Label(top, text=self.db.get("building_name"), style="Bold.TLabel").pack(side="right" if i18n.rtl else "left", padx=8)
        self.nav = {}
        nav_row = ttk.Frame(self, style="TFrame")
        nav_row.pack(side="top", fill="x", padx=12, pady=(2, 8))
        for key, label in NAV:
            button = ttk.Button(nav_row, text=T(label), style="Nav.TButton", command=lambda k=key: self.show(k))
            button.pack(side="right" if i18n.rtl else "left", padx=3, pady=2)
            self.nav[key] = button
        # محتوای صفحات معمولی اسکرول سراسری ندارد؛ صفحه‌ی خانه در render
        # یک اسکرول موقت و مستقل می‌گیرد که با خروج از خانه کاملاً حذف می‌شود.
        self.content = ttk.Frame(self, style="TFrame")
        self.content.pack(side="top", fill="both", expand=True)

        # ویل موس فقط به نزدیک‌ترین کنترل اسکرول‌پذیرِ زیر نشانگر متصل می‌شود.
        # اگر زیر نشانگر اسکرولی وجود نداشته باشد، هیچ بخشی حرکت نمی‌کند.
        # bind_all بدون add="+" اتصال قبلی همین رویداد را جایگزین می‌کند؛
        # بنابراین با بازسازی پوسته، callbackهای تکراری روی هم انباشته نمی‌شوند.
        self.bind_all("<MouseWheel>", self._scroll_under_pointer)
        self.bind_all("<Button-4>", self._scroll_under_pointer)
        self.bind_all("<Button-5>", self._scroll_under_pointer)

    
    def _scroll_under_pointer(self, event):
        """ویل موس را فقط به نزدیک‌ترین کنترل اسکرول‌پذیر زیر نشانگر می‌فرستد."""
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
            if widget is None:
                return None

            # نزدیک‌ترین کنترل اسکرول‌پذیر را در زنجیره والدها پیدا کن.
            target = None
            probe = widget

            while probe is not None:
                if probe.winfo_class() in (
                    "Canvas", "Text", "Treeview", "Listbox"
                ):
                    if (
                        callable(getattr(probe, "yview", None))
                        and callable(getattr(probe, "yview_scroll", None))
                    ):
                        target = probe
                        break

                probe = getattr(probe, "master", None)

            if target is None:
                return None

            # اگر محتوای اضافه‌ای برای اسکرول وجود ندارد، کاری نکن.
            first, last = target.yview()
            if first <= 0 and last >= 1:
                return None

            # تشخیص جهت حرکت در ویندوز و لینوکس
            delta = getattr(event, "delta", 0)
            number = getattr(event, "num", None)

            if delta:
                units = (
                    int(-delta / 120)
                    if abs(delta) >= 120
                    else (-1 if delta > 0 else 1)
                )
            elif number == 4:
                units = -1
            elif number == 5:
                units = 1
            else:
                return None

            target.yview_scroll(units, "units")
            return "break"

        except (tk.TclError, AttributeError, TypeError):
            return None


    def show(self, page):
        self.page = page
        self.render()

    def render(self):
        for child in self.content.winfo_children():
            child.destroy()
        for key, button in self.nav.items():
            button.configure(style="NavActive.TButton" if key == self.page else "Nav.TButton")

        if self.page == "dashboard":
            # فقط صفحه‌ی خانه داخل Canvas قرار می‌گیرد. اسکرول‌بار تا زمانی
            # که محتوای خانه از ارتفاع قابل نمایش بیشتر نباشد، پنهان است.
            holder = ttk.Frame(self.content, style="TFrame")
            holder.pack(fill="both", expand=True)
            canvas = tk.Canvas(
                holder, bg=self.colors["bg"], highlightthickness=0, bd=0
            )
            scrollbar = ttk.Scrollbar(
                holder, orient="vertical", command=canvas.yview
            )
            scrollbar.pack(side=side_end(), fill="y")
            canvas.pack(side=side_start(), fill="both", expand=True)
            canvas.configure(yscrollcommand=_autohide_scrollbar(scrollbar))

            home_content = ttk.Frame(canvas, style="TFrame")
            window_id = canvas.create_window(
                (0, 0), window=home_content, anchor="nw"
            )

            def update_home_region(_event=None):
                bbox = canvas.bbox("all")
                canvas.configure(scrollregion=bbox if bbox else (0, 0, 0, 0))

            def resize_home_content(event):
                canvas.itemconfigure(window_id, width=event.width)

            home_content.bind("<Configure>", update_home_region)
            canvas.bind("<Configure>", resize_home_content)
            self._home_canvas = canvas
            getattr(self, "page_dashboard")(home_content)
            update_home_region()
        else:
            # با رفتن به هر صفحه‌ی دیگر، Canvas و اسکرول‌بار صفحه‌ی خانه
            # همراه همان صفحه نابود می‌شوند و دیگر وجود ندارند.
            self._home_canvas = None
            getattr(self, "page_" + self.page)(self.content)

    # ------------------------------------------------------------------
    #  پیام‌ها
    # ------------------------------------------------------------------
    def info(self, message, *args):
        messagebox.showinfo(T("توجه"), T(message, *args), parent=self)

    def warn(self, message, *args):
        messagebox.showwarning(T("هشدار"), T(message, *args), parent=self)

    def error(self, message, *args):
        raw = str(message)
        if raw in ERROR_MESSAGES or re.fullmatch(r"[a-z0-9_-]+", raw):
            message = translate_error(raw)
            args = ()
        else:
            args = tuple(
                translate_error(arg)
                if isinstance(arg, (ValueError, str)) and
                   (str(arg) in ERROR_MESSAGES or re.fullmatch(r"[a-z0-9_-]+", str(arg)))
                else arg
                for arg in args
            )
        messagebox.showerror(T("خطا"), T(message, *args), parent=self)

    def show_error_log(self):
        win = tk.Toplevel(self)
        win.title(T("گزارش خطاها"))
        win.geometry("850x520")
        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        text = tk.Text(frame, wrap="word", font=(self.font_family, 10))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        try:
            with open(LOG_PATH, "r", encoding="utf-8") as log_file:
                content = log_file.read()
        except OSError:
            content = "هنوز گزارشی ثبت نشده است."
        text.insert("1.0", content)
        text.configure(state="disabled")

        buttons = ttk.Frame(win)
        buttons.pack(fill="x", padx=10, pady=(0, 10))

        def clear_log():
            try:
                AppLogger._setup()
                for handler in list(AppLogger._logger.handlers):
                    handler.acquire()
                    try:
                        handler.flush()
                        handler.close()
                        AppLogger._logger.removeHandler(handler)
                    finally:
                        handler.release()
                for suffix in ("", ".1", ".2", ".3", ".4", ".5", ".6", ".7", ".8", ".9", ".10"):
                    candidate = LOG_PATH + suffix
                    if os.path.exists(candidate):
                        os.remove(candidate)
                AppLogger._configured = False
                AppLogger._setup()
                text.configure(state="normal")
                text.delete("1.0", "end")
                text.configure(state="disabled")
            except OSError as exc:
                AppLogger.exception(f"Could not clear log: {exc}")
                messagebox.showerror(T("خطا"), "پاک کردن گزارش خطاها ممکن نشد.", parent=win)

        def copy_log():
            try:
                win.clipboard_clear()
                win.clipboard_append(text.get("1.0", "end-1c"))
            except tk.TclError as exc:
                AppLogger.exception(f"Could not copy log: {exc}")

        ttk.Button(buttons, text="پاک کردن لاگ", command=clear_log).pack(side="right", padx=4)
        ttk.Button(buttons, text="کپی", command=copy_log).pack(side="right", padx=4)
        ttk.Button(buttons, text=T("بستن"), command=win.destroy).pack(side="left", padx=4)


    def page_help(self, parent):
        """راهنمای متنی برنامه با بخش‌های بازشونده و ناحیه‌ی اسکرول‌پذیر."""
        self.page_title(parent, T("راهنمای استفاده"))
        ttk.Label(
            parent,
            text="برای مشاهده‌ی توضیحات هر قسمت، روی عنوان آن کلیک کنید.",
            style="Muted.TLabel",
        ).pack(anchor=text_anchor(), padx=22, pady=(0, 8))

        holder = ttk.Frame(parent)
        holder.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        canvas = tk.Canvas(holder, bg=self.colors["bg"], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        canvas.configure(yscrollcommand=_autohide_scrollbar(scrollbar))
        scrollbar.pack(side=side_end(), fill="y")
        canvas.pack(side=side_start(), fill="both", expand=True)

        sections = [
            ("شروع سریع و آشنایی با محیط برنامه",
             "پس از اجرای برنامه، صفحه‌ی اصلی نمای کلی ساختمان و وضعیت مالی را نشان می‌دهد. برای دیدن اطلاعات یک ماه، سال موردنظر را انتخاب کنید و روی کارت همان ماه بزنید. در صفحه‌ی ماهانه، زبانه‌های خلاصه مالی، شارژ و پرداختی‌ها، هزینه‌ها و درآمدهای متفرقه در دسترس هستند."),
            ("مدیریت واحدها",
             "از منوی اصلی وارد «مدیریت واحدها» شوید. با گزینه‌ی «افزودن واحد» شماره واحد، طبقه، اطلاعات مالک و در صورت وجود مستأجر را ثبت کنید. برای تغییر اطلاعات، واحد را انتخاب و «ویرایش واحد» را بزنید. اگر واحد سابقه‌ی مالی داشته باشد، برای حفظ تاریخچه به‌جای حذف کامل غیرفعال می‌شود. واحدهای غیرفعال را می‌توانید با گزینه‌ی نمایش واحدهای غیرفعال ببینید."),
            ("تعیین شارژ و مبلغ پرداختی هر واحد",
             "در صفحه‌ی ماهانه و زبانه‌ی خلاصه مالی، مبلغ پیش‌فرض شارژ هر واحد را وارد و ذخیره کنید. در صورت نیاز می‌توانید مبلغ را تا پایان سال اعمال کنید یا برای واحدهای مختلف مبلغ جداگانه تعیین کنید. اگر حساب دوم فعال باشد، تنظیمات آن نیز جداگانه نمایش داده می‌شود."),
            ("ثبت واریزی‌ها و پرداخت‌های واحدها",
             "در زبانه‌ی «شارژ و پرداختی‌ها»، گزینه‌ی «ثبت پرداخت جدید» را انتخاب کنید. سپس واحد، نوع پرداخت، مبلغ، تاریخ و توضیحات را وارد کنید. برای اصلاح یا حذف یک رکورد، ابتدا آن را از جدول انتخاب کنید و گزینه‌ی مربوط را بزنید. با انتخاب یک ردیف می‌توانید رسید پرداخت آن را نیز تهیه کنید. مبلغ صفر هم برای ثبت پرداخت قابل استفاده است."),
            ("ثبت و مدیریت هزینه‌ها",
             "در زبانه‌ی «هزینه‌ها»، گزینه‌ی «ثبت هزینه جدید» را بزنید و عنوان، دسته‌بندی، مبلغ، تاریخ، حساب پرداخت‌کننده و توضیحات را وارد کنید. برای افزودن یا مدیریت دسته‌بندی‌ها از گزینه‌ی «دسته‌بندی‌ها» استفاده کنید. هزینه‌های ثبت‌شده در جدول همان ماه نمایش داده می‌شوند."),
            ("ثبت درآمدهای متفرقه",
             "در زبانه‌ی «درآمدهای متفرقه»، گزینه‌ی «ثبت درآمد جدید» را انتخاب کنید. عنوان درآمد، مبلغ، تاریخ دریافت، منبع درآمد و حساب مقصد را مشخص کنید. این بخش برای درآمدهایی است که در قالب واریزی شارژ یا پرداختی واحدها ثبت نمی‌شوند."),
            ("بررسی بدهکاران و مانده حساب",
             "از بخش «بدهکاران» می‌توانید وضعیت واحدها را بررسی کنید؛ از جمله مبالغ پرداخت‌شده، سهم تعیین‌شده، بدهی یا بستانکاری ماه‌های قبل و مانده حساب. در صورت فعال بودن چندحسابی، نوع حساب را نیز انتخاب کنید. برای نگهداری یا چاپ فهرست بدهکاران، خروجی PDF همین بخش را تهیه کنید."),
            ("گزارش‌گیری PDF و Excel",
             "در صفحه‌ی اصلی، گزارش PDF سالانه و چندماهه و خروجی Excel سالانه در دسترس است. در خلاصه مالی هر ماه نیز می‌توانید گزارش PDF و فایل Excel همان ماه را بسازید. برای گزارش چندماهه، ماه‌های موردنظر را انتخاب کنید؛ بازه‌های انتخابی باید پیوسته باشند. گزارش PDF بدهکاران نیز از بخش بدهکاران قابل تهیه است."),
            ("تنظیمات برنامه",
             "از منوی «تنظیمات» می‌توانید نام و مشخصات ساختمان، اطلاعات مدیر، موجودی اولیه حساب‌ها، اندازه قلم، پوسته روشن یا تیره، زبان رابط کاربری و فعال یا غیرفعال بودن حالت چندحسابی را تغییر دهید. تنظیمات ترتیب جدول‌های خروجی PDF و Excel نیز در همین بخش قرار دارد. پس از تغییر، «ذخیره کلیه تغییرات تنظیمات» را انتخاب کنید."),
            ("پشتیبان‌گیری و بازیابی اطلاعات",
             "برای تهیه نسخه پشتیبان، از منوی «پرونده» گزینه‌ی «پشتیبان‌گیری» را انتخاب و محل ذخیره فایل را مشخص کنید. برای برگرداندن اطلاعات، «بازیابی پشتیبان» را بزنید و فایل پشتیبان را انتخاب کنید؛ توجه داشته باشید که بازیابی، اطلاعات فعلی را با اطلاعات فایل پشتیبان جایگزین می‌کند. برنامه هنگام خروج نیز پشتیبان‌گیری خودکار انجام می‌دهد. بهتر است نسخه‌های پشتیبان را در محل دیگری هم نگه دارید."),
            ("سؤالات رایج",
             "• آیا برای استفاده از برنامه اینترنت لازم است؟ خیر؛ برنامه برای استفاده‌ی عادی آفلاین است.\n• اطلاعات کجا ذخیره می‌شوند؟ به‌صورت محلی در پوشه‌ی داده‌های BuildingManager در پروفایل کاربر ویندوز.\n• اگر اشتباهاً اطلاعاتی را حذف یا تغییر دادم چه کنم؟ در صورت داشتن فایل پشتیبان سالم، از گزینه‌ی بازیابی استفاده کنید.\n• چرا بعضی گزینه‌ها را نمی‌بینم؟ برخی گزینه‌ها، مانند حساب دوم، فقط در صورت فعال بودن حالت چندحسابی نمایش داده می‌شوند.\n• اگر برنامه خطا داد چه کنم؟ از منوی «راهنما» گزینه‌ی «گزارش خطاها» را باز کنید و متن گزارش را برای بررسی نگه دارید.")
        ]

        for title, description in sections:
            section = ttk.Frame(content, style="Card.TFrame", padding=(8, 7))
            section.pack(fill="x", padx=6, pady=4)
            panel = ttk.Frame(section, style="Card.TFrame", padding=(12, 8))
            state = {"open": False}
            button = ttk.Button(section, text="＋ " + title, style="TButton")
            button.configure(command=lambda p=panel, st=state, b=button, t=title, d=description:
                             self._toggle_help_section(p, st, b, t, d, content))
            button.pack(fill="x")

    def _toggle_help_section(self, panel, state, button, title, description, content):
        """باز و بسته کردن یک بخش از راهنمای استفاده."""
        if state["open"]:
            panel.pack_forget()
            state["open"] = False
            button.configure(text="＋ " + title)
            return

        for child in panel.winfo_children():
            child.destroy()
        label = ttk.Label(
            panel,
            text=description,
            justify="right" if i18n.rtl else "left",
            anchor=text_anchor(),
            wraplength=max(320, content.winfo_width() - 60),
            style="CardText.TLabel",
        )
        label.pack(fill="x", anchor=text_anchor())
        panel.pack(fill="x", padx=2, pady=(5, 2))
        state["open"] = True
        button.configure(text="− " + title)

    def report_callback_exception(self, exc_type, exc_value, exc_tb):
        AppLogger.log("error", "Tk callback exception", exc_info=(exc_type, exc_value, exc_tb))
        if not _STARTUP_COMPLETE:
            _print_exception_to_console(
                exc_type, exc_value, exc_tb,
                context="Tk callback failed before the main window was ready",
            )
            return
        try:
            friendly = (
                translate_error(exc_value)
                if isinstance(exc_value, ValueError) else
                "عملیات انجام نشد. جزئیات در «راهنما ← گزارش خطاها» ثبت شد."
            )
            messagebox.showerror(T("خطا"), friendly, parent=self)
        except Exception:
            pass

    def confirm(self, message, *args):
        return messagebox.askyesno(T("تأیید"), T(message, *args), parent=self)

    # ------------------------------------------------------------------
    #  ابزارهای ساخت صفحه
    # ------------------------------------------------------------------
    def page_title(self, parent, text):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", padx=20, pady=(16, 4))
        ttk.Label(frame, text=text, style="Header.TLabel").pack(side=side_start())
        return frame

    def toolbar(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=12, pady=(8, 4))
        return bar

    def tool_button(self, bar, text, command, accent=False):
        button = ttk.Button(bar, text=T(text), command=command, style="Accent.TButton" if accent else "TButton")
        button.pack(side=side_start(), padx=4)
        return button

    def stat_card(self, parent, title, value, row, col, tone="Value"):
        card = ttk.Frame(parent, style="Card.TFrame", padding=(14, 10))
        card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
        ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor=text_anchor())
        ttk.Label(card, text=value, style=tone + ".TLabel").pack(anchor=text_anchor(), pady=(4, 0))
        parent.columnconfigure(col, weight=1)
        return card

    def unit_text(self, number):
        return T("واحد {}", number)

    def unit_choice_label(self, unit):
        if unit and unit["status"] == ST_TENANT:
            tenant = (unit["tenant"] or "").strip()
            owner = (unit["owner"] or "").strip()
            if tenant and owner:
                return f"{self.unit_text(unit['number'])}  —  مستأجر: {tenant} | مالک: {owner}"
        name = self.db.payer_name(unit)
        return f"{self.unit_text(unit['number'])}  —  {name}" if name else self.unit_text(unit["number"])

    def month_bar(self, parent, on_change):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=20, pady=(14, 6))
        names = [month_name(i) for i in range(1, 13)]
        month_var, year_var = tk.StringVar(value=names[self.month - 1]), tk.IntVar(value=self.year)

        def move(delta):
            self.month += delta
            if self.month == 0:
                self.month, self.year = 12, self.year - 1
            elif self.month == 13:
                self.month, self.year = 1, self.year + 1
            on_change()

        def pick_month(_event=None):
            self.month = names.index(month_var.get()) + 1
            on_change()

        def pick_year(_event=None):
            try:
                value = int(year_var.get())
            except (tk.TclError, ValueError):
                return
            if 1300 <= value <= 1600 and value != self.year:
                self.year = value
                on_change()

        ttk.Button(bar, text=T("ماه قبل"), command=lambda: move(-1)).pack(side=side_start(), padx=3)
        combo = ttk.Combobox(bar, textvariable=month_var, values=names, state="readonly", width=12)
        combo.pack(side=side_start(), padx=3)
        combo.bind("<<ComboboxSelected>>", pick_month)
        spin = ttk.Spinbox(bar, from_=1300, to=1600, textvariable=year_var, width=7, command=pick_year)
        spin.pack(side=side_start(), padx=3)
        spin.bind("<Return>", pick_year)
        ttk.Button(bar, text=T("ماه بعد"), command=lambda: move(1)).pack(side=side_start(), padx=3)
        return bar

    # ------------------------------------------------------------------
    #  صفحه‌ی اصلی
    # ------------------------------------------------------------------
    def page_dashboard(self, parent):
        self.page_title(parent, self.db.get("building_name"))
        bar = self.toolbar(parent)
        year_var = tk.IntVar(value=self.year)

        def apply_year(_event=None):
            try:
                value = int(year_var.get())
            except (tk.TclError, ValueError):
                return
            if 1300 <= value <= 1600 and value != self.year:
                self.year = value
                self.render()

        ttk.Label(bar, text=T("سال مالی") + ":").pack(side=side_start(), padx=4)
        spin = ttk.Spinbox(bar, from_=1300, to=1600, textvariable=year_var, width=7, command=apply_year)
        spin.pack(side=side_start(), padx=4)
        spin.bind("<Return>", apply_year)
        self.tool_button(bar, "گزارش مالی سالانه PDF", self.pdf_annual_report)
        self.tool_button(bar, "گزارش مالی چندماهه PDF", self.pdf_multi_month_report)
        self.tool_button(bar, "خروجی Excel سالانه", self.excel_annual)
        self.tool_button(bar, "دسته‌بندی‌ها", self.manage_categories)

        counts, acc = self.db.unit_counts(), self.db.accounts()
        balance = self.db.current_balances()
        cards = ttk.Frame(parent)
        cards.pack(fill="x", padx=14, pady=(8, 0))
        items = [(T("واحدها"), str(counts["units"]), "Value"), (T("مالکان"), str(counts["owners"]), "Value"),
                 (T("مستأجران"), str(counts["tenants"]), "Value"),
                 (T("موجودی فعلی {}", acc["names"][0]), f"{money(balance[0])} {T('تومان')}",
                  "ValueWarn" if balance[0] < 0 else "Value")]
        if acc["multi"]:
            items.append((T("موجودی فعلی {}", acc["names"][1]), f"{money(balance[1])} {T('تومان')}",
                          "ValueWarn" if balance[1] < 0 else "Value"))
        for col, (title, value, tone) in enumerate(items):
            self.stat_card(cards, title, value, 0, col, tone)

        ttk.Label(parent, text=T("ماه‌های سال"), style="Header.TLabel").pack(fill="x", padx=22, pady=(18, 4),
                                                                              anchor=text_anchor())
        grid = ttk.Frame(parent)
        grid.pack(fill="both", expand=True, padx=14, pady=4)
        for index, (season, first) in enumerate(SEASONS):
            col = 3 - index if i18n.rtl else index
            box = ttk.LabelFrame(grid, text=T(season))
            box.grid(row=0, column=col, sticky="nsew", padx=6, pady=6)
            grid.columnconfigure(col, weight=1)
            for offset in range(3):
                m = first + offset + 1
                f = self.db.flow(self.year, m)
                card = ttk.Frame(box, style="Card.TFrame", padding=8)
                card.pack(fill="x", padx=6, pady=5)
                ttk.Button(card, text=f"{month_name(m)} {self.year}", command=lambda mm=m: self.open_month(mm)
                           ).pack(fill="x")
                for label, value in ((T("کل شارژ"), self.db.total_assessed(KIND_CHARGE, self.year, m)),
                                     (T("دریافتی"), f[0] + f[1]), (T("درآمد متفرقه"), f[4] + f[5]),
                                     (T("هزینه"), f[2] + f[3])):
                    ttk.Label(card, text=f"{label}: {money(value)}", style="CardText.TLabel").pack(anchor=text_anchor(), pady=1)

    def open_month(self, month):
        self.month = month
        self.show("month")

    # ------------------------------------------------------------------
    #  صفحه‌ی ثبت ماهانه
    # ------------------------------------------------------------------
    def page_month(self, parent):
        self.month_bar(parent, self.render)
        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True, padx=18, pady=8)
        tabs = [("summary", "خلاصه مالی", self.tab_summary), ("payments", "شارژ و پرداختی‌ها", self.tab_payments),
                ("expenses", "هزینه‌ها", self.tab_expenses), ("incomes", "درآمدهای متفرقه", self.tab_incomes)]
        # درآمدهای متفرقه در محیط ثبت ماهانه همیشه آخرین تب است.
        keys = []
        for key, label, builder in tabs:
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=T(label))
            builder(frame)
            keys.append(key)
        if self.tab in keys:
            notebook.select(keys.index(self.tab))
        notebook.bind("<<NotebookTabChanged>>", lambda _e: setattr(self, "tab", keys[notebook.index("current")]))

    # ---- خلاصه ----
    def tab_summary(self, parent):
        # محتوای خلاصه در یک Canvas مستقل قرار می‌گیرد تا در پنجره‌های کوتاه
        # نیز تمام کارت‌ها، تنظیمات و دکمه‌ی گزارش قابل دسترسی باشند.
        holder = ttk.Frame(parent)
        holder.pack(fill="both", expand=True)

        canvas = tk.Canvas(holder, bg=self.colors["bg"], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)

        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        canvas.configure(yscrollcommand=_autohide_scrollbar(scrollbar))

        scrollbar.pack(side=side_end(), fill="y")
        canvas.pack(side=side_start(), fill="both", expand=True)

        y, m = self.year, self.month
        ov, acc = self.db.overview(y, m), self.db.accounts()
        n1, n2 = acc["pdf"]
        o, e = ov["balances"]["open"], ov["balances"]["end"]
        toman = T("تومان")
        cards = [
            ("opening_1", T("شروع ماه {}", n1), o[0], "Value"),
            ("closing_1", T("پایان ماه {}", n1), e[0], "ValueWarn" if e[0] < 0 else "Value"),
        ]
        if acc["multi"]:
            cards += [
                ("opening_2", T("شروع ماه {}", n2), o[1], "Value"),
                ("closing_2", T("پایان ماه {}", n2), e[1], "ValueWarn" if e[1] < 0 else "Value"),
            ]
        cards += [
            ("charge_assessed", T("کل شارژ تعیین‌شده"), ov["charge_assessed"], "Value"),
            ("charge_received", T("واریزی شارژ به {}", n1), ov["charge_received"], "ValueGood"),
            ("charge_due", T("بدهی شارژ واحدها"), ov["charge_due"],
             "ValueWarn" if ov["charge_due"] else "Value"),
        ]
        if acc["multi"]:
            cards += [
                ("contrib_assessed", T("کل پرداختی تعیین‌شده"), ov["contrib_assessed"], "Value"),
                ("contrib_received", T("واریزی به {}", n2), ov["contrib_received"], "ValueGood"),
                ("contrib_due", T("بدهی پرداختی واحدها"), ov["contrib_due"],
                 "ValueWarn" if ov["contrib_due"] else "Value"),
            ]
        cards.append(("income_1", T("درآمد متفرقه از {}", n1), ov["income1"], "Value"))
        if acc["multi"]:
            cards.append(("income_2", T("درآمد متفرقه از {}", n2), ov["income2"], "Value"))
        cards.append(("expense_1", T("هزینه از {}", n1), ov["expense1"], "Value"))
        if acc["multi"]:
            cards.append(("expense_2", T("هزینه از {}", n2), ov["expense2"], "Value"))

        # ترتیب کارت‌ها یک تنظیم سراسری است، نه وابسته به ماه یا سال.
        try:
            saved_order = json.loads(self.db.get("monthly_summary_card_order", "[]") or "[]")
        except (TypeError, ValueError):
            saved_order = []
        card_map = {item[0]: item for item in cards}
        ordered_keys = [key for key in saved_order if key in card_map]
        ordered_keys += [key for key in card_map if key not in ordered_keys]
        cards = [card_map[key] for key in ordered_keys]

        grid = ttk.Frame(content)
        grid.pack(fill="x", padx=8, pady=(10, 3))
        card_widgets = {}

        def redraw_summary_cards():
            for position, key in enumerate(ordered_keys):
                card_widgets[key].grid(row=position // 3, column=position % 3,
                                       padx=4, pady=4, sticky="nsew")
            for col in range(3):
                grid.columnconfigure(col, weight=1)

        drag_state = {"key": None}

        def drag_start(event, key):
            drag_state["key"] = key

        def drag_finish(event):
            source = drag_state.get("key")
            drag_state["key"] = None
            if not source:
                return
            x, y = event.x_root, event.y_root
            target = None
            for key, widget in card_widgets.items():
                left, top = widget.winfo_rootx(), widget.winfo_rooty()
                if left <= x <= left + widget.winfo_width() and top <= y <= top + widget.winfo_height():
                    target = key
                    break
            if target and target != source:
                old_index, new_index = ordered_keys.index(source), ordered_keys.index(target)
                ordered_keys.pop(old_index)
                ordered_keys.insert(new_index, source)
                self.db.set("monthly_summary_card_order", json.dumps(ordered_keys, ensure_ascii=False))
                redraw_summary_cards()

        for key, title, value, tone in cards:
            card = ttk.Frame(grid, style="Card.TFrame", padding=(9, 6), cursor="fleur")
            card_widgets[key] = card
            title_label = ttk.Label(
                card, text=title, style="CardTitle.TLabel", wraplength=210,
                justify="right" if i18n.rtl else "left", cursor="fleur"
            )
            title_label.pack(anchor=text_anchor())
            value_label = ttk.Label(card, text=f"{money(value)} {toman}",
                                    style=tone + ".TLabel", cursor="fleur")
            value_label.pack(anchor=text_anchor(), pady=(2, 0))
            for widget in (card, title_label, value_label):
                widget.bind("<ButtonPress-1>", lambda event, k=key: drag_start(event, k), add="+")
                widget.bind("<ButtonRelease-1>", drag_finish, add="+")
        redraw_summary_cards()

        # هر حساب مبلغ مستقل دارد؛ هر دو از یک الگوریتم محاسبه استفاده می‌کنند.
        self.assess_panel(content, KIND_CHARGE)
        if acc["multi"]:
            self.assess_panel(content, KIND_CONTRIB)

        complete, partial, unpaid = ov["counts"]
        ttk.Label(
            content,
            text=T("پرداخت کامل: {0} — ناقص: {1} — پرداخت‌نشده: {2}",
                   complete, partial, unpaid),
            style="Bold.TLabel"
        ).pack(anchor=text_anchor(), padx=16, pady=(10, 5))

        bar = self.toolbar(content)
        self.tool_button(bar, "گزارش PDF", self.pdf_month_report, accent=True)
        self.tool_button(bar, "خروجی Excel ماهانه", self.excel_month)

    # ---- شارژ و پرداختی‌ها ----
    def tab_payments(self, parent):
        acc = self.db.accounts()
        y, m = self.year, self.month
        bar = self.toolbar(parent)
        self.tool_button(bar, "ثبت پرداخت جدید", lambda: self.payment_dialog(None), accent=True)
        self.tool_button(bar, "ویرایش انتخاب", lambda: self.edit_selected(table, self.payment_dialog))
        self.tool_button(bar, "حذف انتخاب", lambda: self.delete_record(table, self.db.delete_payment,
                                                                    "پرداخت انتخاب‌شده حذف شود؟"))
        self.tool_button(bar, "رسید پرداخت", lambda: self.receipt_for(table))

        def rows():
            out = []
            for p in self.db.payments(y, m):
                kind = p["payment_type"] if p["payment_type"] in (KIND_CHARGE, KIND_CONTRIB) else KIND_CHARGE
                # رکوردهای پرداختی قدیمی در حالت تک‌حسابی هم باید قابل مشاهده و ویرایش باشند.
                st = self.db.statement(kind, y, m, p["unit_id"])
                payer = self.db.payer_name(
                    {"tenant": p["tenant"], "owner": p["owner"], "status": p["unit_status"]}, kind
                )
                out.append((p["id"], (self.unit_text(p["unit_number"]) if p["unit_number"] else "-", payer, T(kind),
                                      money(p["amount"]), money(st["share"]), money(st["prev_debt"]),
                                      money(st["prev_credit"]), money(st["payable"]), money(st["balance"]),
                                      p["paid_at"], p["notes"] or ""), None))
            return out

        def footer():
            total = sum(p["amount"] for p in self.db.payments(y, m))
            return T("مجموع واریزی‌ها: {} تومان", money(total))

        table = DataTable(parent, self, "payments", [
            ("unit", "واحد", 80), ("name", "نام", 130), ("kind", "نوع", 70), ("amount", "واریزی", 100),
            ("share", "حق‌السهم", 100), ("prev_debt", "بدهکاری ماه‌های قبل", 120),
            ("prev_credit", "بستانکاری ماه‌های قبل", 120), ("payable", "قابل واریز", 100),
            ("balance", "مانده حساب", 100), ("date", "تاریخ", 90), ("notes", "توضیحات", 160)],
            rows, on_open=lambda: self.edit_selected(table, self.payment_dialog),
            row_key=f"payments_{y}_{m}", footer_fn=footer, sort_options=[
                ("unit_asc", "بر اساس واحدها", "unit", "unit", False),
                ("amount_asc", "مبلغ از کم به زیاد", "amount", "amount", False),
                ("amount_desc", "مبلغ از زیاد به کم", "amount", "amount", True),
                ("date_asc", "تاریخ از قدیم به جدید", "date", "date", False),
                ("date_desc", "تاریخ از جدید به قدیم", "date", "date", True),
                ("name_asc", "بر اساس نام", "name", "text", False),
                ("type_asc", "بر اساس نوع پرداخت", "kind", "text", False)])
        table.pack(fill="both", expand=True, padx=12, pady=(2, 10))

    def assess_panel(self, parent, kind):
        y, m, acc = self.year, self.month, self.db.accounts()
        is_charge = kind == KIND_CHARGE
        account_name = acc["names"][0 if is_charge else 1]
        box = ttk.LabelFrame(parent, text=T("شارژ هر واحد ({})", account_name))
        box.pack(fill="x", padx=12, pady=(8, 2))
        row = ttk.Frame(box)
        row.pack(fill="x", padx=10, pady=8)
        var = tk.StringVar(value=money(self.db.default_assessment(kind, y, m)))
        ttk.Label(row, text=T("مبلغ هر واحد") + ":").pack(side=side_start())
        MoneyEntry(row, textvariable=var, width=16).pack(side=side_start(), padx=6)
        ttk.Button(row, text=T("ذخیره"), command=lambda: self.save_assessment(kind, var, False)).pack(side=side_start())
        ttk.Button(row, text=T("اعمال تا پایان سال"),
                   command=lambda: self.save_assessment(kind, var, True)).pack(side=side_start(), padx=6)
        ttk.Button(row, text=T("تعیین مبلغ جداگانه برای واحدها"),
                   command=lambda: self.overrides_dialog(kind)).pack(side=side_start())
        flow = self.db.flow(y, m)
        ttk.Label(row, text=T("کل: {0} — دریافتی: {1} — مانده وصول: {2} تومان", money(self.db.total_assessed(kind, y, m)),
                              money(flow[0] if is_charge else flow[1]), money(self.db.outstanding(kind, y, m))),
                  style="Bold.TLabel").pack(side=side_end())

    def save_assessment(self, kind, var, through_year_end):
        try:
            amount = parse_money(var.get())
        except ValueError as exc:
            return self.error(translate_error(exc) if str(exc) in ERROR_MESSAGES else "مبلغ باید عددی باشد.")
        if amount < 0:
            return self.error("مبلغ شارژ یا پرداختی نمی‌تواند منفی باشد.")
        if through_year_end and not self.confirm("این مبلغ برای {} تا پایان سال {} اعمال شود؟",
                                                 month_name(self.month), self.year):
            return
        self.db.set_default_assessment(kind, self.year, self.month, amount, through_year_end)
        self.render()

    def overrides_dialog(self, kind):
        units = self.db.units()
        if not units:
            return self.warn("ابتدا حداقل یک واحد ثبت کنید.")
        y, m, c = self.year, self.month, self.colors
        overrides = self.db.unit_overrides(kind, y, m)
        default = self.db.default_assessment(kind, y, m)
        win = tk.Toplevel(self)
        win.title(f"{T('تعیین مبلغ جداگانه برای واحدها')} — {month_name(m)} {y}")
        win.configure(bg=c["bg"])
        win.geometry("580x540")
        win.transient(self)
        ttk.Label(win, text=T("برای هر واحد مبلغ دلخواه را وارد کنید. اگر خالی بماند، مبلغ پیش‌فرض ({}) اعمال می‌شود.",
                              money(default)), wraplength=540, justify="right" if i18n.rtl else "left"
                  ).pack(fill="x", padx=16, pady=(14, 8))
        holder = ttk.Frame(win)
        holder.pack(fill="both", expand=True, padx=16)
        canvas = tk.Canvas(holder, bg=c["bg"], highlightthickness=0)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=_autohide_scrollbar(scroll))
        scroll.pack(side=side_end(), fill="y")
        canvas.pack(side=side_start(), fill="both", expand=True)

        variables = {}
        for unit in units:
            line = ttk.Frame(inner)
            line.pack(fill="x", pady=3)
            ttk.Label(line, text=self.unit_choice_label(unit), width=34, anchor=text_anchor()).pack(side=side_start())
            var = tk.StringVar(value=money(overrides[unit["id"]]) if unit["id"] in overrides else "")
            MoneyEntry(line, textvariable=var, width=18).pack(side=side_start(), padx=6)
            variables[unit["id"]] = var

        def save():
            mapping = {}
            for unit_id, var in variables.items():
                text = var.get().strip()
                try:
                    amount = parse_money(text) if text else None
                except ValueError as exc:
                    message = translate_error(exc) if str(exc) in ERROR_MESSAGES else T("مبلغ باید عددی باشد.")
                    return messagebox.showerror(T("خطا"), T(message), parent=win)
                if amount is not None and amount < 0:
                    return messagebox.showerror(T("خطا"), T("مبلغ نمی‌تواند منفی باشد."), parent=win)
                mapping[unit_id] = amount
            self.db.set_unit_overrides(kind, y, m, mapping)
            win.destroy()
            self.render()

        buttons = ttk.Frame(win)
        buttons.pack(pady=12)
        ttk.Button(buttons, text=T("ذخیره"), style="Accent.TButton", command=save).pack(side=side_start(), padx=6)
        ttk.Button(buttons, text=T("انصراف"), command=win.destroy).pack(side=side_start(), padx=6)
        try:
            win.wait_visibility()
            win.grab_set()
        except tk.TclError:
            pass

    @staticmethod
    def _selected_id(table):
        selected = table.selected()
        return int(selected) if selected is not None else None

    def edit_selected(self, table, editor, message="ابتدا یک مورد را انتخاب کنید."):
        record_id = self._selected_id(table)
        if record_id is None:
            return self.warn(message)
        return editor(record_id)

    def delete_record(self, table, deleter, question):
        record_id = self._selected_id(table)
        if record_id is None:
            return self.warn("ابتدا یک مورد را انتخاب کنید.")
        if not self.confirm(question):
            return
        try:
            deleter(record_id)
        except ValueError as exc:
            return self.error(translate_error(exc))
        except sqlite3.Error as exc:
            return self.error("حذف انجام نشد:\n{}", exc)
        self.render()

    def receipt_for(self, table):
        payment_id = self._selected_id(table)
        if payment_id is None:
            return self.warn("یک پرداخت را انتخاب کنید.")
        self.pdf_receipt(payment_id)

    def payment_dialog(self, payment_id):
        y, m, acc = self.year, self.month, self.db.accounts()
        payment = self.db.payment(payment_id) if payment_id else None
        if payment_id and payment is None:
            return self.error("پرداخت پیدا نشد.")
        units = self.db.units()
        if payment and payment["unit_id"] not in [u["id"] for u in units]:
            extra = self.db.unit(payment["unit_id"])
            if extra:
                units.append(extra)
        if not units:
            return self.warn("ابتدا حداقل یک واحد ثبت کنید.")
        kinds = [(KIND_CHARGE, T("شارژ"))]
        if acc["multi"] or (payment is not None and payment["payment_type"] == KIND_CONTRIB):
            kinds.append((KIND_CONTRIB, T("پرداختی")))
        fields = [
            {"key": "unit_id", "label": "واحد", "kind": "choice", "required": True,
             "choices": [(u["id"], self.unit_choice_label(u)) for u in units],
             "default": payment["unit_id"] if payment else None},
            {"key": "kind", "label": "نوع", "kind": "radio", "choices": kinds,
             "default": (payment["payment_type"] if payment else KIND_CHARGE)},
            {"key": "amount", "label": "مبلغ", "kind": "money", "required": True,
             "default": payment["amount"] if payment else None},
            {"key": "paid_at", "label": "تاریخ", "kind": "date", "required": True,
             "default": payment["paid_at"] if payment else default_date_for(y, m)},
            {"key": "notes", "label": "توضیحات", "default": payment["notes"] if payment else ""},
        ]

        def autofill(form):
            if payment is not None or "amount" in form.touched:
                return
            uid, kind = form.get("unit_id"), form.get("kind")
            if uid is None or kind is None:
                return
            balance = self.db.statement(kind, y, m, uid)["balance"]
            form.set("amount", balance if balance else "")

        result = FormDialog(self, "ویرایش پرداخت" if payment else "ثبت پرداخت", fields, on_change=autofill).result
        if result:
            self.db.save_payment(payment_id, {**result, "year": y, "month": m})
            self.render()

    # ---- درآمدهای متفرقه ----
    def tab_incomes(self, parent):
        y, m, acc = self.year, self.month, self.db.accounts()
        bar = self.toolbar(parent)
        self.tool_button(bar, "ثبت درآمد جدید", lambda: self.income_dialog(None), accent=True)
        self.tool_button(bar, "ویرایش انتخاب", lambda: self.edit_selected(table, self.income_dialog))
        self.tool_button(bar, "حذف انتخاب", lambda: self.delete_record(table, self.db.delete_income,
                                                                    "درآمد انتخاب‌شده حذف شود؟"))
        self.tool_button(bar, "دسته‌بندی‌ها", self.manage_categories)

        def rows():
            return [(item["id"], (item["title"], money(item["amount"]), item["received_at"],
                                  acc["pdf"][1] if (acc["multi"] and item["account"] == 2)
                                  else acc["pdf"][0], item["source"] or T("سایر"), item["notes"] or ""), None)
                    for item in self.db.incomes(y, m)]

        def footer():
            return T("مجموع درآمد متفرقه: {} تومان", money(sum(item["amount"] for item in self.db.incomes(y, m))))

        table = DataTable(parent, self, "incomes", [
            ("title", "عنوان", 180), ("amount", "مبلغ", 110), ("date", "تاریخ", 90),
            ("account", "حساب مقصد", 145), ("source", "منبع درآمد", 160),
            ("notes", "توضیحات", 180)], rows, on_open=lambda: self.edit_selected(table, self.income_dialog),
            row_key=f"incomes_{y}_{m}", footer_fn=footer, sort_options=[
                ("amount_asc", "مبلغ از کم به زیاد", "amount", "amount", False),
                ("amount_desc", "مبلغ از زیاد به کم", "amount", "amount", True),
                ("date_asc", "تاریخ از قدیم به جدید", "date", "date", False),
                ("date_desc", "تاریخ از جدید به قدیم", "date", "date", True),
                ("title_asc", "بر اساس عنوان", "title", "text", False),
                ("type_asc", "بر اساس حساب", "account", "number", False)])
        table.pack(fill="both", expand=True, padx=12, pady=(2, 10))

    def income_dialog(self, income_id):
        y, m, acc = self.year, self.month, self.db.accounts()
        item = self.db.income(income_id) if income_id else None
        if income_id and item is None:
            return self.error("درآمد پیدا نشد.")
        accounts = [(1, acc["pdf"][0])] + ([(2, acc["pdf"][1])] if acc["multi"] else [])
        source_names = self.db.income_sources() or ["سایر"]
        fields = [
            {"key": "title", "label": "عنوان", "required": True, "default": item["title"] if item else ""},
            {"key": "amount", "label": "مبلغ", "kind": "money", "required": True, "positive": True,
             "default": item["amount"] if item else None},
            {"key": "received_at", "label": "تاریخ دریافت", "kind": "date", "required": True,
             "default": item["received_at"] if item else default_date_for(y, m)},
            {"key": "source", "label": "منبع درآمد", "kind": "choice",
             "choices": [(name, name) for name in source_names],
             "default": (item["source"] if item and item["source"] in source_names else source_names[0])},
            {"key": "account", "label": "واریز به حساب", "kind": "radio", "choices": accounts,
             "default": item["account"] if item and acc["multi"] else 1},
            {"key": "notes", "label": "توضیحات", "default": item["notes"] if item else ""},
        ]
        result = FormDialog(self, "ویرایش درآمد متفرقه" if item else "ثبت درآمد متفرقه", fields).result
        if result:
            if item is not None and not acc["multi"]:
                # در حالت نمایش تک‌حسابی، حساب واقعی رکورد ویرایش‌شده حفظ می‌شود.
                result["account"] = item["account"]
            self.db.save_income(income_id, {**result, "year": y, "month": m})
            self.render()

    # ---- هزینه‌ها ----
    def tab_expenses(self, parent):
        y, m, acc = self.year, self.month, self.db.accounts()
        bar = self.toolbar(parent)
        self.tool_button(bar, "ثبت هزینه جدید", lambda: self.expense_dialog(None), accent=True)
        self.tool_button(bar, "ویرایش انتخاب", lambda: self.edit_selected(table, self.expense_dialog))
        self.tool_button(bar, "حذف انتخاب", lambda: self.delete_record(table, self.db.delete_expense,
                                                                    "هزینه انتخاب‌شده حذف شود؟"))
        self.tool_button(bar, "دسته‌بندی‌ها", self.manage_categories)

        def rows():
            return [(e["id"], (e["title"], e["category"] or "", money(e["amount"]), e["paid_at"],
                               acc["pdf"][1] if (acc["multi"] and e["account"] == 2) else acc["pdf"][0],
                               e["notes"] or ""), None) for e in self.db.expenses(y, m)]

        def footer():
            return T("مجموع هزینه: {} تومان", money(sum(e["amount"] for e in self.db.expenses(y, m))))

        table = DataTable(parent, self, "expenses", [
            ("title", "عنوان", 200), ("category", "دسته‌بندی", 110), ("amount", "مبلغ", 110), ("date", "تاریخ", 90),
            ("type", "نوع هزینه", 150), ("notes", "توضیحات", 200)],
            rows, on_open=lambda: self.edit_selected(table, self.expense_dialog),
            row_key=f"expenses_{y}_{m}", footer_fn=footer, sort_options=[
                ("amount_asc", "مبلغ از کم به زیاد", "amount", "amount", False),
                ("amount_desc", "مبلغ از زیاد به کم", "amount", "amount", True),
                ("date_asc", "تاریخ از قدیم به جدید", "date", "date", False),
                ("date_desc", "تاریخ از جدید به قدیم", "date", "date", True),
                ("category_asc", "بر اساس دسته‌بندی", "category", "text", False),
                ("title_asc", "بر اساس عنوان", "title", "text", False),
                ("type_asc", "بر اساس نوع هزینه", "type", "text", False)])
        table.pack(fill="both", expand=True, padx=12, pady=(2, 10))

    def expense_dialog(self, expense_id):
        y, m, acc = self.year, self.month, self.db.accounts()
        expense = self.db.expense(expense_id) if expense_id else None
        if expense_id and expense is None:
            return self.error("هزینه پیدا نشد.")
        categories = self.db.categories()
        if not categories:
            self.db.add_category("سایر")
            categories = ["سایر"]
        if expense and expense["category"] and expense["category"] not in categories:
            categories.append(expense["category"])
        accounts = [(1, acc["pdf"][0])] + ([(2, acc["pdf"][1])] if acc["multi"] else [])
        fields = [
            {"key": "title", "label": "عنوان", "required": True, "default": expense["title"] if expense else ""},
            {"key": "category", "label": "دسته‌بندی", "kind": "choice", "choices": [(c, c) for c in categories],
             "default": expense["category"] if expense else categories[0]},
            {"key": "amount", "label": "مبلغ", "kind": "money", "required": True, "positive": True,
             "default": expense["amount"] if expense else None},
            {"key": "paid_at", "label": "تاریخ", "kind": "date", "required": True,
             "default": expense["paid_at"] if expense else default_date_for(y, m)},
            {"key": "account", "label": "نوع هزینه", "kind": "radio", "choices": accounts,
             "default": (expense["account"] if expense and acc["multi"] else 1)},
            {"key": "notes", "label": "توضیحات", "default": expense["notes"] if expense else ""},
        ]
        result = FormDialog(self, "ویرایش هزینه" if expense else "ثبت هزینه", fields).result
        if result:
            if expense is not None and not acc["multi"]:
                # حساب اصلی هزینه در دیتابیس می‌ماند؛ فقط در رابط کاربری تجمیع شده است.
                result["account"] = expense["account"]
            self.db.save_expense(expense_id, {**result, "year": y, "month": m})
            self.render()

    # ------------------------------------------------------------------
    #  واحدها
    # ------------------------------------------------------------------
    def page_units(self, parent):
        self.page_title(parent, T("مدیریت واحدها"))
        bar = self.toolbar(parent)
        self.tool_button(bar, "افزودن واحد", lambda: self.unit_dialog(None), accent=True)
        self.tool_button(bar, "ویرایش واحد", lambda: self.edit_selected(table, self.unit_dialog, "ابتدا یک واحد را انتخاب کنید."))
        self.tool_button(bar, "حذف واحد", self.delete_unit)
        ttk.Checkbutton(bar, text=T("نمایش واحدهای غیرفعال"), variable=self.show_inactive,
                        command=lambda: table.refresh()).pack(side=side_start(), padx=14)

        def rows():
            out = []
            for u in self.db.units(include_inactive=self.show_inactive.get()):
                tenant = u["tenant"] if u["status"] == ST_TENANT else ""
                tenant_phone = u["tenant_phone"] if u["status"] == ST_TENANT else ""
                out.append((u["id"], (u["number"], u["floor"] or "", T(u["status"]), u["owner"] or "",
                                      u["owner_phone"] or "", tenant or "", tenant_phone or "", u["notes"] or "",
                                      "✓" if u["active"] else "—"), None if u["active"] else "muted"))
            return out

        table = DataTable(parent, self, "units", [
            ("number", "شماره واحد", 90), ("floor", "طبقه", 70), ("status", "وضعیت", 90), ("owner", "مالک", 150),
            ("owner_phone", "تلفن مالک", 120), ("tenant", "مستأجر", 150), ("tenant_phone", "تلفن مستأجر", 120),
            ("notes", "توضیحات", 170), ("active", "فعال", 60)], rows,
            on_open=lambda: self.unit_dialog(self._selected_id(table)),
            row_key="units_manual", footer_fn=lambda: T("{} واحد فعال", self.db.unit_counts()["units"]),
            sort_options=[("unit_asc", "بر اساس واحدها", "number", "unit", False),
                          ("floor_asc", "بر اساس طبقه", "floor", "unit", False),
                          ("status_asc", "بر اساس وضعیت", "status", "text", False),
                          ("owner_asc", "بر اساس نام مالک", "owner", "text", False)])
        table.pack(fill="both", expand=True, padx=12, pady=(2, 10))

    def unit_dialog(self, unit_id):
        unit = self.db.unit(unit_id) if unit_id else None
        if unit_id and unit is None:
            return self.error("واحد پیدا نشد.")
        statuses = [(ST_OWNER, T("مالک")), (ST_TENANT, T("مستأجر"))]

        def d(key, fallback=""):
            return (unit[key] if unit and unit[key] is not None else fallback)

        fields = [
            {"key": "number", "label": "شماره واحد", "required": True,
             "default": d("number", self.db.next_unit_number())},
            {"key": "floor", "label": "طبقه", "default": d("floor")},
            {"key": "status", "label": "نوع سکونت", "kind": "choice", "choices": statuses,
             "default": d("status", ST_OWNER) if d("status", ST_OWNER) != LEGACY_ST_VACANT else ST_OWNER},
            {"key": "owner", "label": "نام مالک", "default": d("owner")},
            {"key": "owner_phone", "label": "تلفن مالک", "default": d("owner_phone")},
            {"key": "tenant", "label": "نام مستأجر", "default": d("tenant"), "show_if": ("status", ST_TENANT)},
            {"key": "tenant_phone", "label": "تلفن مستأجر", "default": d("tenant_phone"),
             "show_if": ("status", ST_TENANT)},
            {"key": "notes", "label": "توضیحات", "default": d("notes")},
        ]
        fields.append({"key": "active", "label": "وضعیت واحد", "kind": "radio",
                       "choices": [(True, T("فعال")), (False, T("غیرفعال"))],
                       "default": bool(unit["active"]) if unit else True})

        def validate(res):
            if self.db.unit_number_exists(res["number"], unit_id):
                return T("این شماره‌ی واحد قبلاً ثبت شده است.")
            return None

        result = FormDialog(self, "ویرایش واحد" if unit else "افزودن واحد", fields, validate=validate).result
        if result:
            # وضعیت فعال/غیرفعال مستقل از مالک/مستأجر است و در افزودن و ویرایش یکسان عمل می‌کند.
            result["active"] = bool(result.get("active", True))
            try:
                self.db.save_unit(unit_id, result, self.year, self.month)
            except ValueError as exc:
                return self.error(translate_error(exc))
            self.render()

    def delete_unit(self):
        table = next((w for w in self.content.winfo_children() if isinstance(w, DataTable)), None)
        unit_id = self._selected_id(table) if table else None
        if unit_id is None:
            return self.warn("ابتدا یک واحد را انتخاب کنید.")
        if self.db.unit_record_count(unit_id):
            if not self.confirm("این واحد سابقه‌ی مالی دارد؛ برای حفظ تاریخچه‌ی پرداخت‌ها حذف نمی‌شود و غیرفعال می‌شود. ادامه می‌دهید؟"):
                return
        elif not self.confirm("واحد حذف شود؟"):
            return
        try:
            outcome = self.db.remove_unit(unit_id, self.year, self.month)
        except ValueError as exc:
            return self.error(translate_error(exc))
        if outcome == "archived":
            self.info("واحد غیرفعال شد.")
        self.render()

    # ------------------------------------------------------------------
    #  بدهکاران
    # ------------------------------------------------------------------
    def page_debtors(self, parent):
        self.month_bar(parent, self.render)
        acc = self.db.accounts()
        if not acc["multi"]:
            self.debt_kind = KIND_CHARGE
        bar = self.toolbar(parent)
        kind_var = tk.StringVar(value=self.debt_kind)

        def change_kind():
            self.debt_kind = kind_var.get()
            self.render()

        ttk.Radiobutton(bar, text=T(acc["names"][0]), value=KIND_CHARGE, variable=kind_var,
                        command=change_kind).pack(side=side_start(), padx=8)
        if acc["multi"]:
            ttk.Radiobutton(bar, text=T(acc["names"][1]), value=KIND_CONTRIB, variable=kind_var,
                            command=change_kind).pack(side=side_start(), padx=8)
        self.tool_button(bar, "خروجی PDF", lambda: self.pdf_debtors(self.debt_kind), accent=True)
        kind = self.debt_kind
        # صفر بودن حق‌السهم ماه جاری به معنی صفر بودن بدهی‌های منتقل‌شده از ماه‌های قبل نیست.
        if not self.debtor_rows(kind):
            ttk.Label(parent, text=T("برای این حساب بدهیِ تسویه‌نشده‌ای وجود ندارد."),
                      foreground=self.colors["muted"], wraplength=900, justify="right").pack(
                          fill="x", padx=20, pady=(2, 8))

        def rows():
            return [(u["id"], (self.unit_text(u["number"]), self.db.payer_name(u, kind), self.db.payer_phone(u, kind),
                               money(st["paid"]), money(st["share"]), money(st["prev_debt"]),
                               money(st["prev_credit"]), money(st["payable"]), money(st["balance"])),
                     "warn") for u, st in self.debtor_rows(kind)]

        def footer():
            total = sum(st["balance"] for _, st in self.debtor_rows(kind))
            return T("جمع مانده: {} تومان", money(total))

        table = DataTable(parent, self, "debtors", [
            ("unit", "واحد", 75), ("name", "نام", 140), ("phone", "تلفن", 105),
            ("paid", "واریزی", 100), ("share", "حق‌السهم", 100),
            ("prev_debt", "بدهکاری ماه‌های قبل", 125), ("prev_credit", "بستانکاری ماه‌های قبل", 130),
            ("payable", "قابل واریز", 105), ("balance", "مانده حساب", 105)], rows,
            row_key=f"debtors_{kind}_{self.year}_{self.month}", footer_fn=footer, sort_options=[
                ("unit_asc", "بر اساس واحدها", "unit", "unit", False),
                ("amount_asc", "مانده از کم به زیاد", "balance", "amount", False),
                ("amount_desc", "مانده از زیاد به کم", "balance", "amount", True),
                ("name_asc", "بر اساس نام", "name", "text", False)])
        table.pack(fill="both", expand=True, padx=18, pady=(4, 12))

    # ------------------------------------------------------------------
    #  مدیریت دسته‌بندی‌ها: هزینه‌ها و منابع درآمد
    # ------------------------------------------------------------------
    def manage_categories(self):
        c = self.colors
        win = tk.Toplevel(self)
        win.title(T("دسته‌بندی‌ها"))
        win.configure(bg=c["bg"])
        win.geometry("500x500")
        win.transient(self)

        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)
        expense_tab = ttk.Frame(notebook)
        income_tab = ttk.Frame(notebook)
        notebook.add(expense_tab, text=T("دسته‌بندی هزینه‌ها"))
        notebook.add(income_tab, text=T("دسته‌بندی منبع درآمد"))

        def build_tab(parent, *, income=False):
            heading = "منابع درآمد" if income else "دسته‌بندی‌های هزینه‌ها"
            add_title = "افزودن منبع درآمد" if income else "افزودن دسته‌بندی"
            edit_title = "ویرایش منبع درآمد" if income else "ویرایش دسته‌بندی"
            list_frame = ttk.Frame(parent)
            list_frame.pack(fill="both", expand=True, padx=8, pady=(10, 4))
            ttk.Label(list_frame, text=T(heading), style="Header.TLabel").pack(pady=(2, 8))
            body = ttk.Frame(list_frame)
            body.pack(fill="both", expand=True)
            listbox = tk.Listbox(body, bg=c["input"], fg=c["fg"], selectbackground=c["select_bg"],
                                 selectforeground=c["select_fg"], highlightthickness=1,
                                 highlightbackground=c["border"], font=(self.font_family, 11), activestyle="none")
            scroll = ttk.Scrollbar(body, orient="vertical", command=listbox.yview)
            scroll.pack(side=side_end(), fill="y")
            listbox.pack(side=side_start(), fill="both", expand=True)
            listbox.configure(yscrollcommand=_autohide_scrollbar(scroll))

            get_items = self.db.income_sources if income else self.db.categories
            add_item = self.db.add_income_source if income else self.db.add_category
            rename_item = self.db.rename_income_source if income else self.db.rename_category
            delete_item = self.db.delete_income_source if income else self.db.delete_category
            usage_item = self.db.income_source_usage if income else self.db.category_usage

            def refresh():
                listbox.delete(0, "end")
                for name in get_items():
                    listbox.insert("end", name)

            def chosen():
                selection = listbox.curselection()
                return listbox.get(selection[0]) if selection else None

            def prompt(title, initial=""):
                name_label = "نام منبع درآمد" if income else "نام دسته‌بندی"
                res = FormDialog(self, title, [{"key": "name", "label": name_label, "required": True,
                                               "default": initial}], parent=win).result
                return res["name"].strip() if res else None

            def add():
                name = prompt(add_title)
                if name:
                    try:
                        add_item(name)
                    except sqlite3.IntegrityError:
                        messagebox.showerror(T("خطا"), T("این دسته‌بندی قبلاً وجود دارد."), parent=win)
                    refresh()

            def edit():
                old = chosen()
                if old is None:
                    return messagebox.showwarning(T("هشدار"), T("یک دسته‌بندی را انتخاب کنید."), parent=win)
                new = prompt(edit_title, old)
                if new and new != old:
                    try:
                        rename_item(old, new)
                    except sqlite3.IntegrityError:
                        messagebox.showerror(T("خطا"), T("این نام قبلاً وجود دارد."), parent=win)
                    refresh()

            def delete():
                name = chosen()
                if name is None:
                    return messagebox.showwarning(T("هشدار"), T("یک دسته‌بندی را انتخاب کنید."), parent=win)
                if name == "سایر":
                    return messagebox.showwarning(T("هشدار"), T("دسته‌بندی «سایر» قابل حذف نیست."), parent=win)
                used = usage_item(name)
                if used:
                    message = (T("این منبع درآمد در {} درآمد استفاده شده است.\nابتدا این درآمدها به «سایر» منتقل می‌شوند.\nادامه می‌دهید؟", used)
                               if income else
                               T("این دسته‌بندی در {} هزینه استفاده شده است.\nابتدا این هزینه‌ها به «سایر» منتقل می‌شوند.\nادامه می‌دهید؟", used))
                    if not messagebox.askyesno(T("تأیید"), message, parent=win):
                        return
                delete_item(name)
                refresh()

            buttons = ttk.Frame(list_frame)
            buttons.pack(fill="x", padx=4, pady=(8, 2))
            ttk.Button(buttons, text=T("افزودن"), style="Accent.TButton", command=add).pack(side=side_start(), padx=3)
            ttk.Button(buttons, text=T("ویرایش"), command=edit).pack(side=side_start(), padx=3)
            ttk.Button(buttons, text=T("حذف"), command=delete).pack(side=side_start(), padx=3)
            refresh()

        build_tab(expense_tab, income=False)
        build_tab(income_tab, income=True)
        try:
            win.wait_visibility()
            win.grab_set()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    #  تنظیمات
    # ------------------------------------------------------------------
    def page_settings(self, parent):
        self.page_title(parent, T("تنظیمات پیشرفته ساختمان"))
        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True, padx=20, pady=10)
        tabs = [ttk.Frame(notebook) for _ in range(4)]
        labels = ["اطلاعات ساختمان", "تنظیمات ظاهری", "تنظیمات منطقی", "تنظیمات PDF و Excel"]
        order = list(zip(tabs, labels))
        # ترتیب زبانه‌ها ثابت است؛ تنظیمات PDF و Excel آخرین زبانه باقی می‌ماند.
        for frame, label in order:
            notebook.add(frame, text=T(label))
        db, rtl = self.db, i18n.rtl
        label_col, widget_col = (1, 0) if rtl else (0, 1)

        def group(frame, title):
            box = ttk.LabelFrame(frame, text=T(title))
            box.pack(anchor="center", padx=20, pady=24, ipadx=18, ipady=10)
            return box

        def row(box, index, label, widget):
            ttk.Label(box, text=T(label)).grid(row=index, column=label_col, sticky=text_anchor(), padx=10, pady=8)
            widget.grid(row=index, column=widget_col, padx=10, pady=8)

        # --- اطلاعات ساختمان ---
        box = group(tabs[0], "مشخصات کلی ساختمان")
        text_vars = {}
        for index, (label, key) in enumerate([("نام ساختمان", "building_name"), ("آدرس", "address"),
                                              ("نام مدیر", "manager"), ("تلفن مدیر", "phone")]):
            text_vars[key] = tk.StringVar(value=db.get(key))
            row(box, index, label, ttk.Entry(box, textvariable=text_vars[key], width=38,
                                             justify="right" if rtl else "left"))
        bal1 = tk.StringVar(value=money(db.get_money("initial_export_balance")))
        bal2 = tk.StringVar(value=money(db.get_money("initial_saman_balance")))
        row(box, 4, "موجودی اولیه کارت اول", MoneyEntry(box, textvariable=bal1, width=36))
        row(box, 5, "موجودی اولیه کارت دوم", MoneyEntry(box, textvariable=bal2, width=36))

        # --- ظاهر ---
        box = group(tabs[1], "تنظیمات ظاهری نرم‌افزار")
        fonts = [("normal", T("عادی (Normal)")), ("large", T("بزرگ (Large)"))]
        themes = [("light", T("روشن")), ("dark", T("تیره"))]
        font_var = tk.StringVar(value=dict(fonts)[db.get("font_size") if db.get("font_size") in dict(fonts) else "normal"])
        theme_var = tk.StringVar(value=dict(themes)[db.get("appearance") if db.get("appearance") in dict(themes) else "light"])
        lang_names = list(LANGUAGES)
        lang_var = tk.StringVar(value=next((n for n, code in LANGUAGES.items() if code == db.get("language")), "فارسی"))
        row(box, 0, "اندازه قلم (Font Size)", ttk.Combobox(box, textvariable=font_var, values=[l for _, l in fonts],
                                                             state="readonly", width=35))
        row(box, 1, "حالت نمایش (Appearance)", ttk.Combobox(box, textvariable=theme_var, values=[l for _, l in themes],
                                                              state="readonly", width=35))
        row(box, 2, "زبان رابط کاربری (Language)", ttk.Combobox(box, textvariable=lang_var, values=lang_names,
                                                                  state="readonly", width=35))

        # --- تنظیمات منطقی: همه بخش‌ها در یک صفحه‌ی اسکرول‌پذیر ---
        logical_outer = ttk.Frame(tabs[2])
        logical_outer.pack(fill="both", expand=True, padx=8, pady=8)
        logical_canvas = tk.Canvas(
            logical_outer, highlightthickness=0, bd=0,
            background=self.colors.get("bg", "#f2f2f2")
        )
        logical_scroll = ttk.Scrollbar(
            logical_outer, orient="vertical", command=logical_canvas.yview
        )
        logical_canvas.configure(yscrollcommand=_autohide_scrollbar(logical_scroll))
        logical_scroll.pack(side=side_end(), fill="y")
        logical_canvas.pack(side=side_start(), fill="both", expand=True)
        logical_content = ttk.Frame(logical_canvas)
        logical_window = logical_canvas.create_window(
            (0, 0), window=logical_content, anchor="nw"
        )

        def update_logical_scrollregion(_event=None):
            logical_canvas.configure(scrollregion=logical_canvas.bbox("all"))

        def resize_logical_content(event):
            logical_canvas.itemconfigure(logical_window, width=event.width)

        logical_content.bind("<Configure>", update_logical_scrollregion)
        logical_canvas.bind("<Configure>", resize_logical_content)

        # --- حساب‌ها ---
        box = group(logical_content, "مدیریت حساب‌ها و کارت‌های مالی")
        multi_opts = [("1", T("فعال")), ("0", T("غیرفعال"))]
        multi_var = tk.StringVar(value=dict(multi_opts)[db.get("multi_account_enabled") if db.get("multi_account_enabled") in ("0", "1") else "1"])
        row(box, 0, "وضعیت چندحسابی", ttk.Combobox(box, textvariable=multi_var, values=[l for _, l in multi_opts],
                                                    state="readonly", width=35))
        acc_vars = {}
        for index, (label, key) in enumerate([("نام کارت اول (برنامه)", "account1_name"),
                                              ("نام کارت اول (در خروجی PDF)", "account1_pdf"),
                                              ("نام کارت دوم (برنامه)", "account2_name"),
                                              ("نام کارت دوم (در خروجی PDF)", "account2_pdf")], 1):
            acc_vars[key] = tk.StringVar(value=db.get(key))
            row(box, index, label, ttk.Entry(box, textvariable=acc_vars[key], width=38, justify="right" if rtl else "left"))
        # --- سیاست شارژ واحد غیرفعال ---
        inactive_policy_opts = [
            ("same_month", T("از ابتدای همان ماه؛ دیگر شارژ نگیرد")),
            ("next_month", T("تا پایان همین ماه شارژ شود؛ از ماه بعد متوقف شود")),
        ]
        saved_policy = db.get("inactive_unit_charge_policy", "next_month")
        if saved_policy not in ("same_month", "next_month"):
            saved_policy = "next_month"
        inactive_policy_var = tk.StringVar(value=dict(inactive_policy_opts)[saved_policy])
        calculation_box = group(logical_content, "قوانین محاسبه شارژ")
        row(calculation_box, 0, "نحوه محاسبه شارژ واحد غیرفعال", ttk.Combobox(
            calculation_box, textvariable=inactive_policy_var,
            values=[label for _value, label in inactive_policy_opts],
            state="readonly", width=38))

        # --- مرتب‌سازی جدول‌های خروجی PDF و Excel (با اسکرول عمودی) ---
        export_sort_vars = {}
        export_outer = ttk.Frame(tabs[3])
        export_outer.pack(fill="both", expand=True, padx=8, pady=8)
        export_canvas = tk.Canvas(export_outer, highlightthickness=0, bd=0,
                                  background=self.colors.get("bg", "#f2f2f2"))
        export_scroll = ttk.Scrollbar(export_outer, orient="vertical", command=export_canvas.yview)
        export_canvas.configure(yscrollcommand=_autohide_scrollbar(export_scroll))
        export_scroll.pack(side=side_end(), fill="y")
        export_canvas.pack(side=side_start(), fill="both", expand=True)
        export_box = ttk.Frame(export_canvas)
        export_window = export_canvas.create_window((0, 0), window=export_box, anchor="nw")

        def update_export_scrollregion(_event=None):
            export_canvas.configure(scrollregion=export_canvas.bbox("all"))

        def resize_export_content(event):
            export_canvas.itemconfigure(export_window, width=event.width)

        export_box.bind("<Configure>", update_export_scrollregion)
        export_canvas.bind("<Configure>", resize_export_content)

        ttk.Label(export_box, text=T("ترتیب پیش‌فرض جدول‌ها در هر نوع خروجی را جداگانه انتخاب کنید."),
                  style="Bold.TLabel").pack(anchor=text_anchor(), pady=(4, 10))
        for output_kind, output_label in (("pdf_month", "PDF ماهانه"), ("pdf_annual", "PDF سالانه"),
                                          ("pdf_multi", "گزارش مالی چندماهه PDF"), ("pdf_debtors", "PDF بدهکاران"), ("excel_annual", "Excel سالانه"), ("excel_month", "Excel ماهانه")):
            group_box = ttk.LabelFrame(export_box, text=T(output_label))
            group_box.pack(fill="x", padx=6, pady=6, anchor="n")
            for table_kind, table_label in EXPORT_SORT_TABLES[output_kind]:
                line = ttk.Frame(group_box)
                line.pack(fill="x", padx=8, pady=5)
                ttk.Label(line, text=T(table_label), width=32, anchor=text_anchor()).pack(side=side_start(), padx=5)
                choices = [("default", T("ترتیب پیش‌فرض برنامه"))] + [(value, T(label)) for value, label in EXPORT_SORT_FIELDS[table_kind]]
                saved_mode = self.db.get(f"export_sort_{output_kind}_{table_kind}")
                initial_mode = saved_mode if saved_mode else "default"
                var = tk.StringVar(value=initial_mode)
                export_sort_vars[f"export_sort_{output_kind}_{table_kind}"] = var
                labels_by_value = {value: label for value, label in choices}
                if var.get() not in labels_by_value:
                    var.set(self.default_export_sort_mode(table_kind))
                combo = ttk.Combobox(line, state="readonly", width=32,
                                     values=[label for _, label in choices])
                combo.set(labels_by_value[var.get()])
                combo.pack(side=side_start(), padx=5)
                def sync_choice(event, v=var, cb=combo, mapping={label: value for value, label in choices}):
                    v.set(mapping.get(cb.get(), "default"))
                combo.bind("<<ComboboxSelected>>", sync_choice)

        def save():
            try:
                initial1, initial2 = parse_money(bal1.get()), parse_money(bal2.get())
            except ValueError as exc:
                message = translate_error(exc) if str(exc) in ERROR_MESSAGES else "موجودی اولیه باید عددی باشد."
                return self.error(message)
            if initial1 < 0 or initial2 < 0:
                return self.error("موجودی اولیه نمی‌تواند منفی باشد.")
            values = {k: v.get().strip() for k, v in {**text_vars, **acc_vars}.items()}
            for key in ("account1_name", "account2_name", "account1_pdf", "account2_pdf"):
                values[key] = values[key] or SETTING_DEFAULTS[key]
            if values["account1_name"] == values["account2_name"]:
                return self.error("نام دو کارت نباید یکسان باشد.")
            if values["account1_pdf"] == values["account2_pdf"]:
                return self.error("نام نمایشی دو حساب در گزارش‌ها نباید یکسان باشد.")
            values.update({key: var.get() for key, var in export_sort_vars.items()})
            values.update({
                "initial_export_balance": initial1, "initial_saman_balance": initial2,
                "font_size": next((k for k, l in fonts if l == font_var.get()), "normal"),
                "appearance": next((k for k, l in themes if l == theme_var.get()), "light"),
                "language": LANGUAGES.get(lang_var.get(), "fa"),
                "multi_account_enabled": next((k for k, l in multi_opts if l == multi_var.get()), "1"),
                "inactive_unit_charge_policy": next(
                    (k for k, label in inactive_policy_opts if label == inactive_policy_var.get()), "next_month"),
            })
            db.set_many(values)
            self.reload_preferences()
            self.page = "dashboard"
            self.render()
            self.info("تمامی تنظیمات با موفقیت ذخیره و در محاسبات اعمال شد.")

        ttk.Button(parent, text=T("ذخیره کلیه تغییرات تنظیمات"), style="Accent.TButton", command=save).pack(pady=14)

    # ------------------------------------------------------------------
    #  پشتیبان‌گیری و خروج
    # ------------------------------------------------------------------
    def do_backup(self):
        target = filedialog.asksaveasfilename(
            parent=self, defaultextension=".sqlite3", initialfile=datetime.now().strftime("building_%Y%m%d.sqlite3"),
            filetypes=[(T("پایگاه داده SQLite"), "*.sqlite3"), (T("همه فایل‌ها"), "*.*")])
        if not target:
            return
        try:
            self.db.backup_to(target)
        except ValueError as exc:
            return self.error(translate_error(exc))
        except (OSError, sqlite3.Error) as exc:
            return self.error("پشتیبان‌گیری انجام نشد:\n{}", exc)
        self.info("نسخه پشتیبان ایجاد شد.")

    def do_restore(self):
        source = filedialog.askopenfilename(
            parent=self, filetypes=[(T("پایگاه داده SQLite"), "*.sqlite3"), (T("همه فایل‌ها"), "*.*")])
        if not source:
            return
        if os.path.abspath(source) == os.path.abspath(self.db.path):
            return self.warn("فایل انتخاب‌شده همین پایگاه داده فعلی است.")
        if not self.confirm("تمام اطلاعات فعلی با پشتیبان جایگزین شود؟"):
            return
        try:
            self.db.restore_from(source)
        except ValueError as exc:
            code = str(exc)
            if code in ERROR_MESSAGES or re.fullmatch(r"[a-z0-9_-]+", code):
                return self.error(translate_error(code))
            return self.error("فایل پشتیبان سالم نیست.")
        except (OSError, sqlite3.Error) as exc:
            return self.error("بازیابی انجام نشد:\n{}", exc)
        self.page = "dashboard"
        self.reload_preferences()
        self.info("پشتیبان با موفقیت بازیابی شد.")

    def on_close(self):
        try:
            self.db.auto_backup()
        except ValueError as exc:
            messagebox.showwarning(T("هشدار"), translate_error(exc), parent=self)
        except (OSError, sqlite3.Error) as exc:
            AppLogger.exception(f"Automatic backup failed: {exc}")
            messagebox.showwarning(
                T("هشدار"),
                "پشتیبان‌گیری خودکار انجام نشد. لطفاً از اطلاعات نسخه پشتیبان دستی تهیه کنید.",
                parent=self,
            )
        self.db.close()
        self.destroy()




__all__ = [name for name in globals() if not name.startswith('__')]
