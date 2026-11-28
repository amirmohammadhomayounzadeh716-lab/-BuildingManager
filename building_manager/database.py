from .i18n import *

class Database:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = None
        self.import_error = None
        self._open()

    # ---------------- اتصال و ساختار ----------------
    def _open(self):
        try:
            self.conn = sqlite3.connect(
                self.path, timeout=5, factory=SafeSQLiteConnection
            )
        except sqlite3.Error as exc:
            _raise_database_error(exc)
        try:
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.execute("PRAGMA busy_timeout=5000")
            try:
                self.conn.execute("PRAGMA journal_mode=WAL")
            except (sqlite3.DatabaseError, ValueError) as exc:
                AppLogger.warning(f"Could not enable SQLite WAL mode: {exc}")
            self._settings = None
            self._create_schema()
            self._seed_settings()
            self._migrate()
            # Startup data-integrity steps are required. If one fails, do not
            # continue with a partially initialized database.
            for step_name, step in (
                ("JSON import", self._import_json_if_empty),
                ("income source synchronization", self._sync_income_sources),
                ("unit activity periods", self._ensure_unit_activity_periods),
                ("database normalization", self._normalize),
            ):
                try:
                    step()
                except Exception as exc:
                    AppLogger.exception(f"Required database initialization step failed: {step_name}")
                    raise RuntimeError(
                        f"Database initialization failed during {step_name}"
                    ) from exc
            _secure_storage_permissions(self.path)
        except Exception:
            try:
                self.conn.close()
            except Exception:
                pass
            raise

    def _create_schema(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS income_sources (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS units (
            id INTEGER PRIMARY KEY, number TEXT NOT NULL DEFAULT '', floor TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'مالک', owner TEXT DEFAULT '', tenant TEXT DEFAULT '',
            phone TEXT DEFAULT '', owner_phone TEXT DEFAULT '', tenant_phone TEXT DEFAULT '',
            notes TEXT DEFAULT '', active INTEGER NOT NULL DEFAULT 1,
            inactive_year INTEGER, inactive_month INTEGER, inactive_charge_policy TEXT);
        CREATE TABLE IF NOT EXISTS unit_activity_periods (
            id INTEGER PRIMARY KEY, unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
            start_year INTEGER NOT NULL, start_month INTEGER NOT NULL,
            end_year INTEGER, end_month INTEGER);
        CREATE INDEX IF NOT EXISTS idx_unit_activity_periods_unit
            ON unit_activity_periods(unit_id, start_year, start_month);
        CREATE TABLE IF NOT EXISTS residents (
            id INTEGER PRIMARY KEY, unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
            name TEXT NOT NULL, phone TEXT DEFAULT '', role TEXT NOT NULL DEFAULT 'ساکن', notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS months (
            year INTEGER NOT NULL, month INTEGER NOT NULL,
            charge_per_unit INTEGER NOT NULL DEFAULT 0, payment_per_unit INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(year, month));
        CREATE TABLE IF NOT EXISTS unit_charges (
            year INTEGER NOT NULL, month INTEGER NOT NULL,
            unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
            amount INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(year, month, unit_id));
        CREATE TABLE IF NOT EXISTS unit_payments (
            year INTEGER NOT NULL, month INTEGER NOT NULL,
            unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
            amount INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(year, month, unit_id));
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY, year INTEGER NOT NULL, month INTEGER NOT NULL,
            unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
            amount INTEGER NOT NULL, paid_at TEXT NOT NULL, notes TEXT DEFAULT '',
            payment_type TEXT NOT NULL DEFAULT 'شارژ');
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY, year INTEGER NOT NULL, month INTEGER NOT NULL,
            title TEXT NOT NULL, category TEXT DEFAULT 'سایر', amount INTEGER NOT NULL,
            paid_at TEXT NOT NULL, payer TEXT DEFAULT '', notes TEXT DEFAULT '',
            payment_bank TEXT NOT NULL DEFAULT 'کارت صادرات', account INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS incomes (
            id INTEGER PRIMARY KEY, year INTEGER NOT NULL, month INTEGER NOT NULL,
            title TEXT NOT NULL, category TEXT DEFAULT 'سایر', amount INTEGER NOT NULL,
            received_at TEXT NOT NULL, source TEXT DEFAULT '', notes TEXT DEFAULT '',
            account INTEGER NOT NULL DEFAULT 1);
        CREATE INDEX IF NOT EXISTS idx_payments_ym ON payments(year, month);
        CREATE INDEX IF NOT EXISTS idx_expenses_ym ON expenses(year, month);
        """)
        self.conn.commit()

    def columns(self, table):
        return {r["name"] for r in self.q(f"PRAGMA table_info({table})")}

    def _seed_settings(self):
        legacy = self.conn.execute("SELECT value FROM settings WHERE key='initial_balance'").fetchone()
        for key, value in SETTING_DEFAULTS.items():
            if key == "initial_export_balance" and legacy and legacy["value"]:
                value = legacy["value"]
            self.conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, value))
        self.conn.commit()

    @staticmethod
    def _legacy_income_period(raw_date):
        """سال و ماه را از تاریخ شمسی قدیمی یا تاریخ میلادی ISO استخراج می‌کند."""
        value = normalize_digits(raw_date or "").strip()
        if not value:
            return None
        # وجود T یا : نشانه‌ی قالب ISO است؛ ابتدا فقط تاریخ میلادی بررسی می‌شود.
        if "T" in value or ":" in value:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                year, month, _day = gregorian_to_jalali(parsed.year, parsed.month, parsed.day)
                return year, month
            except (TypeError, ValueError, OverflowError):
                return None
        # تاریخ بدون نشانه‌ی ISO فقط وقتی شمسی است که سال آن در بازه‌ی معقول باشد.
        jalali = parse_shamsi(value[:10])
        if jalali and 1200 <= jalali[0] <= 1600:
            return jalali[0], jalali[1]
        # اگر تاریخ شمسی معتبر نبود، قالب ISO میلادی را هم امتحان می‌کنیم.
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            year, month, _day = gregorian_to_jalali(parsed.year, parsed.month, parsed.day)
            return year, month
        except (TypeError, ValueError, OverflowError):
            return None

    def _migrate(self):
        """مهاجرت ساختار قدیمی را به‌صورت یک تراکنش اتمیک انجام می‌دهد."""
        # SAVEPOINT مانع باقی ماندن ALTER/UPDATEهای نیمه‌کاره در صورت شکست می‌شود.
        # آزمون دستی: migration را با یک ستون نامعتبر متوقف کنید؛ user_version و schema باید ثابت بمانند.
        version = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
        if version >= 3:
            return
        # مقدار اولیه بیرون try خوانایی مسیر پس از commit را حفظ می‌کند.
        # آزمون دستی: migration دیتابیس نسخه‌ی قدیمی را اجرا کنید و backfill فقط پس از commit بررسی شود.
        added_account = False
        self.conn.execute("SAVEPOINT migrate_v3")
        try:
            wanted = {
                "units": [("number", "TEXT NOT NULL DEFAULT ''"), ("active", "INTEGER NOT NULL DEFAULT 1"),
                          ("owner_phone", "TEXT DEFAULT ''"), ("tenant_phone", "TEXT DEFAULT ''"),
                          ("inactive_year", "INTEGER"), ("inactive_month", "INTEGER"),
                          ("inactive_charge_policy", "TEXT")],
                "payments": [("payment_type", "TEXT NOT NULL DEFAULT 'شارژ'")],
                "months": [("payment_per_unit", "INTEGER NOT NULL DEFAULT 0")],
                "expenses": [("payment_bank", "TEXT NOT NULL DEFAULT 'کارت صادرات'"),
                             ("account", "INTEGER NOT NULL DEFAULT 1")],
                "incomes": [("year", "INTEGER NOT NULL DEFAULT 1400"), ("month", "INTEGER NOT NULL DEFAULT 1"),
                            ("title", "TEXT NOT NULL DEFAULT 'درآمد متفرقه'"),
                            ("category", "TEXT DEFAULT 'سایر'"), ("amount", "INTEGER NOT NULL DEFAULT 0"),
                            ("received_at", "TEXT NOT NULL DEFAULT ''"), ("source", "TEXT DEFAULT ''"),
                            ("notes", "TEXT DEFAULT ''"), ("account", "INTEGER NOT NULL DEFAULT 1")],
            }
            added_columns = set()
            for table, items in wanted.items():
                have = self.columns(table)
                for column, ddl in items:
                    if column not in have:
                        self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
                        added_columns.add((table, column))
                        added_account = added_account or (table, column) == ("expenses", "account")
            # تبدیل وضعیت قدیمی نیز پیش از ثبت نسخه‌ی جدید انجام می‌شود تا رفتار قبلی حفظ شود.
            self.conn.execute(
                "UPDATE units SET status=? WHERE status=?", (ST_OWNER, LEGACY_ST_VACANT)
            )
            income_columns = self.columns("incomes")
            if "paid_at" in income_columns and "received_at" in income_columns:
                self.conn.execute("UPDATE incomes SET received_at=paid_at WHERE received_at='' AND paid_at IS NOT NULL")
            if "date" in income_columns:
                self.conn.execute("UPDATE incomes SET received_at=date WHERE received_at='' AND date IS NOT NULL")
            if "account_id" in income_columns:
                self.conn.execute("UPDATE incomes SET account=account_id WHERE account=1 AND account_id IS NOT NULL")
            if ("incomes", "year") in added_columns or ("incomes", "month") in added_columns:
                for row in self.q("SELECT id, received_at FROM incomes"):
                    period = self._legacy_income_period(row["received_at"])
                    if not period:
                        continue
                    year, month = period
                    # FIX(2): build the backfill UPDATE from only the newly added period columns.
                    assignments, values = [], []
                    if ("incomes", "year") in added_columns:
                        assignments.append("year=?")
                        values.append(year)
                    if ("incomes", "month") in added_columns:
                        assignments.append("month=?")
                        values.append(month)
                    if assignments:
                        values.append(row["id"])
                        self.conn.execute(
                            f"UPDATE incomes SET {', '.join(assignments)} WHERE id=?",
                            tuple(values),
                        )
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_incomes_ym ON incomes(year,month)")
            # برای واحدهای غیرفعال قدیمی، آخرین ماه دارای سابقه مالی سقف شارژ است.
            legacy_inactive = self.q("SELECT id FROM units WHERE active=0 AND inactive_year IS NULL")
            for unit_row in legacy_inactive:
                uid = unit_row["id"]
                last = self.one(
                    "SELECT MAX(y*100+m) AS period FROM ("
                    "SELECT year y,month m FROM payments WHERE unit_id=? UNION ALL "
                    "SELECT year y,month m FROM unit_charges WHERE unit_id=? UNION ALL "
                    "SELECT year y,month m FROM unit_payments WHERE unit_id=?)",
                    (uid, uid, uid))
                period = last["period"] if last else None
                if period:
                    iy, im = divmod(int(period), 100)
                else:
                    iy, im = 1300, 1
                self.conn.execute(
                    "UPDATE units SET inactive_year=?,inactive_month=?,inactive_charge_policy='legacy' WHERE id=?",
                    (iy, im, uid))
            self.conn.execute("PRAGMA user_version=3")
            self.conn.execute("RELEASE migrate_v3")
            self.conn.commit()
        except Exception:
            try:
                self.conn.execute("ROLLBACK TO migrate_v3")
                self.conn.execute("RELEASE migrate_v3")
                self.conn.commit()
            except Exception as rollback_exc:
                AppLogger.exception(f"Migration rollback failed: {rollback_exc}")
            AppLogger.exception("Database migration to version 3 failed")
            raise
        # عملیات وابسته به تنظیمات پس از commit موفق migration اجرا می‌شوند.
        if added_account:
            self._backfill_expense_accounts()

    def _backfill_expense_accounts(self):
        """هزینه‌های قدیمی که با «نام کارت دوم» ثبت شده بودند را به حساب ۲ نسبت می‌دهد."""
        names = {self.get("account2_name"), self.get("account2_pdf"), "کارت سامان", "هزینه اساسی"}
        names.discard("")
        marks = ",".join("?" * len(names))
        self.conn.execute(f"UPDATE expenses SET account=2 WHERE payment_bank IN ({marks})", tuple(names))
        self.conn.commit()

    def _import_json_if_empty(self):
        """فقط وقتی دیتابیس کاملاً خالی است و فایل‌های JSON نسخه‌ی قبلی هست، از آن‌ها بازیابی می‌کند."""
        if (self.val("SELECT COUNT(*) FROM units") or self.val("SELECT COUNT(*) FROM payments")
                or self.val("SELECT COUNT(*) FROM expenses") or self.val("SELECT COUNT(*) FROM incomes")):
            return
        folder = next((d for d in JSON_DIRS if os.path.exists(os.path.join(d, JSON_FILES["units"]))), None)
        if not folder:
            return
        try:
            data = {}
            for table, filename in JSON_FILES.items():
                path = os.path.join(folder, filename)
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data[table] = json.load(f)
            # سازگاری با نام ستون‌های رایج در نسخه‌های قدیمی درآمدهای متفرقه
            for row in data.get("incomes", []) or []:
                if "received_at" not in row:
                    row["received_at"] = row.get("paid_at", row.get("date", ""))
                if "account" not in row and "account_id" in row:
                    row["account"] = row["account_id"]
                if "year" not in row or "month" not in row:
                    period = self._legacy_income_period(row.get("received_at"))
                    if not period:
                        period = (current_shamsi_year(), current_shamsi_month())
                    row.setdefault("year", period[0])
                    row.setdefault("month", period[1])
            with self.conn:
                for table in ("settings", "categories", "units", "residents", "months", "unit_charges",
                              "unit_payments", "payments", "expenses", "incomes"):
                    rows = data.get(table) or []
                    if not rows:
                        continue
                    have = self.columns(table)
                    cols = [c for c in rows[0].keys() if c in have]
                    if not cols:
                        continue
                    sql = (f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) "
                           f"VALUES ({','.join('?' for _ in cols)})")
                    self.conn.executemany(sql, [tuple(r.get(c) for c in cols) for r in rows])
            self._settings = None
            self._backfill_expense_accounts()
        except Exception as exc:
            self.conn.rollback()
            self.import_error = f"{type(exc).__name__}: {exc}"

    def _normalize(self):
        # تخصیص از مجموعه‌ی شماره‌های عددی موجود انجام می‌شود تا شماره‌ی ثبت‌شده تداخل نکند.
        # آزمون دستی: شماره‌های ۱ و ۳ و یک خانه‌ی خالی بسازید؛ خالی باید ۲ بگیرد و اجرای دوباره تغییری ندهد.
        version = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
        if version < 2:
            self.conn.execute(
                "UPDATE units SET status=? WHERE status=?", (ST_OWNER, LEGACY_ST_VACANT)
            )
            self.conn.execute("PRAGMA user_version=2")
        # تفکیک شماره‌های ثبت‌شده از اعداد مثبت مانع تداخل و بازنویسی شناسه‌های متنی می‌شود.
        # آزمون دستی: واحدهای ۱، ۳ و خالی بسازید؛ واحد خالی باید ۲ بگیرد و اجرای دوباره تغییری ندهد.
        used_numbers = set()
        used_numeric = set()
        for row in self.q(
            "SELECT number FROM units WHERE number IS NOT NULL AND TRIM(number) <> ''"
        ):
            value = str(row["number"]).strip()
            used_numbers.add(value)
            try:
                numeric_value = int(value)
                if numeric_value > 0:
                    used_numeric.add(numeric_value)
            except (TypeError, ValueError):
                # شماره‌های غیرعددی حفظ می‌شوند، اما در جست‌وجوی عدد بعدی دخالت ندارند.
                continue
        empty_units = self.q(
            "SELECT id FROM units WHERE number IS NULL OR TRIM(number) = '' ORDER BY id"
        )
        for row in empty_units:
            candidate = 1
            while candidate in used_numeric:
                candidate += 1
            value = str(candidate)
            self.conn.execute("UPDATE units SET number=? WHERE id=?", (value, row["id"]))
            used_numbers.add(value)
            used_numeric.add(candidate)
        if self.get("categories_initialized", "0") != "1":
            if not self.val("SELECT COUNT(*) FROM categories"):
                for i, name in enumerate(DEFAULT_CATEGORIES):
                    self.conn.execute("INSERT OR IGNORE INTO categories(name,sort_order) VALUES(?,?)", (name, i))
            self.conn.execute("INSERT INTO settings(key,value) VALUES('categories_initialized','1') "
                              "ON CONFLICT(key) DO UPDATE SET value='1'")
            self._settings = None
        self.conn.commit()

    # ---------------- ابزارهای سطح پایین ----------------
    def q(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    def one(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()

    def val(self, sql, params=(), default=0):
        row = self.one(sql, params)
        return row[0] if row and row[0] is not None else default

    def exe(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    @staticmethod
    def _require_positive_amount(value, field="مبلغ"):
        try:
            amount = int(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"{field}-invalid") from None
        if amount <= 0:
            raise ValueError(f"{field}-must-be-positive")
        return amount

    @staticmethod
    def _require_nonnegative_amount(value, field="مبلغ"):
        try:
            amount = int(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"{field}-invalid") from None
        if amount < 0:
            raise ValueError(f"{field}-must-not-be-negative")
        return amount

    @staticmethod
    def _validated_period(raw_date, fallback_year=None, fallback_month=None):
        # تاریخ اصلی در صورت معتبر بودن اولویت دارد و fallback نادیده گرفته می‌شود.
        parsed = parse_shamsi(raw_date) if str(raw_date or "").strip() else None
        if parsed:
            year, month, _day = parsed
            if 1 <= year <= 9999 and 1 <= month <= 12:
                return year, month
        # در نبود تاریخ معتبر، سال و ماه جایگزین باید هر دو معتبر باشند.
        if fallback_year is not None or fallback_month is not None:
            # وجود هرکدام از اجزای fallback یعنی هر دو باید ارائه و معتبر باشند.
            if fallback_year is None or fallback_month is None:
                raise ValueError("invalid-period")
            try:
                fy, fm = int(fallback_year), int(fallback_month)
            except (TypeError, ValueError, OverflowError):
                raise ValueError("invalid-period") from None
            if 1 <= fy <= 9999 and 1 <= fm <= 12:
                return fy, fm
            raise ValueError("invalid-period")
        # اگر تاریخ ورودی خالی یا نامعتبر باشد و fallback ارائه نشده باشد، خطای تاریخ می‌دهیم.
        raise ValueError("invalid-shamsi-date")

    def close(self):
        try:
            self.conn.commit()
            self.conn.close()
        except sqlite3.Error:
            pass

    # ---------------- تنظیمات ----------------
    def get(self, key, default=_UNSET):
        """تنظیم ذخیره‌شده را می‌خواند؛ default صریح حتی اگر None یا صفر باشد حفظ می‌شود.

        آزمون دستی: get('missing', None) باید None و get('missing') باید رشته‌ی خالی بدهد.
        """
        if self._settings is None:
            self._settings = {r["key"]: r["value"] for r in self.q("SELECT key,value FROM settings")}
        value = self._settings.get(key, _UNSET)
        if value is _UNSET:
            value = SETTING_DEFAULTS.get(key, "") if default is _UNSET else default
        return value

    def set(self, key, value):
        self.set_many({key: value})

    def set_many(self, mapping):
        with self.conn:
            for key, value in mapping.items():
                self.conn.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
        if self._settings is not None:
            self._settings.update({k: str(v) for k, v in mapping.items()})
        # تغییرات تنظیمات بدون نگهداری کش محاسباتی انجام می‌شوند.

    def get_money(self, key):
        try:
            return parse_money(self.get(key) or 0)
        except ValueError:
            return 0

    def accounts(self):
        return {
            "multi": self.get("multi_account_enabled") == "1",
            "names": [self.get("account1_name") or "کارت صادرات", self.get("account2_name") or "کارت سامان"],
            "pdf": [self.get("account1_pdf") or "حساب هزینه های جاری",
                    self.get("account2_pdf") or "حساب هزینه های اساسی"],
        }

    # ---------------- دسته‌بندی هزینه‌ها ----------------
    def categories(self):
        return [r["name"] for r in self.q("SELECT name FROM categories ORDER BY sort_order,id")]

    def category_usage(self, name):
        return self.val("SELECT COUNT(*) FROM expenses WHERE category=?", (name,))

    def add_category(self, name):
        order = self.val("SELECT COALESCE(MAX(sort_order),-1)+1 FROM categories")
        self.exe("INSERT INTO categories(name,sort_order) VALUES(?,?)", (name, order))

    def rename_category(self, old, new):
        with self.conn:
            self.conn.execute("UPDATE categories SET name=? WHERE name=?", (new, old))
            self.conn.execute("UPDATE expenses SET category=? WHERE category=?", (new, old))

    def delete_category(self, name):
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO categories(name,sort_order) VALUES('سایر',999)")
            self.conn.execute("UPDATE expenses SET category='سایر' WHERE category=?", (name,))
            self.conn.execute("DELETE FROM categories WHERE name=?", (name,))

    # ---------------- دسته‌بندی منبع درآمد ----------------
    def _sync_income_sources(self):
        """منابع درآمد را با حذف فاصله‌های یونیکد و بدون UPDATE تکراری همگام می‌کند."""
        # حذف فاصله‌های یونیکد از داده‌ی قدیمی، تطبیق منبع درآمد را بدون تغییر متن داخلی حفظ می‌کند.
        # آزمون دستی: source=" برق\u00a0" بسازید؛ پس از اجرا باید دقیقاً «برق» ذخیره شود.
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO income_sources(name,sort_order) VALUES('سایر',999)")
            rows = self.conn.execute("SELECT id, source FROM incomes").fetchall()
            sources = set()
            for row in rows:
                original = row["source"]
                cleaned = str(original or "").strip()
                if not cleaned:
                    cleaned = "سایر"
                if cleaned != original:
                    self.conn.execute("UPDATE incomes SET source=? WHERE id=?", (cleaned, row["id"]))
                sources.add(cleaned)
            for name in sorted(sources):
                order = self.conn.execute(
                    "SELECT COALESCE(MAX(sort_order),-1)+1 FROM income_sources"
                ).fetchone()[0]
                self.conn.execute(
                    "INSERT OR IGNORE INTO income_sources(name,sort_order) VALUES(?,?)", (name, order)
                )

    def income_sources(self):
        return [r["name"] for r in self.q("SELECT name FROM income_sources ORDER BY sort_order,id")]

    def income_source_usage(self, name):
        return self.val("SELECT COUNT(*) FROM incomes WHERE source=?", (name,))

    def add_income_source(self, name):
        order = self.val("SELECT COALESCE(MAX(sort_order),-1)+1 FROM income_sources")
        self.exe("INSERT INTO income_sources(name,sort_order) VALUES(?,?)", (name, order))

    def rename_income_source(self, old, new):
        with self.conn:
            self.conn.execute("UPDATE income_sources SET name=? WHERE name=?", (new, old))
            self.conn.execute("UPDATE incomes SET source=? WHERE source=?", (new, old))

    def delete_income_source(self, name):
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO income_sources(name,sort_order) VALUES('سایر',999)")
            self.conn.execute("UPDATE incomes SET source='سایر' WHERE source=?", (name,))
            self.conn.execute("DELETE FROM income_sources WHERE name=?", (name,))

    # ---------------- واحدها ----------------
    def _accounting_start_period(self):
        row = self.one(
            "SELECT MIN(period) AS period FROM ("
            "SELECT year*100+month AS period FROM months UNION ALL "
            "SELECT year*100+month FROM payments UNION ALL "
            "SELECT year*100+month FROM expenses UNION ALL "
            "SELECT year*100+month FROM incomes UNION ALL "
            "SELECT year*100+month FROM unit_charges UNION ALL "
            "SELECT year*100+month FROM unit_payments)"
        )
        if row and row["period"]:
            return divmod(int(row["period"]), 100)
        # اگر واحد قدیمی هست اما هیچ سابقه مالی وجود ندارد، شروع از ابتدای
        # تقویم جاری بدهی ناخواسته می‌سازد؛ ۱۳۰۰/۰۱ مرز خنثی و سازگار است.
        if self.val("SELECT COUNT(*) FROM units"):
            return 1300, 1
        return current_shamsi_year(), current_shamsi_month()

    def _ensure_unit_activity_periods(self):
        """برای واحدهای قدیمی بازه تاریخی می‌سازد؛ همه‌ی درج‌ها اتمیک هستند."""
        start_year, start_month = self._accounting_start_period()
        # اگر درج هر واحدی شکست بخورد، تمام درج‌های همین مرحله rollback می‌شوند؛
        # بنابراین هیچ واحدی به‌صورت تصادفی بدون بازه‌ی فعالیت باقی نمی‌ماند.
        with self.conn:
            existing_unit_ids = {
                row["unit_id"] for row in self.conn.execute(
                    "SELECT unit_id FROM unit_activity_periods"
                )
            }
            missing_periods = []
            for unit in self.conn.execute("SELECT * FROM units"):
                if unit["id"] in existing_unit_ids:
                    continue
                end_year = unit["inactive_year"] if not unit["active"] else None
                end_month = unit["inactive_month"] if not unit["active"] else None
                missing_periods.append(
                    (unit["id"], start_year, start_month, end_year, end_month)
                )
            if missing_periods:
                self.conn.executemany(
                    "INSERT INTO unit_activity_periods"
                    "(unit_id,start_year,start_month,end_year,end_month) VALUES(?,?,?,?,?)",
                    missing_periods,
                )

    def _close_activity_period(self, unit_id, year, month):
        """بستن آخرین بازهٔ باز؛ تراکنش را فراخواننده مدیریت می‌کند."""
        return self.conn.execute(
            "UPDATE unit_activity_periods SET end_year=?,end_month=? "
            "WHERE id=(SELECT id FROM unit_activity_periods WHERE unit_id=? "
            "AND end_year IS NULL ORDER BY start_year DESC,start_month DESC,id DESC LIMIT 1)",
            (year, month, unit_id))

    def units(self, include_inactive=False):
        sql = "SELECT * FROM units" + ("" if include_inactive else " WHERE active=1")
        return sorted(self.q(sql), key=lambda r: (natural_key(r["number"]), r["id"]))

    def unit(self, unit_id):
        return self.one("SELECT * FROM units WHERE id=?", (unit_id,))

    def next_unit_number(self):
        numbers = [int(normalize_digits(r["number"])) for r in self.q("SELECT number FROM units")
                   if normalize_digits(r["number"]).strip().isdigit()]
        return str(max(numbers) + 1) if numbers else "1"

    def unit_number_exists(self, number, exclude_id=None):
        target = normalize_digits(number).strip().lower()
        return any(normalize_digits(r["number"]).strip().lower() == target and r["id"] != exclude_id
                   for r in self.q("SELECT id, number FROM units"))

    def save_unit(self, unit_id, d, year=None, month=None):
        """ذخیرهٔ واحد و بازهٔ فعالیت آن به‌صورت اتمیک."""
        try:
            year = int(year if year is not None else current_shamsi_year())
            month = int(month if month is not None else current_shamsi_month())
        except (TypeError, ValueError, OverflowError):
            raise ValueError("invalid-year-month") from None
        if not 1 <= year <= 9999 or not 1 <= month <= 12:
            raise ValueError("invalid-year-month")

        values = (d["number"], d["floor"], d["status"], d["owner"], d["owner_phone"],
                  d.get("tenant", ""), d.get("tenant_phone", ""), d["notes"],
                  1 if d.get("active", True) else 0)
        # واحد و بازهٔ فعالیت باید با هم ثبت شوند یا با هم rollback شوند.
        with self.conn:
            if unit_id is None:
                cur = self.conn.execute(
                    "INSERT INTO units(number,floor,status,owner,owner_phone,tenant,tenant_phone,notes,active) "
                    "VALUES(?,?,?,?,?,?,?,?,?)", values)
                new_id = cur.lastrowid
                if values[-1]:
                    self.conn.execute(
                        "INSERT INTO unit_activity_periods(unit_id,start_year,start_month) VALUES(?,?,?)",
                        (new_id, year, month))
                else:
                    if year < 1 or month < 1:
                        raise ValueError("invalid-year-month")
                    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
                    if prev_year < 1:
                        raise ValueError("invalid-year-month")
                    self.conn.execute(
                        "INSERT INTO unit_activity_periods(unit_id,start_year,start_month,end_year,end_month) "
                        "VALUES(?,?,?,?,?)", (new_id, year, month, prev_year, prev_month))
            else:
                old = self.conn.execute("SELECT * FROM units WHERE id=?", (unit_id,)).fetchone()
                if old is None:
                    raise ValueError("واحد موردنظر پیدا نشد.")
                was_active, will_be_active = bool(old["active"]), bool(d.get("active", True))
                if was_active and not will_be_active:
                    policy = self.get("inactive_unit_charge_policy", "next_month")
                    if year < 1 or month < 1:
                        raise ValueError("invalid-year-month")
                    stop_year, stop_month = (year, month) if policy == "next_month" else (
                        (year - 1, 12) if month == 1 else (year, month - 1))
                    if stop_year < 1:
                        raise ValueError("invalid-year-month")
                    self._close_activity_period(unit_id, stop_year, stop_month)
                    self.conn.execute(
                        "UPDATE units SET number=?,floor=?,status=?,owner=?,owner_phone=?,tenant=?,tenant_phone=?,"
                        "notes=?,active=0,inactive_year=?,inactive_month=?,inactive_charge_policy=? WHERE id=?",
                        values[:-1] + (stop_year, stop_month, policy, unit_id))
                elif not was_active and will_be_active:
                    self.conn.execute(
                        "UPDATE units SET number=?,floor=?,status=?,owner=?,owner_phone=?,tenant=?,tenant_phone=?,"
                        "notes=?,active=1,inactive_year=NULL,inactive_month=NULL,inactive_charge_policy=NULL WHERE id=?",
                        values[:-1] + (unit_id,))
                    self.conn.execute(
                        "INSERT INTO unit_activity_periods(unit_id,start_year,start_month) VALUES(?,?,?)",
                        (unit_id, year, month))
                else:
                    self.conn.execute(
                        "UPDATE units SET number=?,floor=?,status=?,owner=?,owner_phone=?,tenant=?,tenant_phone=?,"
                        "notes=?,active=? WHERE id=?", values + (unit_id,))
        return new_id if unit_id is None else unit_id

    def unit_record_count(self, unit_id):
        return sum(self.val(f"SELECT COUNT(*) FROM {t} WHERE unit_id=?", (unit_id,))
                   for t in ("payments", "unit_charges", "unit_payments"))

    def remove_unit(self, unit_id, year=None, month=None):
        """واحد دارای سابقه یا ماه شارژ بایگانی می‌شود؛ تغییرات اتمیک هستند."""
        with self.conn:
            unit = self.conn.execute("SELECT * FROM units WHERE id=?", (unit_id,)).fetchone()
            if unit is None:
                return "deleted"
            record_count = sum(
                self.conn.execute(f"SELECT COUNT(*) FROM {table} WHERE unit_id=?", (unit_id,)).fetchone()[0]
                for table in ("payments", "unit_charges", "unit_payments"))
            if record_count:
                if unit["active"]:
                    try:
                        year = int(year if year is not None else current_shamsi_year())
                        month = int(month if month is not None else current_shamsi_month())
                    except (TypeError, ValueError, OverflowError):
                        raise ValueError("invalid-year-month") from None
                    if not 1 <= year <= 9999 or not 1 <= month <= 12:
                        raise ValueError("invalid-year-month")
                    policy = self.get("inactive_unit_charge_policy", "next_month")
                    if year < 1 or month < 1:
                        raise ValueError("invalid-year-month")
                    stop_year, stop_month = (year, month) if policy == "next_month" else (
                        (year - 1, 12) if month == 1 else (year, month - 1))
                    if stop_year < 1:
                        raise ValueError("invalid-year-month")
                    self._close_activity_period(unit_id, stop_year, stop_month)
                    self.conn.execute(
                        "UPDATE units SET active=0,inactive_year=?,inactive_month=?,inactive_charge_policy=? WHERE id=?",
                        (stop_year, stop_month, policy, unit_id))
                result = "archived"
            else:
                self.conn.execute("DELETE FROM residents WHERE unit_id=?", (unit_id,))
                self.conn.execute("DELETE FROM units WHERE id=?", (unit_id,))
                result = "deleted"
        return result

    def unit_counts(self):
        return {
            "units": self.val("SELECT COUNT(*) FROM units WHERE active=1"),
            "owners": self.val("SELECT COUNT(*) FROM units WHERE active=1 AND status=?", (ST_OWNER,)),
            "tenants": self.val("SELECT COUNT(*) FROM units WHERE active=1 AND status=?", (ST_TENANT,)),
        }

    @staticmethod
    def payer_name(unit, kind=None):
        """نام مسئول پرداخت: شارژ مصرفی=مستأجرِ ثبت‌شده (در صورت نبود، مالک)، پرداختی=مالک."""
        if unit is None:
            return ""
        if kind == KIND_CHARGE:
            return (unit["tenant"] or "").strip() or (unit["owner"] or "")
        if kind == KIND_CONTRIB:
            return unit["owner"] or ""
        if (unit["tenant"] or "").strip():
            return unit["tenant"]
        return unit["owner"] or ""

    @staticmethod
    def payer_phone(unit, kind=None):
        if unit is None:
            return ""
        if kind == KIND_CHARGE:
            return (unit["tenant_phone"] or "").strip() or (unit["owner_phone"] or "")
        if kind == KIND_CONTRIB:
            return unit["owner_phone"] or ""
        if (unit["tenant"] or "").strip():
            return unit["tenant_phone"] or ""
        return unit["owner_phone"] or ""

    # ---------------- پرداخت‌ها و هزینه‌ها ----------------
    def payments(self, year, month):
        rows = self.q("SELECT p.*, u.number AS unit_number, u.status AS unit_status, u.owner, u.tenant "
                      "FROM payments p LEFT JOIN units u ON u.id=p.unit_id "
                      "WHERE p.year=? AND p.month=?", (year, month))
        # ترتیب اولیه‌ی پرداختی‌ها در نصب جدید: شماره‌ی واحد به‌صورت طبیعی (۱، ۲، ۱۰).
        return sorted(rows, key=lambda row: natural_key(row["unit_number"] or ""))

    def payment(self, payment_id):
        return self.one("SELECT * FROM payments WHERE id=?", (payment_id,))

    def save_payment(self, payment_id, d):
        kind = d.get("kind")
        amount = self._require_nonnegative_amount(d.get("amount"), "payment-amount")
        if kind not in (KIND_CHARGE, KIND_CONTRIB):
            raise ValueError("invalid-payment-type")
        try:
            unit_id = int(d.get("unit_id"))
        except (TypeError, ValueError, OverflowError):
            raise ValueError("invalid-unit") from None
        if self.unit(unit_id) is None:
            raise ValueError("unit-not-found")
        period = self._validated_period(d.get("paid_at"), d.get("year"), d.get("month"))
        values = (unit_id, kind, amount, d["paid_at"], d.get("notes", ""))
        if payment_id is None:
            self.exe("INSERT INTO payments(unit_id,payment_type,amount,paid_at,notes,year,month) "
                     "VALUES(?,?,?,?,?,?,?)", values + period)
        else:
            self.exe("UPDATE payments SET unit_id=?,payment_type=?,amount=?,paid_at=?,notes=?,year=?,month=? WHERE id=?",
                     values + period + (payment_id,))

    def delete_payment(self, payment_id):
        self.exe("DELETE FROM payments WHERE id=?", (payment_id,))

    def expenses(self, year, month):
        # جدیدترین هزینه ابتدا نمایش داده می‌شود؛ مبلغ در ترتیب پیش‌فرض نقشی ندارد.
        return self.q("SELECT * FROM expenses WHERE year=? AND month=? "
                      "ORDER BY paid_at DESC, id DESC", (year, month))

    def expense(self, expense_id):
        return self.one("SELECT * FROM expenses WHERE id=?", (expense_id,))

    def save_expense(self, expense_id, d):
        amount = self._require_positive_amount(d.get("amount"), "expense-amount")
        period = self._validated_period(d.get("paid_at"), d.get("year"), d.get("month"))
        try:
            account = int(d.get("account", 1))
        except (TypeError, ValueError, OverflowError):
            raise ValueError("invalid-account") from None
        if account not in (1, 2):
            raise ValueError("invalid-account")
        title = str(d.get("title", "")).strip()
        if not title:
            raise ValueError("expense-title-required")
        values = (title, d.get("category") or "سایر", amount, d["paid_at"], account, d.get("notes", ""))
        if expense_id is None:
            self.exe("INSERT INTO expenses(title,category,amount,paid_at,account,notes,year,month) "
                     "VALUES(?,?,?,?,?,?,?,?)", values + period)
        else:
            self.exe("UPDATE expenses SET title=?,category=?,amount=?,paid_at=?,account=?,notes=?,year=?,month=? WHERE id=?",
                     values + period + (expense_id,))

    def delete_expense(self, expense_id):
        self.exe("DELETE FROM expenses WHERE id=?", (expense_id,))

    def incomes(self, year, month):
        return self.q("SELECT * FROM incomes WHERE year=? AND month=? ORDER BY amount DESC, id DESC", (year, month))

    def income(self, income_id):
        return self.one("SELECT * FROM incomes WHERE id=?", (income_id,))

    def save_income(self, income_id, d):
        amount = self._require_positive_amount(d.get("amount"), "income-amount")
        period = self._validated_period(d.get("received_at"), d.get("year"), d.get("month"))
        try:
            account = int(d.get("account", 1))
        except (TypeError, ValueError, OverflowError):
            raise ValueError("invalid-account") from None
        if account not in (1, 2):
            raise ValueError("invalid-account")
        title = str(d.get("title", "")).strip()
        if not title:
            raise ValueError("income-title-required")
        values = (title, d.get("category", "سایر"), amount, d["received_at"],
                  d.get("source", ""), account, d.get("notes", ""))
        if income_id is None:
            self.exe("INSERT INTO incomes(title,category,amount,received_at,source,account,notes,year,month) "
                     "VALUES(?,?,?,?,?,?,?,?,?)", values + period)
        else:
            self.exe("UPDATE incomes SET title=?,category=?,amount=?,received_at=?,source=?,account=?,notes=?,year=?,month=? WHERE id=?",
                     values + period + (income_id,))

    def delete_income(self, income_id):
        self.exe("DELETE FROM incomes WHERE id=?", (income_id,))

    # ---------------- شارژ و پرداختیِ تعیین‌شده ----------------
    def set_default_assessment(self, kind, year, month, amount, through_year_end=False):
        if kind not in ASSESS:
            raise ValueError("invalid-assessment-type")
        amount = self._require_nonnegative_amount(amount, "assessment-amount")
        year, month = int(year), int(month)
        if not (1 <= year <= 9999 and 1 <= month <= 12):
            raise ValueError("invalid-period")
        column = ASSESS[kind][0]
        last = 12 if through_year_end else month
        with self.conn:
            for m in range(month, last + 1):
                self.conn.execute(
                    f"INSERT INTO months(year,month,{column}) VALUES(?,?,?) "
                    f"ON CONFLICT(year,month) DO UPDATE SET {column}=excluded.{column}", (year, m, amount))

    def default_assessment(self, kind, year, month):
        column = ASSESS[kind][0]
        return self.val(f"SELECT {column} FROM months WHERE year=? AND month=?", (year, month))

    def unit_overrides(self, kind, year, month):
        table = ASSESS[kind][1]
        return {r["unit_id"]: r["amount"]
                for r in self.q(f"SELECT unit_id, amount FROM {table} WHERE year=? AND month=?", (year, month))}

    def set_unit_overrides(self, kind, year, month, mapping):
        if kind not in ASSESS:
            raise ValueError("invalid-assessment-type")
        year, month = int(year), int(month)
        if not (1 <= year <= 9999 and 1 <= month <= 12):
            raise ValueError("invalid-period")
        table = ASSESS[kind][1]
        with self.conn:
            for unit_id, amount in mapping.items():
                if amount is not None:
                    amount = self._require_nonnegative_amount(amount, "unit-assessment")
                if self.unit(unit_id) is None:
                    raise ValueError("unit-not-found")
                if amount is None:
                    self.conn.execute(f"DELETE FROM {table} WHERE year=? AND month=? AND unit_id=?",
                                      (year, month, unit_id))
                else:
                    self.conn.execute(
                        f"INSERT INTO {table}(year,month,unit_id,amount) VALUES(?,?,?,?) "
                        f"ON CONFLICT(year,month,unit_id) DO UPDATE SET amount=excluded.amount",
                        (year, month, unit_id, amount))

    # ---------------- محاسبات مالی ----------------
    def _ledger(self):
        # داده‌های دفترکل و بازه‌های فعالیت هر واحد فقط یک‌بار در هر محاسبه خوانده می‌شوند.
        defaults = {(r["year"], r["month"]): (r["charge_per_unit"] or 0, r["payment_per_unit"] or 0)
                    for r in self.q("SELECT year,month,charge_per_unit,payment_per_unit FROM months")}
        overrides = {KIND_CHARGE: {}, KIND_CONTRIB: {}}
        for kind, (_, table) in ASSESS.items():
            for r in self.q(f"SELECT year,month,unit_id,amount FROM {table}"):
                overrides[kind][(r["year"], r["month"], r["unit_id"])] = r["amount"]
        paid = {}
        for r in self.q("SELECT year,month,unit_id,COALESCE(payment_type,'شارژ') AS kind,SUM(amount) AS total "
                        "FROM payments GROUP BY year,month,unit_id,kind"):
            paid[(r["kind"], r["year"], r["month"], r["unit_id"])] = r["total"] or 0
        start = self.val(
            "SELECT MIN(y) FROM (SELECT MIN(year) y FROM months UNION ALL SELECT MIN(year) FROM payments "
            "UNION ALL SELECT MIN(year) FROM expenses UNION ALL SELECT MIN(year) FROM incomes "
            "UNION ALL SELECT MIN(year) FROM unit_charges UNION ALL SELECT MIN(year) FROM unit_payments)",
            default=None) or current_shamsi_year()
        all_units = self.units(include_inactive=True)
        periods = {}
        for r in self.q(
            "SELECT unit_id,start_year,start_month,end_year,end_month "
            "FROM unit_activity_periods ORDER BY unit_id,start_year,start_month,id"
        ):
            periods.setdefault(r["unit_id"], []).append(r)
        return {
            "defaults": defaults,
            "over": overrides,
            "paid": paid,
            "start": int(start),
            "active": [r["id"] for r in all_units],
            "units": {r["id"]: dict(r) for r in all_units},
            "periods": periods,
        }

    @staticmethod
    def _assessment_from_ledger(ledger, kind, year, month, unit_id):
        """محاسبه‌ی سهم با دفترکل از قبل بارگذاری‌شده؛ بدون مراجعه‌ی تکراری به دیتابیس."""
        if kind not in ASSESS:
            return 0
        if unit_id not in ledger["units"]:
            return 0

        periods = ledger["periods"].get(unit_id, ())
        in_active_period = any(
            (year, month) >= (p["start_year"], p["start_month"])
            and (p["end_year"] is None or (year, month) <= (p["end_year"], p["end_month"]))
            for p in periods
        )
        if not in_active_period:
            return 0

        override = ledger["over"][kind].get((year, month, unit_id))
        if override is not None:
            return override
        default = ledger["defaults"].get((year, month))
        if not default:
            return 0
        return default[0 if kind == KIND_CHARGE else 1]

    def assessment(self, kind, year, month, unit_id):
        """حق‌السهم هر حساب را مستقل می‌خواند؛ روش محاسبه برای هر دو یکسان است."""
        return self._assessment_from_ledger(self._ledger(), kind, year, month, unit_id)

    def paid_amount(self, kind, year, month, unit_id):
        return self._ledger()["paid"].get((kind, year, month, unit_id), 0)

    def _statement_from_ledger(self, ledger, kind, year, month, unit_id):
        """محاسبه‌ی گردش حساب با استفاده از یک دفترکل مشترک برای تمام ماه‌ها."""
        debt = credit = 0
        y, m = ledger["start"], 1
        while (y, m) < (year, month):
            assessed = self._assessment_from_ledger(ledger, kind, y, m, unit_id)
            paid = ledger["paid"].get((kind, y, m, unit_id), 0)
            debt += max(0, assessed - paid)
            credit += max(0, paid - assessed)
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        net = credit - debt
        prev_debt, prev_credit = max(0, -net), max(0, net)
        share = self._assessment_from_ledger(ledger, kind, year, month, unit_id)
        paid_now = ledger["paid"].get((kind, year, month, unit_id), 0)
        # «قابل واریز» مبلغ ناخالص بدهی قبلی + حق‌السهم این ماه است.
        # بستانکاری قبلی در ستون مستقل می‌ماند و فقط هنگام محاسبه‌ی مانده از آن کسر می‌شود.
        # مانده هرگز منفی نمی‌شود؛ اضافه‌پرداخت در دفترکل ماه بعد به‌صورت بستانکاری منتقل خواهد شد.
        payable = prev_debt + share
        balance = max(0, payable - prev_credit - paid_now)
        return {"prev_debt": prev_debt, "prev_credit": prev_credit, "share": share, "paid": paid_now,
                "payable": payable, "balance": balance}

    def statement(self, kind, year, month, unit_id):
        """وضعیت حساب یک واحد در یک ماه: بدهی/بستانکاری قبلی، حق‌السهم، قابل واریز و مانده."""
        return self._statement_from_ledger(self._ledger(), kind, year, month, unit_id)

    def total_assessed(self, kind, year, month):
        ledger = self._ledger()
        return sum(
            self._assessment_from_ledger(ledger, kind, year, month, uid)
            for uid in ledger["active"]
        )

    def outstanding(self, kind, year, month):
        ledger = self._ledger()
        return sum(
            self._statement_from_ledger(ledger, kind, year, month, uid)["balance"]
            for uid in ledger["active"]
        )

    def status_counts(self, year, month):
        complete = partial = unpaid = 0
        ledger = self._ledger()
        for uid in ledger["active"]:
            paid = ledger["paid"].get((KIND_CHARGE, year, month, uid), 0)
            statement = self._statement_from_ledger(ledger, KIND_CHARGE, year, month, uid)
            payable = statement["payable"]
            if payable <= 0 and paid <= 0:
                continue  # برای این واحد در این ماه بدهی یا شارژی وجود ندارد
            if statement["balance"] <= 0:
                complete += 1
            elif paid > 0:
                partial += 1
            else:
                unpaid += 1
        return complete, partial, unpaid

    def _flows(self):
        # جریان‌های مالی مستقیماً از پایگاه داده خوانده می‌شوند.
        multi = self.accounts()["multi"]
        flows = {}

        def slot(y, m):
            return flows.setdefault((y, m), [0, 0, 0, 0, 0, 0])

        for r in self.q("SELECT year,month,COALESCE(payment_type,'شارژ') AS kind,SUM(amount) AS s "
                        "FROM payments GROUP BY year,month,kind"):
            if r["kind"] == KIND_CHARGE:
                slot(r["year"], r["month"])[0] += r["s"] or 0
            elif r["kind"] == KIND_CONTRIB:
                # جریان شارژ و پرداختی همیشه جدا نگهداری می‌شوند تا گزارش‌ها
                # با ریزتراکنش‌ها تطبیق داشته باشند؛ تجمیع فقط در محاسبه موجودی انجام می‌شود.
                slot(r["year"], r["month"])[1] += r["s"] or 0
        for r in self.q("SELECT year,month,account,SUM(amount) AS s FROM expenses GROUP BY year,month,account"):
            index = 3 if (multi and r["account"] == 2) else 2
            slot(r["year"], r["month"])[index] += r["s"] or 0
        for r in self.q("SELECT year,month,account,SUM(amount) AS s FROM incomes GROUP BY year,month,account"):
            index = 5 if (multi and r["account"] == 2) else 4
            slot(r["year"], r["month"])[index] += r["s"] or 0
        return flows

    def flow(self, year, month):
        return tuple(self._flows().get((year, month), ZERO_FLOW))

    def _chain(self):
        # زنجیره‌ی موجودی از جریان‌های فعلی ساخته می‌شود و کش ندارد.
        flows = self._flows()
        multi = self.accounts()["multi"]
        initial1 = self.get_money("initial_export_balance")
        initial2 = self.get_money("initial_saman_balance")
        # در حالت نمایش تک‌حسابی، موجودی اولیه‌ی هر دو حساب در یک موجودی تجمیع می‌شود.
        # مقادیر اصلی تنظیمات تغییر نمی‌کنند؛ با فعال‌سازی دوباره‌ی چندحسابی جدا خواهند بود.
        init = (initial1 if multi else initial1 + initial2, initial2 if multi else 0)
        chain, first, last = {}, None, None
        if flows:
            keys = sorted(flows)
            first, last = keys[0], keys[-1]
            o1, o2 = init
            y, m = first
            while (y, m) <= last:
                f = flows.get((y, m), ZERO_FLOW)
                if multi:
                    c1 = o1 + f[0] + f[4] - f[2]
                    c2 = o2 + f[1] + f[5] - f[3]
                else:
                    # در حالت تک‌حسابی تمام گردش‌های مالی در موجودی تجمیعی حساب اول‌اند.
                    c1 = o1 + f[0] + f[1] + f[4] - f[2]
                    c2 = 0
                chain[(y, m)] = (o1, o2, c1, c2)
                o1, o2 = c1, c2
                y, m = (y + 1, 1) if m == 12 else (y, m + 1)
            final = (o1, o2)
        else:
            final = init
        result = {"chain": chain, "first": first, "last": last, "init": init, "final": final}
        return result

    def balances(self, year, month):
        """موجودی ابتدا و انتهای ماه برای هر دو حساب."""
        c = self._chain()
        key = (year, month)
        if c["first"] is None or key < c["first"]:
            o1, o2 = c["init"]
            e1, e2 = o1, o2
        elif key > c["last"]:
            o1, o2 = e1, e2 = c["final"]
        else:
            o1, o2, e1, e2 = c["chain"][key]
        return {"open": (o1, o2), "end": (e1, e2)}

    def current_balances(self):
        return self._chain()["final"]

    def overview(self, year, month):
        """همه‌ی اعدادِ خلاصه‌ی مالی یک ماه (برای صفحه‌ی خلاصه و گزارش PDF)."""
        f = self.flow(year, month)
        counts = self.status_counts(year, month)
        return {
            "balances": self.balances(year, month),
            "charge_assessed": self.total_assessed(KIND_CHARGE, year, month),
            "contrib_assessed": self.total_assessed(KIND_CONTRIB, year, month),
            "charge_received": f[0], "contrib_received": f[1],
            "expense1": f[2], "expense2": f[3],
            "income1": f[4], "income2": f[5],
            "charge_due": self.outstanding(KIND_CHARGE, year, month),
            "contrib_due": self.outstanding(KIND_CONTRIB, year, month),
            "counts": counts,
        }

    def expense_by_category(self, year):
        return self.q("SELECT category, SUM(amount) AS total FROM expenses WHERE year=? "
                      "GROUP BY category ORDER BY total DESC, category", (year,))

    def income_by_source(self, year):
        return self.q("SELECT source, SUM(amount) AS total FROM incomes WHERE year=? "
                      "GROUP BY source ORDER BY total DESC, source", (year,))

    # ---------------- پشتیبان‌گیری ----------------
    def _safe_backup_to(self, path):
        # مسیر مقصد و فایل‌های جانبی قبلی حذف می‌شوند تا VACUUM INTO خطای وجود فایل ندهد.
        target = os.path.abspath(os.fspath(path))
        if target == os.path.abspath(self.path):
            raise ValueError("backup-target-is-current-database")
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(target + suffix)
            except FileNotFoundError:
                pass
        # ابتدا snapshot یکپارچه شامل تغییرات WAL در یک فایل مستقل ساخته می‌شود.
        try:
            self.conn.commit()
            self.conn.execute("VACUUM INTO ?", (target,))
            self.conn.commit()
            return
        except (sqlite3.Error, OSError, ValueError) as exc:
            AppLogger.warning(f"VACUUM INTO backup failed; using database sidecar copy: {exc}")
        # در صورت شکست VACUUM INTO، خود دیتابیس و هر دو فایل جانبی کپی می‌شوند.
        for suffix in ("", "-wal", "-shm"):
            source = self.path + suffix
            destination = target + suffix
            if os.path.exists(source):
                shutil.copy2(source, destination)
            elif suffix:
                try:
                    os.remove(destination)
                except FileNotFoundError:
                    pass
        self.conn.commit()

    def backup_to(self, target):
        # تمام مسیرهای پشتیبان‌گیری از یک پیاده‌سازی امن استفاده می‌کنند.
        self._safe_backup_to(target)

    def auto_backup(self, keep=10):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        name = datetime.now().strftime("building_%Y%m%d_%H%M%S_%f.sqlite3")
        self.backup_to(os.path.join(BACKUP_DIR, name))
        files = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith("building_") and f.endswith(".sqlite3"))
        for old in files[:-keep]:
            try:
                os.remove(os.path.join(BACKUP_DIR, old))
            except OSError:
                pass

    def restore_from(self, source):
        """اعتبارسنجی و مهاجرت نسخه پشتیبان روی فایل موقت؛ دیتابیس جاری در خطا حفظ می‌شود."""
        required = {
            "settings": {"key", "value"}, "categories": {"id", "name"},
            "units": {"id", "status"}, "residents": {"id", "unit_id", "name"},
            "months": {"year", "month"}, "unit_charges": {"year", "month", "unit_id", "amount"},
            "unit_payments": {"year", "month", "unit_id", "amount"},
            "payments": {"id", "year", "month", "unit_id", "amount", "paid_at"},
            "expenses": {"id", "year", "month", "title", "amount", "paid_at"},
        }
        source = os.path.abspath(source)
        if source == os.path.abspath(self.path):
            raise ValueError("same-database")
        tmp = self.path + ".restore_tmp"
        probe = sqlite3.connect(source)
        try:
            check = probe.execute("PRAGMA integrity_check").fetchone()
            tables = {r[0] for r in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not check or check[0] != "ok" or not set(required) <= tables:
                raise ValueError("invalid-backup")
            for table, columns in required.items():
                actual = {r[1] for r in probe.execute(f'PRAGMA table_info("{table}")')}
                if not columns <= actual:
                    raise ValueError(f"invalid-schema:{table}")
            if os.path.exists(tmp):
                os.remove(tmp)
            temp_conn = sqlite3.connect(tmp)
            try:
                probe.backup(temp_conn)
            finally:
                temp_conn.close()
        finally:
            probe.close()

        # مهاجرت روی کپی آزمایشی انجام می‌شود؛ نسخه اصلی هنوز دست‌نخورده است.
        old_json_dirs = JSON_DIRS[:]
        try:
            JSON_DIRS.clear()
            candidate = Database(tmp)
            try:
                integrity = candidate.one("PRAGMA integrity_check")
                fk_errors = candidate.q("PRAGMA foreign_key_check")
                if not integrity or integrity[0] != "ok" or fk_errors:
                    raise ValueError("invalid-migrated-backup")
                for table, columns in {
                    "units": {"number", "active", "owner_phone", "tenant_phone"},
                    "payments": {"payment_type"}, "months": {"payment_per_unit"},
                    "expenses": {"account", "payment_bank"},
                    "incomes": {"id", "year", "month", "title", "amount", "received_at", "account"},
                }.items():
                    if not columns <= candidate.columns(table):
                        raise ValueError(f"invalid-migrated-schema:{table}")
            finally:
                candidate.close()
        except Exception:
            for suffix in ("", "-wal", "-shm"):
                try: os.remove(tmp + suffix)
                except OSError: pass
            raise
        finally:
            JSON_DIRS[:] = old_json_dirs

        # ابتدا نسخه اضطراری می‌سازیم؛ فقط بعد از موفقیت آن دیتابیس را جایگزین می‌کنیم.
        self.backup_to(self.path + ".before_restore.bak")
        self.close()
        try:
            for suffix in ("-wal", "-shm"):
                try: os.remove(self.path + suffix)
                except FileNotFoundError: pass
            os.replace(tmp, self.path)
            self._open()
        except Exception:
            # در صورت شکست جایگزینی یا بازشدن، فایل اضطراری برگردانده می‌شود.
            try:
                if os.path.exists(self.path + ".before_restore.bak"):
                    shutil.copy2(self.path + ".before_restore.bak", self.path)
            finally:
                self._open()
            raise



# ----------------------------------------------------------------------
#  ویجت‌های قابل استفاده‌ی مجدد
# ----------------------------------------------------------------------

__all__ = [name for name in globals() if not name.startswith('__')]
