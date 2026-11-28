#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مدیریت ساختمان — نسخه ۲
========================
برنامه‌ی دسکتاپ (Tkinter + SQLite) برای مدیریت شارژ مصرفی، شارژ مالکانه و هزینه‌های ساختمان.

اجرا:            python BuildingManager.py
کتابخانه‌ها:      pip install reportlab arabic-reshaper python-bidi openpyxl
                 (فقط برای PDF و Excel لازم‌اند؛ خودِ برنامه بدون آن‌ها هم اجرا می‌شود)
فونت PDF:        ویندوز: Tahoma خودکار پیدا می‌شود. روی سیستم‌های دیگر فایل Vazirmatn.ttf
                 را در پوشه‌ی fonts کنار برنامه بگذارید.
داده‌ها:          ~/BuildingManagerData/building.sqlite3   (با نسخه‌های قبلی سازگار است)
پشتیبان خودکار:   ~/BuildingManagerData/backups  (۱۰ نسخه‌ی آخر، هنگام بستن برنامه)
"""
import json
import html
import glob
import logging
import functools
from logging.handlers import RotatingFileHandler
import traceback
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import sys
import tempfile
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

# کتابخانه‌های خروجی سنگین به‌صورت تنبل و فقط هنگام درخواست کاربر بارگذاری می‌شوند.
OPENPYXL_AVAILABLE = False
REPORTLAB_AVAILABLE = False


def _load_openpyxl():
    global OPENPYXL_AVAILABLE, Workbook, Alignment, Font
    if OPENPYXL_AVAILABLE:
        return True
    try:
        from openpyxl import Workbook as _Workbook
        from openpyxl.styles import Alignment as _Alignment, Font as _Font
        Workbook, Alignment, Font = _Workbook, _Alignment, _Font
        OPENPYXL_AVAILABLE = True
        return True
    except ImportError:
        return False


def _load_reportlab():
    global REPORTLAB_AVAILABLE, rl_colors, A4, A5, landscape
    global ParagraphStyle, pdfmetrics, TTFont
    global Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, KeepTogether, PageBreak
    if REPORTLAB_AVAILABLE:
        return True
    try:
        from reportlab.lib import colors as _rl_colors
        from reportlab.lib.pagesizes import A4 as _A4, A5 as _A5, landscape as _landscape
        from reportlab.lib.styles import ParagraphStyle as _ParagraphStyle
        from reportlab.pdfbase import pdfmetrics as _pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont as _TTFont
        from reportlab.platypus import (
            Paragraph as _Paragraph, SimpleDocTemplate as _SimpleDocTemplate,
            Spacer as _Spacer, Table as _Table, TableStyle as _TableStyle,
            KeepTogether as _KeepTogether, PageBreak as _PageBreak
        )
        (rl_colors, A4, A5, landscape, ParagraphStyle, pdfmetrics, TTFont,
         Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, KeepTogether,
         PageBreak) = (
            _rl_colors, _A4, _A5, _landscape, _ParagraphStyle, _pdfmetrics,
            _TTFont, _Paragraph, _SimpleDocTemplate, _Spacer, _Table,
            _TableStyle, _KeepTogether, _PageBreak
        )
        REPORTLAB_AVAILABLE = True
        return True
    except ImportError:
        return False


# ----------------------------------------------------------------------
#  ثبت خطاها و تبدیل خطاهای SQLite
# ----------------------------------------------------------------------
LOG_PATH = os.path.join(os.path.expanduser("~"), "BuildingManagerData", "app.log")


class AppLogger:
    """ثبت خطاها در فایل چرخشی؛ هیچ خروجی‌ای به کنسول ارسال نمی‌شود."""
    _logger = logging.getLogger("BuildingManager")
    _configured = False

    @classmethod
    def _setup(cls):
        if cls._configured:
            return
        try:
            os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
            handler = RotatingFileHandler(
                LOG_PATH, maxBytes=1024 * 1024, backupCount=10, encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s"
            ))
            cls._logger.setLevel(logging.INFO)
            cls._logger.addHandler(handler)
            cls._logger.propagate = False
            cls._configured = True
        except Exception:
            # حتی در صورت شکست ساخت فایل لاگ، logging نباید به stderr برگردد.
            try:
                cls._logger.addHandler(logging.NullHandler())
                logging.lastResort = logging.NullHandler()
            except Exception:
                pass
            cls._configured = True

    @classmethod
    def log(cls, level, message, exc_info=None):
        cls._setup()
        try:
            getattr(cls._logger, level.lower(), cls._logger.error)(
                str(message), exc_info=exc_info
            )
        except Exception:
            pass

    @classmethod
    def info(cls, message):
        cls.log("info", message)

    @classmethod
    def warning(cls, message):
        cls.log("warning", message)

    @classmethod
    def exception(cls, message):
        cls.log("error", message, exc_info=True)


def _sqlite_error_code(exc):
    # کد عددی SQLite مستقل از متن خطا بین سیستم‌عامل‌ها پایدارتر است.
    # آزمون دستی: اتصال فقط‌خواندنی را برای نوشتن استفاده کنید؛ باید db-permission برگردد.
    code = getattr(exc, "sqlite_errorcode", None)
    if code is not None:
        primary_code = int(code) & 0xFF
        if primary_code in (5, 6):
            return "db-locked"
        if primary_code in (11, 26):
            return "db-corrupt"
        if primary_code in (8, 3, 23):
            return "db-permission"
        return "db-error"
    message = str(exc).lower()
    name = type(exc).__name__.lower()
    if "locked" in message or "busy" in message:
        return "db-locked"
    if "malformed" in message or "not a database" in message or "corrupt" in message:
        return "db-corrupt"
    if any(term in message for term in ("readonly", "permission", "access is denied")):
        return "db-permission"
    if "permission" in name:
        return "db-permission"
    return "db-error"


def _raise_database_error(exc):
    code = _sqlite_error_code(exc)
    AppLogger.exception(f"SQLite failure [{code}]: {exc}")
    raise ValueError(code) from None


class SafeSQLiteConnection(sqlite3.Connection):
    """اتصال SQLite که خطاهای پایگاه داده را به کدهای قابل ترجمه تبدیل می‌کند."""
    def execute(self, sql, parameters=(), /):
        try:
            return super().execute(sql, parameters)
        except sqlite3.Error as exc:
            _raise_database_error(exc)

    def executemany(self, sql, seq_of_parameters, /):
        try:
            return super().executemany(sql, seq_of_parameters)
        except sqlite3.Error as exc:
            _raise_database_error(exc)

    def executescript(self, sql_script, /):
        try:
            return super().executescript(sql_script)
        except sqlite3.Error as exc:
            _raise_database_error(exc)

    def commit(self):
        try:
            return super().commit()
        except sqlite3.Error as exc:
            _raise_database_error(exc)

    def rollback(self):
        try:
            return super().rollback()
        except sqlite3.Error as exc:
            _raise_database_error(exc)

    def __exit__(self, exc_type, exc_value, exc_tb):
        try:
            return super().__exit__(exc_type, exc_value, exc_tb)
        except sqlite3.Error as exc:
            _raise_database_error(exc)
            raise  # FIX(8): _raise_database_error always raises; make propagation explicit.


ERROR_MESSAGES = {
    "db-locked": "فایل دیتابیس قفل است. لطفاً برنامه‌های دیگر را ببندید.",
    "db-corrupt": "فایل دیتابیس خراب است. از پشتیبان بازیابی کنید.",
    "db-permission": "دسترسی به فایل دیتابیس ممکن نیست.",
    "db-error": "خطایی در دسترسی به پایگاه داده رخ داد. گزارش خطاها را بررسی کنید.",
    "json-import-failed": "وارد کردن اطلاعات قدیمی از فایل‌های JSON انجام نشد؛ جزئیات خطا: {}",
    "money-decimal-not-allowed": "مبلغ باید عدد صحیح باشد؛ اعشار مجاز نیست.",
    "invalid-shamsi-date": "تاریخ نامعتبر است. نمونه: ۱۴۰۵/۰۲/۱۵",
    "payment-amount-must-not-be-negative": "مبلغ نمی‌تواند منفی باشد.",
    "expense-amount-must-be-positive": "مبلغ باید بیشتر از صفر باشد.",
    "unit-not-found": "واحد پیدا نشد.",
    "invalid-unit": "واحد انتخاب‌شده معتبر نیست.",
    "invalid-account": "حساب انتخاب‌شده معتبر نیست.",
    "invalid-payment-type": "نوع پرداخت معتبر نیست.",
    "expense-title-required": "عنوان هزینه الزامی است.",
    "backup-target-is-current-database": "فایل مقصد نمی‌تواند همان پایگاه داده‌ی فعلی باشد.",
    "invalid-year-month": "سال یا ماه معتبر نیست.",
    "invalid-period": "سال یا ماه معتبر نیست.",
    "payment-amount-invalid": "مبلغ پرداخت باید عددی باشد.",
    "expense-amount-invalid": "مبلغ هزینه باید عددی باشد.",
    "income-amount-invalid": "مبلغ درآمد باید عددی باشد.",
    "income-amount-must-be-positive": "مبلغ باید بیشتر از صفر باشد.",
    "payment-amount-must-be-positive": "مبلغ باید بیشتر از صفر باشد.",
    "assessment-amount-must-not-be-negative": "مبلغ نمی‌تواند منفی باشد.",
    "assessment-amount-invalid": "مبلغ باید عددی باشد.",
    "income-title-required": "عنوان درآمد الزامی است.",
    "invalid-assessment-type": "نوع شارژ یا پرداختی معتبر نیست.",
    "invalid-backup": "فایل پشتیبان سالم نیست.",
    "invalid-migrated-backup": "ساختار فایل پشتیبان معتبر نیست.",
    "same-database": "فایل انتخاب‌شده همین پایگاه داده فعلی است.",
}


def translate_error(code):
    """کد خطای داخلی را به پیام قابل‌فهم فارسی تبدیل می‌کند."""
    if isinstance(code, BaseException):
        code = str(code)
    code = str(code or "")
    if code in ERROR_MESSAGES:
        return ERROR_MESSAGES[code]
    if code.startswith(("invalid-schema:", "invalid-migrated-schema:")):
        return "ساختار فایل پشتیبان با نسخه فعلی برنامه سازگار نیست."
    if code.endswith("-must-not-be-negative"):
        return "مبلغ نمی‌تواند منفی باشد."
    if code.endswith("-must-be-positive"):
        return "مبلغ باید بیشتر از صفر باشد."
    if code.endswith("-invalid"):
        return "مقدار واردشده معتبر نیست."
    if code.startswith("sqlite"):
        return ERROR_MESSAGES["db-error"]
    if code and re.fullmatch(r"[a-z0-9_-]+", code):
        AppLogger.warning(f"translate_error: unknown code {code!r}")  # FIX(7): retain diagnostics for unknown codes.
    return code if code and not re.fullmatch(r"[a-z0-9_-]+", code) else (
        "عملیات انجام نشد. لطفاً ورودی‌ها را بررسی کنید."
    )


# تا زمانی که پنجره‌ی اصلی ساخته نشده، خطاها باید در کنسول چاپ شوند.
_STARTUP_COMPLETE = False


def _print_exception_to_console(exc_type, exc_value, exc_tb, context="Unhandled exception"):
    try:
        print(f"\n[{context}]", file=sys.stderr, flush=True)
        traceback.print_exception(exc_type, exc_value, exc_tb, file=sys.stderr)
        sys.stderr.flush()
    except Exception:
        pass


def _global_exception_hook(exc_type, exc_value, exc_tb):
    _print_exception_to_console(exc_type, exc_value, exc_tb)
    AppLogger.log("error", "Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
    if _STARTUP_COMPLETE:
        try:
            messagebox.showerror(
                "خطای پیش‌بینی‌نشده",
                "خطایی پیش آمد و جزئیات آن در گزارش خطاها ذخیره شد.\n"
                "لطفاً برنامه را دوباره اجرا کنید.",
            )
        except tk.TclError:
            pass
        except Exception:
            pass


sys.excepthook = _global_exception_hook


def _thread_exception_hook(args):
    _print_exception_to_console(
        args.exc_type, args.exc_value, args.exc_traceback,
        context=f"Unhandled exception in thread {getattr(args.thread, 'name', 'unknown')}",
    )
    AppLogger.log(
        "error", "Unhandled thread exception",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


if hasattr(threading, "excepthook"):
    threading.excepthook = _thread_exception_hook


def _secure_storage_permissions(db_path=None):
    """مجوزهای محدود فایل‌ها فقط روی لینوکس و macOS اعمال می‌شود."""
    if db_path is None:
        db_path = DB_PATH
    if os.name == "nt":
        return
    for target, mode in ((db_path, 0o600), (BACKUP_DIR, 0o700)):
        try:
            if os.path.exists(target):
                os.chmod(target, mode)
        except OSError as exc:
            AppLogger.warning(f"Could not chmod {target}: {exc}")



# ----------------------------------------------------------------------
#  ثابت‌ها
# ----------------------------------------------------------------------
APP_VERSION = "18.5"
MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
          "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
SEASONS = [("بهار", 0), ("تابستان", 3), ("پاییز", 6), ("زمستان", 9)]
DEFAULT_CATEGORIES = ["آب", "برق", "گاز", "آسانسور", "نظافت", "تعمیرات",
                      "نگهبانی", "شارژ/قبوض", "بیمه", "سایر"]

# مقادیری که داخل دیتابیس ذخیره می‌شوند (همیشه فارسی؛ هرگز ترجمه نمی‌شوند)
KIND_CHARGE = "شارژ"
KIND_CONTRIB = "پرداختی"
LEGACY_ST_VACANT, ST_OWNER, ST_TENANT = "خالی", "مالک", "مستأجر"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DATA_DIR = os.path.join(os.path.expanduser("~"), "BuildingManagerData")
BACKUP_DIR = os.path.join(APP_DATA_DIR, "backups")
DB_PATH = os.path.join(APP_DATA_DIR, "building.sqlite3")
LEGACY_DB_PATH = os.path.join(BASE_DIR, "building.sqlite3")
JSON_DIRS = [os.path.join(APP_DATA_DIR, "building_data"), os.path.join(BASE_DIR, "building_data")]
JSON_FILES = {
    "settings": "settings.json", "categories": "categories.json", "units": "units.json",
    "residents": "residents.json", "months": "months.json", "unit_charges": "charges.json",
    "unit_payments": "unit_payments.json", "payments": "payments.json",
    "expenses": "expenses.json", "incomes": "incomes.json",
}

SETTING_DEFAULTS = {
    "building_name": "ساختمان من", "address": "", "manager": "", "phone": "",
    "initial_export_balance": "0", "initial_saman_balance": "0",
    "font_size": "normal", "appearance": "light", "language": "fa",
    "multi_account_enabled": "1",
    "inactive_unit_charge_policy": "next_month",
    "account1_name": "کارت صادرات", "account1_pdf": "حساب هزینه های جاری",
    "account2_name": "کارت سامان", "account2_pdf": "حساب هزینه های اساسی",
}

# تنظیمات مرتب‌سازی خروجی‌ها؛ هر کلید مربوط به یک جدول در یک نوع خروجی است.
EXPORT_SORT_FIELDS = {
    "expenses": [
        ("amount_asc", "مبلغ از کم به زیاد"), ("amount_desc", "مبلغ از زیاد به کم"),
        ("date_asc", "تاریخ از قدیم به جدید"), ("date_desc", "تاریخ از جدید به قدیم"),
        ("category_asc", "بر اساس دسته‌بندی"), ("title_asc", "بر اساس عنوان"),
        ("type_asc", "بر اساس نوع هزینه"),
    ],
    "incomes": [
        ("amount_asc", "مبلغ از کم به زیاد"), ("amount_desc", "مبلغ از زیاد به کم"),
        ("date_asc", "تاریخ از قدیم به جدید"), ("date_desc", "تاریخ از جدید به قدیم"),
        ("title_asc", "بر اساس عنوان"), ("type_asc", "بر اساس حساب"),
    ],
    "payments": [
        ("unit_asc", "بر اساس واحدها"), ("amount_asc", "مبلغ از کم به زیاد"),
        ("amount_desc", "مبلغ از زیاد به کم"), ("date_asc", "تاریخ از قدیم به جدید"),
        ("date_desc", "تاریخ از جدید به قدیم"), ("name_asc", "بر اساس نام"),
        ("type_asc", "بر اساس نوع پرداخت"),
    ],
    "debtors": [
        ("unit_asc", "بر اساس واحدها"), ("amount_asc", "مانده از کم به زیاد"),
        ("amount_desc", "مانده از زیاد به کم"), ("name_asc", "بر اساس نام"),
    ],
    "summary": [("amount_asc", "مبلغ از کم به زیاد"), ("amount_desc", "مبلغ از زیاد به کم"),
                ("label_asc", "بر اساس عنوان")],
    "trend": [("date_asc", "تاریخ از قدیم به جدید"), ("date_desc", "تاریخ از جدید به قدیم"),
              ("amount_asc", "موجودی از کم به زیاد"), ("amount_desc", "موجودی از زیاد به کم")],
    "categories": [("amount_asc", "مجموع از کم به زیاد"), ("amount_desc", "مجموع از زیاد به کم"),
                   ("category_asc", "بر اساس دسته‌بندی")],
    "monthly_summary": [("date_asc", "تاریخ از قدیم به جدید"), ("date_desc", "تاریخ از جدید به قدیم")],
}

EXPORT_SORT_TABLES = {
    "pdf_month": [("summary", "گزارش ماهانه — خلاصه مالی"), ("expenses", "گزارش ماهانه — هزینه‌ها"),
                  ("payments", "گزارش ماهانه — دریافتی‌ها"), ("incomes", "گزارش ماهانه — درآمدهای متفرقه")],
    "pdf_annual": [("summary", "گزارش سالانه — خلاصه مالی"), ("trend", "گزارش سالانه — روند ماهانه"),
                   ("categories", "گزارش سالانه — هزینه‌ها بر اساس دسته‌بندی"),
                   ("payments", "گزارش سالانه — دریافتی‌ها"), ("expenses", "گزارش سالانه — هزینه‌ها"),
                   ("incomes", "گزارش سالانه — درآمدهای متفرقه")],
    "pdf_multi": [("summary", "گزارش چندماهه — خلاصه مالی"), ("trend", "گزارش چندماهه — روند ماهانه"),
                  ("categories", "گزارش چندماهه — هزینه‌ها بر اساس دسته‌بندی"),
                  ("payments", "گزارش چندماهه — دریافتی‌ها"), ("expenses", "گزارش چندماهه — هزینه‌ها"),
                  ("incomes", "گزارش چندماهه — درآمدهای متفرقه")],
    "pdf_debtors": [("debtors", "گزارش بدهکاران — جدول بدهکاران")],
    "excel_annual": [("monthly_summary", "Excel سالانه — خلاصه ماهانه"),
                     ("payments", "Excel سالانه — دریافتی‌ها"), ("expenses", "Excel سالانه — هزینه‌ها"),
                     ("incomes", "Excel سالانه — درآمدهای متفرقه")],
    "excel_month": [("payments", "Excel ماهانه — دریافتی‌ها"),
                    ("expenses", "Excel ماهانه — هزینه‌ها"),
                    ("incomes", "Excel ماهانه — درآمدهای متفرقه")],
}


def prepare_storage():
    """پوشه‌ی داده را می‌سازد و دیتابیس معتبر قدیمی را بدون حذف داده پیدا می‌کند."""
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    _secure_storage_permissions()
    if os.path.exists(DB_PATH):
        return

    candidates = []
    if os.path.abspath(LEGACY_DB_PATH) != os.path.abspath(DB_PATH) and os.path.isfile(LEGACY_DB_PATH):
        candidates.append(LEGACY_DB_PATH)
    candidates.extend(sorted(
        (f for f in glob.glob(os.path.join(BASE_DIR, "building_*.sqlite3")) if os.path.isfile(f)),
        reverse=True
    ))

    for source in candidates:
        probe = None
        try:
            probe = sqlite3.connect(
                f"file:{os.path.abspath(source)}?mode=ro", uri=True, timeout=2
            )
            tables = {
                row[0] for row in probe.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "units" not in tables:
                continue
            if probe.execute("SELECT 1 FROM units LIMIT 1").fetchone() is None:
                continue
            probe.close()
            probe = None
            shutil.copy2(source, DB_PATH)
            break
        except (OSError, sqlite3.Error, ValueError) as exc:
            AppLogger.warning(f"Skipped database candidate {source}: {exc}")
        finally:
            if probe is not None:
                try:
                    probe.close()
                except sqlite3.Error:
                    pass
    _secure_storage_permissions()


# ----------------------------------------------------------------------
#  ابزارهای عمومی: عدد، پول، تاریخ شمسی
# ----------------------------------------------------------------------
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_digits(text):
    """ارقام فارسی و عربی را به انگلیسی تبدیل می‌کند."""
    return str(text if text is not None else "").translate(_DIGITS)


def money(value):
    try:
        return f"{int(value or 0):,}"
    except (TypeError, ValueError):
        return "0"


def parse_money(value):
    """متن مبلغ را به عدد صحیح تبدیل می‌کند؛ برای ورودی نامعتبر ValueError می‌دهد.

    آزمون دستی: مقدارهای 1.5 و ۱٫۵ باید money-decimal-not-allowed بدهند.
    """
    text = normalize_digits(value).strip()
    if not text:
        return 0
    # FIX(money-decimals): decimal marks are never valid in whole-toman amounts.
    if "." in text or "٫" in text:
        raise ValueError("money-decimal-not-allowed")

    sign = ""
    if text[0] in "+-":
        sign, text = text[0], text[1:]
    if not text:
        raise ValueError("invalid-money")

    if text.isdigit():
        return int(sign + text)

    # FIX(money-grouping): accept one consistent thousands separator and require 3-digit groups.
    separators = {char for char in text if char in ",٬،" or char.isspace()}
    if len(separators) != 1:
        raise ValueError("money-decimal-not-allowed")
    separator = next(iter(separators))
    if separator.isspace():
        valid_grouping = re.fullmatch(r"\d{1,3}(?:\s\d{3})+", text)
    else:
        valid_grouping = re.fullmatch(r"\d{1,3}(?:" + re.escape(separator) + r"\d{3})+", text)
    if not valid_grouping:
        raise ValueError("money-decimal-not-allowed")

    digits = re.sub(r"[,٬،\s]", "", text)
    return int(sign + digits)


def natural_key(text):
    # هر جزء نوع مشخص دارد تا مقایسه‌ی عدد و رشته باعث TypeError نشود.
    parts = re.split(r"(\d+)", normalize_digits(text).strip().lower())
    return [(0, int(p)) if p.isdigit() else (1, p) for p in parts]


def gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100)
            + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1])
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


def today_parts():
    now = datetime.now()
    return gregorian_to_jalali(now.year, now.month, now.day)


def current_shamsi_year():
    return today_parts()[0]


def current_shamsi_month():
    return today_parts()[1]


def today_shamsi():
    y, m, d = today_parts()
    return f"{y:04d}/{m:02d}/{d:02d}"


def _jalali_to_jdn(year, month, day):
    """تبدیل تاریخ جلالی به JDN با محاسبه‌ی کبیسه‌ی Borkowski.

    is_leap فقط سال‌های ۱ تا ۳۱۷۶ را پشتیبانی می‌کند.
    برای بازه‌ی استاندارد الگوریتم Borkowski (سال‌های ۱ تا ۳۱۷۷) استفاده
    می‌شود؛ بیرون از این بازه، چرخه‌ی حسابی ۲۸۲۰ ساله نقش پشتیبان دارد.
    آزمون دستی: اختلاف JDN اول فروردین ۱۴۰۳ و ۱۴۰۴ باید ۳۶۶ باشد.
    """
    breaks = (-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181,
              1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394,
              2456, 3178)

    def div(a, b):
        return a // b

    def mod(a, b):
        return a - (a // b) * b

    if not (1 <= month <= 12 and 1 <= day <= 31):
        raise ValueError("invalid-shamsi-date")

    if 1 <= year <= 3177:
        gy = year + 621
        leap_j = -14
        jp = breaks[0]
        jump = 0
        for jm in breaks[1:]:
            jump = jm - jp
            if year < jm:
                break
            leap_j += div(jump, 33) * 8 + div(mod(jump, 33), 4)
            jp = jm
        n = year - jp
        leap_j += div(n, 33) * 8 + div(mod(n, 33) + 3, 4)
        if mod(jump, 33) == 4 and jump - n == 4:
            leap_j += 1
        leap_g = div(gy, 4) - div((div(gy, 100) + 1) * 3, 4) - 150
        march = 20 + leap_j - leap_g
        # روز اول فروردین همان سال در تقویم میلادی.
        a = (14 - 3) // 12
        gy2 = gy + 4800 - a
        gm2 = 3 + 12 * a - 3
        start_jdn = (march + (153 * gm2 + 2) // 5 + 365 * gy2
                     + gy2 // 4 - gy2 // 100 + gy2 // 400 - 32045)
        month_offset = (month - 1) * 31 if month <= 7 else 186 + (month - 7) * 30
        return start_jdn + month_offset + day - 1

    # سال بیرون از بازه‌ی معتبر Borkowski با فرمول پشتیبان محاسبه می‌شود.
    AppLogger.warning(f"سال خارج از بازه‌ی استاندارد Borkowski: {year}")
    epbase = year - 474 if year >= 0 else year - 473
    epyear = 474 + (epbase % 2820)
    month_offset = (month - 1) * 31 if month <= 7 else (month - 1) * 30 + 6
    return (day + month_offset + (epyear * 682 - 110) // 2816
            + (epyear - 1) * 365 + (epbase // 2820) * 1029983 + 1948319)


# کش محدود مانع رشد نامحدود حافظه در استفاده‌ی طولانی‌مدت می‌شود.
# FIX(9): bound cached leap-year calculations while preserving the supported range.
@functools.lru_cache(maxsize=4096)
def _is_leap_uncached(year):
    return _jalali_to_jdn(year + 1, 1, 1) - _jalali_to_jdn(year, 1, 1) == 366


def is_leap(year):
    # سال خارج از بازه پیش از ورود به helper برمی‌گردد؛ 3177 نباید سال 3178 را محاسبه کند.
    if not (1 <= year <= 3176):
        return False
    return _is_leap_uncached(year)


def days_in_month(year, month):
    if month <= 6:
        return 31
    if month <= 11:
        return 30
    return 30 if is_leap(year) else 29


def _self_test_jalali():
    """آزمون‌های مرزی تقویم را ثبت می‌کند و در شکست، اجرای برنامه را ادامه می‌دهد.

    آزمون دستی: اجرای برنامه باید آزمون‌های سال‌های ۱۴۰۳ تا ۱۴۰۸ را در شروع بررسی کند.
    """
    tests = (
        ("JDN year 1403->1404 must span 366 days", lambda: _jalali_to_jdn(1404, 1, 1) - _jalali_to_jdn(1403, 1, 1) == 366),
        ("JDN year 1404->1405 must span 365 days", lambda: _jalali_to_jdn(1405, 1, 1) - _jalali_to_jdn(1404, 1, 1) == 365),
        ("JDN year 1405->1406 must span 365 days", lambda: _jalali_to_jdn(1406, 1, 1) - _jalali_to_jdn(1405, 1, 1) == 365),
        ("JDN year 1406->1407 must span 365 days", lambda: _jalali_to_jdn(1407, 1, 1) - _jalali_to_jdn(1406, 1, 1) == 365),
        ("JDN year 1408->1409 must span 366 days", lambda: _jalali_to_jdn(1409, 1, 1) - _jalali_to_jdn(1408, 1, 1) == 366),
        ("is_leap(1399) must be True", lambda: is_leap(1399) is True),
        ("is_leap(1403) must be True", lambda: is_leap(1403) is True),
        ("is_leap(1404) must be False", lambda: is_leap(1404) is False),
        ("is_leap(1407) must be False", lambda: is_leap(1407) is False),
        ("is_leap(1408) must be True", lambda: is_leap(1408) is True),
        # در سال کبیسه، ۲۹ اسفند دو روز تا اول فروردین فاصله دارد و ۳۰ اسفند یک روز.
        ("JDN 1403/12/29 to 1404/01/01 must differ by 2", lambda: _jalali_to_jdn(1404, 1, 1) - _jalali_to_jdn(1403, 12, 29) == 2),
        ("JDN 1403/12/30 to 1404/01/01 must differ by 1", lambda: _jalali_to_jdn(1404, 1, 1) - _jalali_to_jdn(1403, 12, 30) == 1),
        ("days_in_month(1403, 12) must be 30", lambda: days_in_month(1403, 12) == 30),
        ("days_in_month(1404, 12) must be 29", lambda: days_in_month(1404, 12) == 29),
        # FIX(jalali-1405-tests): explicitly cover current-year date parsing and Esfand length.
        ("parse_shamsi 1405/01/01", lambda: parse_shamsi("1405/01/01") == (1405, 1, 1)),
        ("parse_shamsi Persian digits in 1405", lambda: parse_shamsi("۱۴۰۵/۱۲/۲۹") == (1405, 12, 29)),
        ("1405 Esfand has 29 days", lambda: days_in_month(1405, 12) == 29),
        ("1405/12/30 is invalid", lambda: parse_shamsi("1405/12/30") is None),
    )
    # اجرای شرطی تست‌ها حتی با python -O ضروری است؛ assert ساده در آن حالت حذف می‌شود.
    # آزمون دستی: برنامه را با python -O اجرا کنید و مطمئن شوید تست‌ها همچنان بررسی می‌شوند.
    for label, check in tests:
        try:
            if not check():
                raise AssertionError(label)
        except Exception:
            AppLogger.exception(f"_self_test_jalali failed: {label}")


# FIX(1): exercise decimal-like separators and valid grouped thousands at startup.
def _self_test_parse_money():
    checks = (
        ("1,5", "money-decimal-not-allowed"),
        ("1,234", 1234),
        ("1,234,567", 1234567),
        ("1,2345", "money-decimal-not-allowed"),
        ("۱۲٬۳۴۵", 12345),
        ("1٫5", "money-decimal-not-allowed"),
        ("12 345", 12345),
        ("1234", 1234),       # FIX(money-plain-digits): protect ungrouped four-digit values.
        ("50000", 50000),     # FIX(money-five-digits): protect ungrouped five-digit values.
        ("1 2", "money-decimal-not-allowed"),
        ("", 0),
        ("abc", "ValueError"),
    )
    for raw, expected in checks:
        try:
            actual = parse_money(raw)
            if isinstance(expected, str):
                AppLogger.warning(f"_self_test_parse_money failed: {raw!r} should raise {expected}")
            elif actual != expected:
                AppLogger.warning(f"_self_test_parse_money failed: {raw!r}: got {actual!r}, expected {expected!r}")
        except Exception as exc:
            expected_error = (
                str(exc) == expected if expected == "money-decimal-not-allowed"
                else isinstance(exc, ValueError) if expected == "ValueError"
                else False
            )
            if not expected_error:
                AppLogger.exception(f"_self_test_parse_money failed for {raw!r}: {exc}")


# FIX(2): verify the version-2 legacy income schema receives both period columns.
def _self_test_migrate_income_backfill():
    connection = None
    try:
        connection = sqlite3.connect(":memory:", factory=SafeSQLiteConnection)
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE units (
                id INTEGER PRIMARY KEY, status TEXT DEFAULT 'مالک', active INTEGER DEFAULT 1,
                inactive_year INTEGER, inactive_month INTEGER
            );
            CREATE TABLE payments (id INTEGER PRIMARY KEY, year INTEGER, month INTEGER, unit_id INTEGER);
            CREATE TABLE months (year INTEGER, month INTEGER);
            CREATE TABLE expenses (
                id INTEGER PRIMARY KEY, payment_bank TEXT DEFAULT '', account INTEGER DEFAULT 1
            );
            CREATE TABLE incomes (id INTEGER PRIMARY KEY, received_at TEXT);
            CREATE TABLE unit_charges (year INTEGER, month INTEGER, unit_id INTEGER);
            CREATE TABLE unit_payments (year INTEGER, month INTEGER, unit_id INTEGER);
            INSERT INTO incomes(id, received_at) VALUES (1, '1405/02/15');
            PRAGMA user_version=2;
        """)
        db = Database.__new__(Database)
        db.conn = connection
        db._migrate()
        row = connection.execute("SELECT year, month FROM incomes WHERE id=1").fetchone()
        if not row or (row["year"], row["month"]) != (1405, 2):
            AppLogger.warning("_self_test_migrate_income_backfill failed: expected (1405, 2)")
    except Exception as exc:
        AppLogger.exception(f"_self_test_migrate_income_backfill failed: {exc}")
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass



def parse_shamsi(text):
    """«۱۴۰۵/۰۲/۱۵» یا «1405-2-15» → (1405, 2, 15)؛ در غیر این صورت None."""
    m = re.fullmatch(r"(\d{4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})", normalize_digits(text).strip())
    if not m:
        return None
    y, mo, d = (int(g) for g in m.groups())
    # محدودیت سال با بازه‌ی امن is_leap هماهنگ است تا محاسبه‌ی سال بعد از دامنه خارج نشود.
    # آزمون دستی: parse_shamsi("3177/01/01") باید None برگرداند.
    if 1 <= y <= 3176 and 1 <= mo <= 12:
        maximum_day = days_in_month(y, mo)
        if 1 <= d <= maximum_day:
            return y, mo, d
    return None


def default_date_for(year, month):
    """اگر ماهِ نمایش‌داده‌شده ماه جاری باشد امروز؛ وگرنه اول همان ماه."""
    ty, tm, _ = today_parts()
    return today_shamsi() if (year, month) == (ty, tm) else f"{year:04d}/{month:02d}/01"


# ----------------------------------------------------------------------
#  فونت PDF
# ----------------------------------------------------------------------
PDF_FONT = "PersianFont"
PDF_BOLD_FONT = "PersianFont-Bold"
# مسیرهای مشترک فونت فارسی؛ ترتیب جست‌وجو در رابط و PDF یکسان نگه داشته می‌شود.

def register_pdf_font():
    # ثبت فونت جداگانه برای زبان فارسی مانع باقی‌ماندن فونت زبان قبلی در گزارش بعدی می‌شود.
    global PDF_FONT, PDF_BOLD_FONT
    try:
        if not _load_reportlab():
            return False
        lang_tag = "fa" if i18n.lang == "fa" else "default"
        PDF_FONT = f"PersianFont-{lang_tag}"
        PDF_BOLD_FONT = f"PersianFont-Bold-{lang_tag}"
        if i18n.lang == "fa":
            candidates = [
                os.path.join(BASE_DIR, "fonts", "Vazirmatn.ttf"),
                os.path.join(BASE_DIR, "fonts", "Vazirmatn-Regular.ttf"),
                os.path.join(BASE_DIR, "fonts", "tahoma.ttf"),
                os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "tahoma.ttf"),
                "/Library/Fonts/Tahoma.ttf",
                "/System/Library/Fonts/Supplemental/Tahoma.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
        else:
            candidates = [
                os.path.join(BASE_DIR, "fonts", "Vazirmatn.ttf"),
                os.path.join(BASE_DIR, "fonts", "Vazirmatn-Regular.ttf"),
                os.path.join(BASE_DIR, "fonts", "tahoma.ttf"),
                os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "tahoma.ttf"),
                "/Library/Fonts/Tahoma.ttf",
                "/System/Library/Fonts/Supplemental/Tahoma.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
        selected_path = None
        if PDF_FONT not in pdfmetrics.getRegisteredFontNames():
            for path in candidates:
                if os.path.isfile(path):
                    try:
                        pdfmetrics.registerFont(TTFont(PDF_FONT, path))
                        selected_path = path
                        break
                    except Exception:
                        continue
            if selected_path is None:
                return False
        # FIX(6): removed the unused path lookup when the regular font was already registered.
        if PDF_BOLD_FONT not in pdfmetrics.getRegisteredFontNames():
            bold_candidates = [
                os.path.join(BASE_DIR, "fonts", "Vazirmatn-Bold.ttf"),
                os.path.join(BASE_DIR, "fonts", "tahomabd.ttf"),
                os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "tahomabd.ttf"),
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                os.path.join(BASE_DIR, "fonts", "Vazirmatn-Medium.ttf"),
            ]
            for path in bold_candidates:
                if os.path.isfile(path):
                    try:
                        pdfmetrics.registerFont(TTFont(PDF_BOLD_FONT, path))
                        break
                    except Exception:
                        continue
        bold_face = PDF_BOLD_FONT if PDF_BOLD_FONT in pdfmetrics.getRegisteredFontNames() else PDF_FONT
        pdfmetrics.registerFontFamily(PDF_FONT, normal=PDF_FONT, bold=bold_face,
                                      italic=PDF_FONT, boldItalic=bold_face)
        return True
    except Exception as exc:
        AppLogger.exception(f"PDF font registration failed: {exc}")
        return False

# ----------------------------------------------------------------------
#  ترجمه (متن‌های رابط کاربری). کلیدها همان متن فارسی‌اند.
#  اطلاعاتی که کاربر وارد می‌کند (نام‌ها، آدرس‌ها، توضیحات) هرگز ترجمه نمی‌شود.
# ----------------------------------------------------------------------
LANGUAGES = {
    "فارسی": "fa", "English": "en", "العربية": "ar", "Türkçe": "tr",
    "Deutsch": "de", "Français": "fr", "中文": "zh", "日本語": "ja", "한국어": "ko",
}
RTL_LANGS = {"fa", "ar"}
_LANG_ORDER = ["en", "ar", "tr", "de", "fr", "zh", "ja", "ko"]
_ZW = "\u200c"


def _norm_key(text):
    return text.replace(_ZW, "").replace("ي", "ی").replace("ك", "ک").strip()


# کدهای خطا در ERROR_MESSAGES نگهداری می‌شوند؛ _RAW فقط برای ترجمه‌ی متن‌های رابط کاربری است.
# آزمون دستی: T("json-import-failed") باید خود کلید را برگرداند.
_RAW = r"""
شارژ | Charge | رسوم | Aidat | Gebühr | Charge | 物业费 | 管理費 | 관리비
پرداختی | Contribution | مساهمة | Katkı | Beitrag | Contribution | 缴款 | 拠出金 | 분담금
فروردین | Farvardin | فروردين | Farvardin | Farvardin | Farvardin | Farvardin | Farvardin | Farvardin
اردیبهشت | Ordibehesht | أرديبهشت | Ordibehesht | Ordibehescht | Ordibehesht | Ordibehesht | Ordibehesht | Ordibehesht
خرداد | Khordad | خرداد | Khordad | Chordad | Khordad | Khordad | Khordad | Khordad
تیر | Tir | تير | Tir | Tir | Tir | Tir | Tir | Tir
مرداد | Mordad | مرداد | Mordad | Mordad | Mordad | Mordad | Mordad | Mordad
شهریور | Shahrivar | شهريور | Şehrivar | Schahriwar | Shahrivar | Shahrivar | Shahrivar | Shahrivar
مهر | Mehr | مهر | Mehr | Mehr | Mehr | Mehr | Mehr | Mehr
آبان | Aban | آبان | Aban | Aban | Aban | Aban | Aban | Aban
آذر | Azar | آذر | Azar | Azar | Azar | Azar | Azar | Azar
دی | Dey | دي | Dey | Dei | Dey | Dey | Dey | Dey
بهمن | Bahman | بهمن | Bahman | Bahman | Bahman | Bahman | Bahman | Bahman
اسفند | Esfand | إسفند | Esfand | Esfand | Esfand | Esfand | Esfand | Esfand
خالی | Vacant | شاغر | Boş | Leer | Libre | 空置 | 空室 | 공실
مالک | Owner | المالك | Malik | Eigentümer | Propriétaire | 业主 | 所有者 | 소유자
مستأجر | Tenant | المستأجر | Kiracı | Mieter | Locataire | 租户 | 賃借人 | 임차인
بهار | Spring | الربيع | İlkbahar | Frühling | Printemps | 春季 | 春 | 봄
تابستان | Summer | الصيف | Yaz | Sommer | Été | 夏季 | 夏 | 여름
پاییز | Autumn | الخريف | Sonbahar | Herbst | Automne | 秋季 | 秋 | 가을
زمستان | Winter | الشتاء | Kış | Winter | Hiver | 冬季 | 冬 | 겨울
ذخیره | Save | حفظ | Kaydet | Speichern | Enregistrer | 保存 | 保存 | 저장
گزارش ایجاد شد. | Report created. | تم إنشاء التقرير. | Rapor oluşturuldu. | Bericht erstellt. | Rapport créé. | 报告已生成。 | レポートを作成しました。 | 보고서가 생성되었습니다.
واحد | Unit | وحدة | Daire | Einheit | Logement | 单元 | 部屋 | 세대
نام | Name | الاسم | Ad | Name | Nom | 姓名 | 名前 | 이름
نوع | Type | النوع | Tür | Typ | Type | 类型 | 種類 | 유형
واریزی | Amount | المبلغ | Tutar | Betrag | Montant | 金额 | 金額 | 금액
حق‌السهم | Share | الحصة | Pay | Anteil | Quote-part | 应摊份额 | 分担額 | 분담액
بدهکاری ماه‌های قبل | Debt from Previous Months | دين الأشهر السابقة | Önceki Aylardan Borç | Schulden aus Vormonaten | Dette des mois précédents | 往月欠款 | 前月までの未払い | 이전 달 미납액
بستانکاری ماه‌های قبل | Credit from Previous Months | رصيد دائن من الأشهر السابقة | Önceki Aylardan Alacak | Guthaben aus Vormonaten | Crédit des mois précédents | 往月余额 | 前月までの過払い | 이전 달 선납액
قابل واریز | Amount Due | المبلغ المستحق | Ödenecek Tutar | Fälliger Betrag | Montant à payer | 应缴金额 | 支払うべき額 | 납부할 금액
مانده حساب | Balance | الرصيد | Bakiye | Saldo | Solde | 余额 | 残高 | 잔액
تاریخ | Date | التاريخ | Tarih | Datum | Date | 日期 | 日付 | 날짜
توضیحات | Notes | ملاحظات | Notlar | Notizen | Notes | 备注 | メモ | 메모
نوع هزینه | Expense Type | نوع المصروف | Gider Türü | Ausgabenart | Type de dépense | 费用类型 | 経費の種類 | 지출 유형
دسته‌بندی | Category | الفئة | Kategori | Kategorie | Catégorie | 类别 | カテゴリ | 분류
مبلغ | Amount | المبلغ | Tutar | Betrag | Montant | 金额 | 金額 | 금액
عنوان | Title | العنوان | Başlık | Titel | Titre | 标题 | タイトル | 제목
صفحه اصلی | Home | الرئيسية | Ana Sayfa | Startseite | Accueil | 主页 | ホーム | 홈
ثبت ماهانه | Monthly Entry | القيد الشهري | Aylık Kayıt | Monatserfassung | Saisie mensuelle | 月度登记 | 月次入力 | 월별 입력
مدیریت واحدها | Manage Units | إدارة الوحدات | Daireleri Yönet | Einheiten verwalten | Gérer les logements | 管理单元 | 部屋の管理 | 세대 관리
بدهکاران | Debtors | المدينون | Borçlular | Schuldner | Débiteurs | 欠款住户 | 未払い者 | 미납자
تنظیمات | Settings | الإعدادات | Ayarlar | Einstellungen | Paramètres | 设置 | 設定 | 설정
رسید پرداخت | Payment Receipt | إيصال الدفع | Ödeme Makbuzu | Zahlungsbeleg | Reçu de paiement | 付款收据 | 支払い領収書 | 납부 영수증
هزینه‌ها | Expenses | المصروفات | Giderler | Ausgaben | Dépenses | 费用 | 経費 | 지출
فایل Excel ایجاد شد. | The Excel file was created. | تم إنشاء ملف Excel. | Excel dosyası oluşturuldu. | Die Excel-Datei wurde erstellt. | Le fichier Excel a été créé. | Excel 文件已生成。 | Excelファイルを作成しました。 | Excel 파일이 생성되었습니다.
واحد {} | Unit {} | الوحدة {} | Daire {} | Einheit {} | Logement {} | {}号单元 | 部屋 {} | {}호
گزارش مالی سالانه PDF | Annual Financial Report (PDF) | التقرير المالي السنوي PDF | Yıllık Mali Rapor (PDF) | Jahresfinanzbericht (PDF) | Rapport financier annuel (PDF) | 年度财务报告（PDF） | 年次会計レポート（PDF） | 연간 재무 보고서(PDF)
خروجی Excel سالانه | Annual Excel Export | تصدير Excel السنوي | Yıllık Excel Çıktısı | Jahres-Excel-Export | Export Excel annuel | 导出年度Excel | 年次Excelエクスポート | 연간 Excel 내보내기
خروجی Excel ماهانه | Monthly Excel Export | تصدير Excel الشهري | Aylık Excel Çıktısı | Monatlicher Excel-Export | Export Excel mensuel | 导出月度Excel | 月次Excelエクスポート | 월간 Excel 내보내기
Excel ماهانه | Monthly Excel | Excel الشهري | Aylık Excel | Monats-Excel | Excel mensuel | 月度 Excel | 月次 Excel | 월간 Excel
Excel ماهانه — دریافتی‌ها | Monthly Excel — Receipts | Excel الشهري — المقبوضات | Aylık Excel — Tahsilatlar | Monats-Excel — Einnahmen | Excel mensuel — Encaissements | 月度 Excel — 收款 | 月次 Excel — 受取 | 월간 Excel — 수입액
Excel ماهانه — هزینه‌ها | Monthly Excel — Expenses | Excel الشهري — المصروفات | Aylık Excel — Giderler | Monats-Excel — Ausgaben | Excel mensuel — Dépenses | 月度 Excel — 费用 | 月次 Excel — 支出 | 월간 Excel — 지출
Excel ماهانه — درآمدهای متفرقه | Monthly Excel — Miscellaneous Income | Excel الشهري — الإيرادات المتنوعة | Aylık Excel — Diğer Gelirler | Monats-Excel — Sonstige Einnahmen | Excel mensuel — Revenus divers | 月度 Excel — 其他收入 | 月次 Excel — その他の収入 | 월간 Excel — 기타 수입
دسته‌بندی هزینه‌ها | Expense Categories | فئات المصروفات | Gider Kategorileri | Ausgabenkategorien | Catégories de dépenses | 费用类别 | 経費カテゴリ | 지출 분류
تومان | Toman | تومان | Toman | Toman | tomans | 土曼 | トマン | 토만
گزارش PDF | PDF Report | تقرير PDF | PDF Raporu | PDF-Bericht | Rapport PDF | PDF报告 | PDFレポート | PDF 보고서
ثبت پرداخت جدید | Add Payment | تسجيل دفعة جديدة | Yeni Ödeme Ekle | Neue Zahlung erfassen | Nouveau paiement | 新增付款 | 支払いを追加 | 새 납부 등록
ویرایش انتخاب | Edit Selected | تعديل المحدد | Seçileni Düzenle | Auswahl bearbeiten | Modifier la sélection | 编辑所选 | 選択を編集 | 선택 항목 수정
حذف انتخاب | Delete Selected | حذف المحدد | Seçileni Sil | Auswahl löschen | Supprimer la sélection | 删除所选 | 選択を削除 | 선택 항목 삭제
ثبت هزینه جدید | Add Expense | تسجيل مصروف جديد | Yeni Gider Ekle | Neue Ausgabe erfassen | Nouvelle dépense | 新增费用 | 経費を追加 | 새 지출 등록
دسته‌بندی‌ها | Categories | الفئات | Kategoriler | Kategorien | Catégories | 类别 | カテゴリ | 분류
افزودن واحد | Add Unit | إضافة وحدة | Daire Ekle | Einheit hinzufügen | Ajouter un logement | 添加单元 | 部屋を追加 | 세대 추가
ویرایش واحد | Edit Unit | تعديل الوحدة | Daireyi Düzenle | Einheit bearbeiten | Modifier le logement | 编辑单元 | 部屋を編集 | 세대 수정
حذف واحد | Delete Unit | حذف الوحدة | Daireyi Sil | Einheit löschen | Supprimer le logement | 删除单元 | 部屋を削除 | 세대 삭제
خروجی PDF | Export PDF | تصدير PDF | PDF Çıktısı | PDF exportieren | Exporter en PDF | 导出PDF | PDFを出力 | PDF 내보내기
تنظیمات منطقی (چندحسابی) | Account Settings (Multi-account) | إعدادات الحسابات (متعددة) | Hesap Ayarları (Çoklu hesap) | Kontoeinstellungen (Mehrere Konten) | Paramètres des comptes (multi-comptes) | 账户设置（多账户） | アカウント設定（複数口座） | 계정 설정(다중 계좌)
مشخصات کلی ساختمان | General Building Details | تفاصيل المبنى العامة | Genel Bina Bilgileri | Allgemeine Gebäudedaten | Détails généraux du bâtiment | 楼宇基本信息 | 建物の基本情報 | 건물 기본 정보
موجودی اولیه کارت اول | Initial Balance of First Account | الرصيد الابتدائي للحساب الأول | Birinci Hesabın Başlangıç Bakiyesi | Anfangssaldo des ersten Kontos | Solde initial du premier compte | 第一账户初始余额 | 1つ目の口座の初期残高 | 첫 번째 계좌 초기 잔액
موجودی اولیه کارت دوم | Initial Balance of Second Account | الرصيد الابتدائي للحساب الثاني | İkinci Hesabın Başlangıç Bakiyesi | Anfangssaldo des zweiten Kontos | Solde initial du second compte | 第二账户初始余额 | 2つ目の口座の初期残高 | 두 번째 계좌 초기 잔액
تنظیمات ظاهری نرم‌افزار | Software Appearance Settings | إعدادات مظهر البرنامج | Yazılım Görünüm Ayarları | Darstellungseinstellungen der Software | Paramètres d'apparence du logiciel | 软件外观设置 | ソフトウェアの外観設定 | 소프트웨어 화면 설정
مدیریت حساب‌ها و کارت‌های مالی | Manage Accounts & Cards | إدارة الحسابات والبطاقات المالية | Hesap ve Kartları Yönet | Konten und Karten verwalten | Gérer les comptes et cartes | 管理账户与银行卡 | 口座とカードの管理 | 계좌 및 카드 관리
وضعیت چندحسابی | Multi-account Status | حالة الحسابات المتعددة | Çoklu Hesap Durumu | Status Mehrfachkonten | État multi-comptes | 多账户状态 | 複数口座の状態 | 다중 계좌 상태
نسخه پشتیبان ایجاد شد. | Backup created. | تم إنشاء النسخة الاحتياطية. | Yedek oluşturuldu. | Sicherung erstellt. | Sauvegarde créée. | 备份已创建。 | バックアップを作成しました。 | 백업이 생성되었습니다.
پشتیبان با موفقیت بازیابی شد. | Backup restored successfully. | تمت استعادة النسخة الاحتياطية بنجاح. | Yedek başarıyla geri yüklendi. | Sicherung erfolgreich wiederhergestellt. | Sauvegarde restaurée avec succès. | 备份已成功恢复。 | バックアップを復元しました。 | 백업이 복원되었습니다.
خطا | Error | خطأ | Hata | Fehler | Erreur | 错误 | エラー | 오류
برای گزارش PDF نصب کنید:\npip install reportlab | To create PDF reports, install:\npip install reportlab | لإنشاء تقارير PDF ثبّت:\npip install reportlab | PDF raporu için şunu kurun:\npip install reportlab | Für PDF-Berichte installieren Sie:\npip install reportlab | Pour créer des rapports PDF, installez :\npip install reportlab | 生成PDF报告请安装：\npip install reportlab | PDFレポートには次をインストール：\npip install reportlab | PDF 보고서를 만들려면 설치하세요:\npip install reportlab
فونت فارسی برای PDF پیدا نشد. فایل Vazirmatn.ttf را در پوشه‌ی fonts کنار برنامه قرار دهید. | No Persian font was found for PDF. Put Vazirmatn.ttf in the "fonts" folder next to the program. | لم يتم العثور على خط فارسي لـ PDF. ضع ملف Vazirmatn.ttf في مجلد fonts بجانب البرنامج. | PDF için Farsça yazı tipi bulunamadı. Vazirmatn.ttf dosyasını programın yanındaki "fonts" klasörüne koyun. | Für das PDF wurde keine persische Schriftart gefunden. Legen Sie Vazirmatn.ttf in den Ordner „fonts“ neben dem Programm. | Aucune police persane trouvée pour le PDF. Placez Vazirmatn.ttf dans le dossier « fonts » à côté du programme. | 未找到可用于PDF的波斯语字体。请将 Vazirmatn.ttf 放在程序旁的 fonts 文件夹中。 | PDF用のペルシア語フォントが見つかりません。Vazirmatn.ttf をプログラムと同じ場所の fonts フォルダに置いてください。 | PDF용 페르시아어 글꼴을 찾을 수 없습니다. Vazirmatn.ttf를 프로그램 옆 fonts 폴더에 넣으세요.
خلاصه مالی | Financial Summary | الملخص المالي | Mali Özet | Finanzübersicht | Résumé financier | 财务摘要 | 会計サマリー | 재무 요약
گزارش مالی سال {} با موفقیت ایجاد شد. | The financial report for {} was created successfully. | تم إنشاء التقرير المالي لسنة {} بنجاح. | {} yılı mali raporu başarıyla oluşturuldu. | Der Finanzbericht für {} wurde erstellt. | Le rapport financier de {} a été créé avec succès. | {}年度财务报告已成功生成。 | {}年の会計レポートを作成しました。 | {}년 재무 보고서가 생성되었습니다.
پرداخت پیدا نشد. | Payment not found. | لم يتم العثور على الدفعة. | Ödeme bulunamadı. | Zahlung nicht gefunden. | Paiement introuvable. | 未找到该付款。 | 支払いが見つかりません。 | 납부 내역을 찾을 수 없습니다.
رسید ایجاد شد. | Receipt created. | تم إنشاء الإيصال. | Makbuz oluşturuldu. | Beleg erstellt. | Reçu créé. | 收据已生成。 | 領収書を作成しました。 | 영수증이 생성되었습니다.
برای خروجی Excel نصب کنید:\npip install openpyxl | To export Excel files, install:\npip install openpyxl | لتصدير ملفات Excel ثبّت:\npip install openpyxl | Excel çıktısı için şunu kurun:\npip install openpyxl | Für den Excel-Export installieren Sie:\npip install openpyxl | Pour exporter en Excel, installez :\npip install openpyxl | 导出Excel请安装：\npip install openpyxl | Excelに出力するには次をインストール：\npip install openpyxl | Excel로 내보내려면 설치하세요:\npip install openpyxl
مدیریت ساختمان | Building Manager | إدارة المبنى | Bina Yönetimi | Gebäudeverwaltung | Gestion de l'immeuble | 楼宇管理 | 建物管理 | 건물 관리
توجه | Notice | تنبيه | Bilgi | Hinweis | Information | 提示 | お知らせ | 알림
هشدار | Warning | تحذير | Uyarı | Warnung | Avertissement | 警告 | 警告 | 경고
تأیید | Confirm | تأكيد | Onayla | Bestätigen | Confirmer | 确认 | 確認 | 확인
شارژ و پرداختی‌ها | Charges & Contributions | الرسوم والمساهمات | Aidat ve Katkılar | Gebühren & Beiträge | Charges et contributions | 物业费与缴款 | 管理費と拠出金 | 관리비 및 분담금
مجموع واریزی‌ها: {} تومان | Total deposits: {} Toman | إجمالي الإيداعات: {} تومان | Toplam yatırım: {} Toman | Summe der Einzahlungen: {} Toman | Total des versements : {} tomans | 存款合计：{} 土曼 | 入金合計：{} トマン | 입금 합계: {} 토만
ابتدا حداقل یک واحد ثبت کنید. | Please add at least one unit first. | يرجى إضافة وحدة واحدة على الأقل أولاً. | Lütfen önce en az bir daire ekleyin. | Bitte legen Sie zuerst mindestens eine Einheit an. | Veuillez d'abord ajouter au moins un logement. | 请先至少添加一个单元。 | 先に部屋を1つ以上登録してください。 | 먼저 세대를 하나 이상 등록하세요.
ابتدا یک مورد را انتخاب کنید. | Please select an item first. | يرجى اختيار عنصر أولاً. | Lütfen önce bir öğe seçin. | Bitte wählen Sie zuerst einen Eintrag aus. | Veuillez d'abord sélectionner un élément. | 请先选择一项。 | 先に項目を選択してください。 | 먼저 항목을 선택하세요.
یک پرداخت را انتخاب کنید. | Please select a payment. | يرجى اختيار دفعة. | Lütfen bir ödeme seçin. | Bitte wählen Sie eine Zahlung aus. | Veuillez sélectionner un paiement. | 请选择一笔付款。 | 支払いを選択してください。 | 납부 내역을 선택하세요.
مجموع هزینه: {} تومان | Total expenses: {} Toman | إجمالي المصروفات: {} تومان | Toplam gider: {} Toman | Gesamtausgaben: {} Toman | Total des dépenses : {} tomans | 费用合计：{} 土曼 | 経費合計：{} トマン | 지출 합계: {} 토만
هزینه پیدا نشد. | Expense not found. | لم يتم العثور على المصروف. | Gider bulunamadı. | Ausgabe nicht gefunden. | Dépense introuvable. | 未找到该费用。 | 経費が見つかりません。 | 지출 내역을 찾을 수 없습니다.
واحد پیدا نشد. | Unit not found. | لم يتم العثور على الوحدة. | Daire bulunamadı. | Einheit nicht gefunden. | Logement introuvable. | 未找到该单元。 | 部屋が見つかりません。 | 세대를 찾을 수 없습니다.
شماره واحد | Unit Number | رقم الوحدة | Daire No | Einheitsnummer | Numéro du logement | 单元编号 | 部屋番号 | 세대 번호
طبقه | Floor | الطابق | Kat | Etage | Étage | 楼层 | 階 | 층
وضعیت | Status | الحالة | Durum | Status | Statut | 状态 | 状態 | 상태
نام مالک | Owner Name | اسم المالك | Malik Adı | Name des Eigentümers | Nom du propriétaire | 业主姓名 | 所有者名 | 소유자 이름
تلفن مالک | Owner Phone | هاتف المالك | Malik Telefonu | Telefon des Eigentümers | Téléphone du propriétaire | 业主电话 | 所有者の電話 | 소유자 전화
نام مستأجر | Tenant Name | اسم المستأجر | Kiracı Adı | Name des Mieters | Nom du locataire | 租户姓名 | 賃借人名 | 임차인 이름
تلفن مستأجر | Tenant Phone | هاتف المستأجر | Kiracı Telefonu | Telefon des Mieters | Téléphone du locataire | 租户电话 | 賃借人の電話 | 임차인 전화
ابتدا یک واحد را انتخاب کنید. | Please select a unit first. | يرجى اختيار وحدة أولاً. | Lütfen önce bir daire seçin. | Bitte wählen Sie zuerst eine Einheit aus. | Veuillez d'abord sélectionner un logement. | 请先选择一个单元。 | 先に部屋を選択してください。 | 먼저 세대를 선택하세요.
واحد غیرفعال شد. | The unit was deactivated. | تم تعطيل الوحدة. | Daire devre dışı bırakıldı. | Die Einheit wurde deaktiviert. | Le logement a été désactivé. | 单元已停用。 | 部屋を無効にしました。 | 세대가 비활성화되었습니다.
جمع مانده: {} تومان | Total outstanding: {} Toman | إجمالي المتبقي: {} تومان | Toplam kalan: {} Toman | Gesamtrest: {} Toman | Total restant : {} tomans | 余额合计：{} 土曼 | 残高合計：{} トマン | 잔액 합계: {} 토만
مدیریت دسته‌بندی هزینه‌ها | Manage Expense Categories | إدارة فئات المصروفات | Gider Kategorilerini Yönet | Ausgabenkategorien verwalten | Gérer les catégories de dépenses | 管理费用类别 | 経費カテゴリの管理 | 지출 분류 관리
افزودن دسته‌بندی | Add Category | إضافة فئة | Kategori Ekle | Kategorie hinzufügen | Ajouter une catégorie | 添加类别 | カテゴリを追加 | 분류 추가
ویرایش دسته‌بندی | Edit Category | تعديل الفئة | Kategoriyi Düzenle | Kategorie bearbeiten | Modifier la catégorie | 编辑类别 | カテゴリを編集 | 분류 수정
فایل انتخاب‌شده همین پایگاه داده فعلی است. | The selected file is the current database itself. | الملف المحدد هو قاعدة البيانات الحالية نفسها. | Seçilen dosya mevcut veritabanının kendisi. | Die gewählte Datei ist die aktuelle Datenbank. | Le fichier sélectionné est la base de données actuelle. | 所选文件就是当前数据库。 | 選択したファイルは現在のデータベースです。 | 선택한 파일은 현재 데이터베이스입니다.
تمام اطلاعات فعلی با پشتیبان جایگزین شود؟ | Replace all current data with the backup? | هل تريد استبدال جميع البيانات الحالية بالنسخة الاحتياطية؟ | Tüm mevcut veriler yedekle değiştirilsin mi? | Alle aktuellen Daten durch die Sicherung ersetzen? | Remplacer toutes les données actuelles par la sauvegarde ? | 要用备份替换当前所有数据吗？ | 現在のデータをすべてバックアップで置き換えますか？ | 현재 모든 데이터를 백업으로 교체할까요?
برای نمایش درست فارسی در PDF نصب کنید:\npip install arabic-reshaper python-bidi | To display Persian text correctly in PDFs, install:\npip install arabic-reshaper python-bidi | لعرض الفارسية بشكل صحيح في PDF ثبّت:\npip install arabic-reshaper python-bidi | PDF'te Farsçanın doğru görünmesi için kurun:\npip install arabic-reshaper python-bidi | Damit Persisch im PDF korrekt angezeigt wird, installieren Sie:\npip install arabic-reshaper python-bidi | Pour afficher correctement le persan dans les PDF, installez :\npip install arabic-reshaper python-bidi | 要在PDF中正确显示波斯语，请安装：\npip install arabic-reshaper python-bidi | PDFでペルシア語を正しく表示するには次をインストール：\npip install arabic-reshaper python-bidi | PDF에서 페르시아어를 올바르게 표시하려면 설치하세요:\npip install arabic-reshaper python-bidi
ساخت یا ذخیره PDF ناموفق بود:\n{} | Creating or saving the PDF failed:\n{} | فشل إنشاء أو حفظ ملف PDF:\n{} | PDF oluşturulamadı veya kaydedilemedi:\n{} | PDF konnte nicht erstellt oder gespeichert werden:\n{} | Échec de la création ou de l'enregistrement du PDF :\n{} | 生成或保存PDF失败：\n{} | PDFの作成または保存に失敗しました：\n{} | PDF를 만들거나 저장하지 못했습니다:\n{}
تلفن | Phone | الهاتف | Telefon | Telefon | Téléphone | 电话 | 電話 | 전화
بدهی ماه‌های قبل | Debt from Previous Months | دين الأشهر السابقة | Önceki Aylardan Borç | Schulden aus Vormonaten | Dette des mois précédents | 往月欠款 | 前月までの未払い | 이전 달 미납액
پرداخت‌شده | Paid | مدفوع | Ödenen | Bezahlt | Payé | 已付 | 支払済み | 납부액
مانده | Remaining | المتبقي | Kalan | Rest | Reste | 余额 | 残り | 잔액
ذخیره‌ی فایل انجام نشد:\n{} | Could not save the file:\n{} | تعذر حفظ الملف:\n{} | Dosya kaydedilemedi:\n{} | Die Datei konnte nicht gespeichert werden:\n{} | Impossible d'enregistrer le fichier :\n{} | 无法保存文件：\n{} | ファイルを保存できませんでした：\n{} | 파일을 저장하지 못했습니다:\n{}
پشتیبان‌گیری | Back up | نسخ احتياطي | Yedekle | Sichern | Sauvegarder | 备份 | バックアップ | 백업
بازیابی پشتیبان | Restore backup | استعادة النسخة الاحتياطية | Yedeği geri yükle | Sicherung wiederherstellen | Restaurer la sauvegarde | 恢复备份 | バックアップを復元 | 백업 복원
خروج | Exit | خروج | Çıkış | Beenden | Quitter | 退出 | 終了 | 종료
پرونده | File | ملف | Dosya | Datei | Fichier | 文件 | ファイル | 파일
واحدها | Units | الوحدات | Daireler | Einheiten | Logements | 单元 | 部屋 | 세대
مالکان | Owners | المالكون | Malikler | Eigentümer | Propriétaires | 业主 | 所有者 | 소유자
مستأجران | Tenants | المستأجرون | Kiracılar | Mieter | Locataires | 租户 | 賃借人 | 임차인
موجودی فعلی {} | Current balance: {} | الرصيد الحالي: {} | Güncel bakiye: {} | Aktueller Kontostand: {} | Solde actuel : {} | 当前余额：{} | 現在の残高：{} | 현재 잔액: {}
شروع ماه {} | Start of month: {} | بداية الشهر: {} | Ay başı: {} | Monatsanfang: {} | Début du mois : {} | 月初：{} | 月初：{} | 월초: {}
پایان ماه {} | End of month: {} | نهاية الشهر: {} | Ay sonu: {} | Monatsende: {} | Fin du mois : {} | 月末：{} | 月末：{} | 월말: {}
کل شارژ تعیین‌شده | Total assessed charge | إجمالي الرسوم المحددة | Belirlenen toplam aidat | Festgelegte Gesamtgebühr | Total des charges fixées | 已设定物业费合计 | 設定済み管理費合計 | 책정된 관리비 합계
واریزی شارژ به {} | Charge deposits to {} | إيداعات الرسوم إلى {} | {} hesabına aidat yatırımı | Gebühreneingänge auf {} | Versements de charges vers {} | 物业费存入 {} | 管理費の入金先 {} | 관리비 입금: {}
بدهی شارژ واحدها | Units' charge debt | ديون رسوم الوحدات | Dairelerin aidat borcu | Gebührenschulden der Einheiten | Dettes de charges des logements | 各单元物业费欠款 | 部屋の管理費未払い | 세대 관리비 미납액
هزینه از {} | Expenses from {} | المصروفات من {} | {} kaynaklı gider | Ausgaben von {} | Dépenses depuis {} | 来自 {} 的支出 | {} からの経費 | {} 지출
پرداخت انتخاب‌شده حذف شود؟ | Delete the selected payment? | هل تريد حذف الدفعة المحددة؟ | Seçilen ödeme silinsin mi? | Die gewählte Zahlung löschen? | Supprimer le paiement sélectionné ? | 要删除所选付款吗？ | 選択した支払いを削除しますか？ | 선택한 납부를 삭제할까요?
مبلغ باید عددی باشد. | The amount must be a number. | يجب أن يكون المبلغ رقماً. | Tutar sayı olmalıdır. | Der Betrag muss eine Zahl sein. | Le montant doit être un nombre. | 金额必须是数字。 | 金額は数値で入力してください。 | 금액은 숫자여야 합니다.
این مبلغ برای {} تا پایان سال {} اعمال شود؟ | Apply this amount from {} to the end of year {}? | هل تريد تطبيق هذا المبلغ من {} حتى نهاية السنة {}؟ | Bu tutar {} ayından {} yılı sonuna kadar uygulansın mı? | Diesen Betrag ab {} bis zum Ende des Jahres {} anwenden? | Appliquer ce montant de {} jusqu'à la fin de l'année {} ? | 是否将此金额从 {} 应用到 {} 年底？ | この金額を {} から {} 年末まで適用しますか？ | 이 금액을 {}부터 {}년 말까지 적용할까요?
حذف انجام نشد:\n{} | Deletion failed:\n{} | فشل الحذف:\n{} | Silme başarısız:\n{} | Löschen fehlgeschlagen:\n{} | Échec de la suppression :\n{} | 删除失败：\n{} | 削除に失敗しました：\n{} | 삭제에 실패했습니다:\n{}
ویرایش پرداخت | Edit Payment | تعديل الدفعة | Ödemeyi Düzenle | Zahlung bearbeiten | Modifier le paiement | 编辑付款 | 支払いを編集 | 납부 수정
ثبت پرداخت | Record Payment | تسجيل دفعة | Ödeme Kaydet | Zahlung erfassen | Enregistrer un paiement | 登记付款 | 支払いを記録 | 납부 기록
هزینه انتخاب‌شده حذف شود؟ | Delete the selected expense? | هل تريد حذف المصروف المحدد؟ | Seçilen gider silinsin mi? | Die gewählte Ausgabe löschen? | Supprimer la dépense sélectionnée ? | 要删除所选费用吗？ | 選択した経費を削除しますか？ | 선택한 지출을 삭제할까요?
ویرایش هزینه | Edit Expense | تعديل المصروف | Gideri Düzenle | Ausgabe bearbeiten | Modifier la dépense | 编辑费用 | 経費を編集 | 지출 수정
ثبت هزینه | Record Expense | تسجيل مصروف | Gider Kaydet | Ausgabe erfassen | Enregistrer une dépense | 登记费用 | 経費を記録 | 지출 기록
فعال | Enabled | مفعّل | Etkin | Aktiv | Activé | 启用 | 有効 | 활성
وضعیت واحد | Unit Status | حالة الوحدة | Daire Durumu | Einheitenstatus | Statut du logement | 单元状态 | 部屋の状態 | 세대 상태
واحد فعال است | Unit is active | الوحدة نشطة | Daire aktif | Einheit ist aktiv | Logement actif | 单元启用中 | 有効な部屋 | 활성 세대
این شماره‌ی واحد قبلاً ثبت شده است. | This unit number already exists. | رقم الوحدة هذا مسجل مسبقاً. | Bu daire numarası zaten kayıtlı. | Diese Einheitennummer existiert bereits. | Ce numéro de logement existe déjà. | 该单元编号已存在。 | この部屋番号は既に登録されています。 | 이미 등록된 세대 번호입니다.
این واحد سابقه‌ی مالی دارد؛ برای حفظ تاریخچه‌ی پرداخت‌ها حذف نمی‌شود و غیرفعال می‌شود. ادامه می‌دهید؟ | This unit has financial history. To keep the payment history it will be deactivated instead of deleted. Continue? | لهذه الوحدة سجل مالي. للحفاظ على تاريخ المدفوعات سيتم تعطيلها بدلاً من حذفها. هل تريد المتابعة؟ | Bu dairenin mali geçmişi var. Ödeme geçmişini korumak için silinmek yerine devre dışı bırakılacak. Devam edilsin mi? | Diese Einheit hat Buchungen. Um die Zahlungshistorie zu erhalten, wird sie deaktiviert statt gelöscht. Fortfahren? | Ce logement a un historique financier. Pour le conserver, il sera désactivé au lieu d'être supprimé. Continuer ? | 该单元有财务记录。为保留付款历史，将停用而不是删除。是否继续？ | この部屋には会計履歴があります。履歴を残すため、削除ではなく無効にします。続行しますか？ | 이 세대에는 재무 기록이 있습니다. 납부 기록을 보존하기 위해 삭제하지 않고 비활성화합니다. 계속할까요?
واحد حذف شود؟ | Delete this unit? | هل تريد حذف هذه الوحدة؟ | Bu daire silinsin mi? | Diese Einheit löschen? | Supprimer ce logement ? | 要删除此单元吗？ | この部屋を削除しますか？ | 이 세대를 삭제할까요?
غیرفعال | Disabled | معطّل | Devre Dışı | Inaktiv | Désactivé | 停用 | 無効 | 비활성
پشتیبان‌گیری انجام نشد:\n{} | Backup failed:\n{} | فشل النسخ الاحتياطي:\n{} | Yedekleme başarısız:\n{} | Sicherung fehlgeschlagen:\n{} | Échec de la sauvegarde :\n{} | 备份失败：\n{} | バックアップに失敗しました：\n{} | 백업에 실패했습니다:\n{}
فایل پشتیبان سالم نیست. | The backup file is corrupted. | ملف النسخة الاحتياطية تالف. | Yedek dosyası bozuk. | Die Sicherungsdatei ist beschädigt. | Le fichier de sauvegarde est corrompu. | 备份文件已损坏。 | バックアップファイルが破損しています。 | 백업 파일이 손상되었습니다.
بازیابی انجام نشد:\n{} | Restore failed:\n{} | فشلت الاستعادة:\n{} | Geri yükleme başarısız:\n{} | Wiederherstellung fehlgeschlagen:\n{} | Échec de la restauration :\n{} | 恢复失败：\n{} | 復元に失敗しました：\n{} | 복원에 실패했습니다:\n{}
کل پرداختی تعیین‌شده | Total assessed contributions | إجمالي المساهمات المحددة | Belirlenen toplam katkı | Festgelegte Gesamtbeiträge | Total des contributions fixées | 已设定缴款额合计 | 設定済み拠出額合計 | 책정된 분담금 합계
واریزی به {} | Deposits to {} | إيداعات إلى {} | {} hesabına yatırılan | Einzahlungen auf {} | Versements vers {} | 存入 {} | 入金先 {} | 입금: {}
بدهی پرداختی واحدها | Units' contribution debt | ديون مساهمات الوحدات | Dairelerin katkı borcu | Beitragsschulden der Einheiten | Dettes de contributions des logements | 各单元缴款欠款 | 部屋の拠出金未払い | 세대 분담금 미납액
شارژ هر واحد ({}) | Charge per Unit ({}) | الرسوم لكل وحدة ({}) | Daire Başına Aidat ({}) | Gebühr pro Einheit ({}) | Charge par logement ({}) | 每单元物业费（{}） | 部屋ごとの管理費（{}） | 세대당 관리비({})
پرداختی هر واحد ({}) | Contribution per Unit ({}) | المساهمة لكل وحدة ({}) | Daire Başına Katkı ({}) | Beitrag pro Einheit ({}) | Contribution par logement ({}) | 每单元缴款额（{}） | 部屋ごとの拠出額（{}） | 세대당 분담금({})
تعیین مبلغ جداگانه برای واحدها | Set Individual Amounts for Units | تحديد مبالغ منفصلة للوحدات | Daireler İçin Ayrı Tutar Belirle | Einzelbeträge je Einheit festlegen | Définir des montants par logement | 为各单元单独设置金额 | 部屋ごとの金額を設定 | 세대별 금액 개별 설정
{} واحد فعال | {} active units | {} وحدة نشطة | {} aktif daire | {} aktive Einheiten | {} logements actifs | {} 个启用单元 | 有効な部屋 {} 件 | 활성 세대 {}개
یک دسته‌بندی را انتخاب کنید. | Please select a category. | يرجى اختيار فئة. | Lütfen bir kategori seçin. | Bitte wählen Sie eine Kategorie aus. | Veuillez sélectionner une catégorie. | 请选择一个类别。 | カテゴリを選択してください。 | 분류를 선택하세요.
دسته‌بندی «سایر» قابل حذف نیست. | The "Other" category cannot be deleted. | لا يمكن حذف فئة «أخرى». | "Diğer" kategorisi silinemez. | Die Kategorie „Sonstiges“ kann nicht gelöscht werden. | La catégorie « Autres » ne peut pas être supprimée. | “其他”类别不能删除。 | 「その他」カテゴリは削除できません。 | '기타' 분류는 삭제할 수 없습니다.
انصراف | Cancel | إلغاء | İptal | Abbrechen | Annuler | 取消 | キャンセル | 취소
فیلدهای الزامی را کامل کنید. | Please fill in the required fields. | يرجى ملء الحقول المطلوبة. | Lütfen zorunlu alanları doldurun. | Bitte füllen Sie die Pflichtfelder aus. | Veuillez remplir les champs obligatoires. | 请填写必填项。 | 必須項目を入力してください。 | 필수 항목을 입력하세요.
ماه قبل | Previous Month | الشهر السابق | Önceki Ay | Vorheriger Monat | Mois précédent | 上个月 | 前の月 | 이전 달
ماه بعد | Next Month | الشهر التالي | Sonraki Ay | Nächster Monat | Mois suivant | 下个月 | 次の月 | 다음 달
ماه‌های سال | Months of the Year | أشهر السنة | Yılın Ayları | Monate des Jahres | Mois de l'année | 全年月份 | 年間の月 | 연간 월별
کل شارژ | Total charge | إجمالي الرسوم | Toplam aidat | Gesamtgebühr | Total des charges | 物业费合计 | 管理費合計 | 관리비 합계
دریافتی | Received | المقبوض | Alınan | Eingenommen | Encaissé | 已收 | 受取額 | 수납액
هزینه | Expense | المصروف | Gider | Ausgabe | Dépense | 费用 | 経費 | 지출
پرداخت کامل: {0} — ناقص: {1} — پرداخت‌نشده: {2} | Fully paid: {0} — Partial: {1} — Unpaid: {2} | مدفوع بالكامل: {0} — جزئي: {1} — غير مدفوع: {2} | Tamamen ödenen: {0} — Kısmi: {1} — Ödenmemiş: {2} | Vollständig bezahlt: {0} — Teilweise: {1} — Unbezahlt: {2} | Payé intégralement : {0} — Partiel : {1} — Impayé : {2} | 全额付款：{0} — 部分付款：{1} — 未付款：{2} | 全額支払い：{0} — 一部支払い：{1} — 未払い：{2} | 완납: {0} — 부분 납부: {1} — 미납: {2}
اعمال تا پایان سال | Apply to Year End | تطبيق حتى نهاية السنة | Yıl Sonuna Kadar Uygula | Bis Jahresende anwenden | Appliquer jusqu'à fin d'année | 应用到年底 | 年末まで適用 | 연말까지 적용
کل: {0} — دریافتی: {1} — مانده وصول: {2} تومان | Total: {0} — Received: {1} — Outstanding: {2} Toman | الإجمالي: {0} — المقبوض: {1} — المتبقي للتحصيل: {2} تومان | Toplam: {0} — Alınan: {1} — Tahsil edilecek: {2} Toman | Gesamt: {0} — Eingenommen: {1} — Offen: {2} Toman | Total : {0} — Encaissé : {1} — Reste à encaisser : {2} tomans | 合计：{0} — 已收：{1} — 待收：{2} 土曼 | 合計：{0} — 受取：{1} — 未回収：{2} トマン | 합계: {0} — 수납: {1} — 미수: {2} 토만
برای هر واحد مبلغ دلخواه را وارد کنید. اگر خالی بماند، مبلغ پیش‌فرض ({}) اعمال می‌شود. | Enter a custom amount for each unit. If left empty, the default amount ({}) is applied. | أدخل مبلغاً مخصصاً لكل وحدة. إذا ترك فارغاً يُطبَّق المبلغ الافتراضي ({}). | Her daire için özel bir tutar girin. Boş bırakılırsa varsayılan tutar ({}) uygulanır. | Geben Sie für jede Einheit einen eigenen Betrag ein. Bleibt das Feld leer, gilt der Standardbetrag ({}). | Saisissez un montant personnalisé pour chaque logement. Si le champ est vide, le montant par défaut ({}) s'applique. | 请为每个单元输入自定义金额。留空则使用默认金额（{}）。 | 各部屋の金額を入力してください。空欄の場合は標準の金額（{}）が適用されます。 | 세대별 금액을 입력하세요. 비워 두면 기본 금액({})이 적용됩니다.
نمایش واحدهای غیرفعال | Show inactive units | إظهار الوحدات المعطلة | Devre dışı daireleri göster | Inaktive Einheiten anzeigen | Afficher les logements désactivés | 显示已停用单元 | 無効な部屋を表示 | 비활성 세대 표시
دسته‌بندی‌های هزینه‌ها | Expense Categories | فئات المصروفات | Gider Kategorileri | Ausgabenkategorien | Catégories de dépenses | 费用类别 | 経費カテゴリ | 지출 분류
نام دسته‌بندی | Category name | اسم الفئة | Kategori adı | Name der Kategorie | Nom de la catégorie | 类别名称 | カテゴリ名 | 분류 이름
این دسته‌بندی در {} هزینه استفاده شده است.\nابتدا این هزینه‌ها به «سایر» منتقل می‌شوند.\nادامه می‌دهید؟ | This category is used in {} expenses.\nThese expenses will first be moved to “Other”.\nContinue? | تُستخدم هذه الفئة في {} من المصروفات.\nسيتم نقل هذه المصروفات أولاً إلى «أخرى».\nهل تريد المتابعة؟ | Bu kategori {} giderde kullanılıyor.\nBu giderler önce “Diğer” kategorisine taşınacak.\nDevam edilsin mi? | Diese Kategorie wird in {} Ausgaben verwendet.\nDiese Ausgaben werden zuerst zu „Sonstige“ verschoben.\nFortfahren? | Cette catégorie est utilisée dans {} dépenses.\nCes dépenses seront d’abord transférées vers « Autre ».\nContinuer ? | 此类别用于 {} 条费用记录。\n这些费用将先转移到“其他”。\n是否继续？ | このカテゴリは {} 件の経費で使用されています。\nこれらの経費は先に「その他」へ移動されます。\n続行しますか？ | 이 분류는 {}개의 지출 항목에서 사용 중입니다.\n해당 지출은 먼저 “기타”로 이동됩니다.\n계속하시겠습니까?
افزودن | Add | إضافة | Ekle | Hinzufügen | Ajouter | 添加 | 追加 | 추가
ویرایش | Edit | تعديل | Düzenle | Bearbeiten | Modifier | 编辑 | 編集 | 수정
حذف | Delete | حذف | Sil | Löschen | Supprimer | 删除 | 削除 | 삭제
بستن | Close | إغلاق | Kapat | Schließen | Fermer | 关闭 | 閉じる | 닫기
پایگاه داده SQLite | SQLite database | قاعدة بيانات SQLite | SQLite veritabanı | SQLite-Datenbank | Base de données SQLite | SQLite 数据库 | SQLiteデータベース | SQLite 데이터베이스
همه فایل‌ها | All files | كل الملفات | Tüm dosyalar | Alle Dateien | Tous les fichiers | 所有文件 | すべてのファイル | 모든 파일
پاکسازی | Clear | مسح | Temizle | Leeren | Effacer | 清除 | クリア | 지우기
سال مالی | Financial Year | السنة المالية | Mali Yıl | Geschäftsjahr | Exercice | 财务年度 | 会計年度 | 회계 연도
مبلغ هر واحد | Amount per Unit | المبلغ لكل وحدة | Daire Başına Tutar | Betrag pro Einheit | Montant par logement | 每单元金额 | 部屋ごとの金額 | 세대당 금액
این دسته‌بندی قبلاً وجود دارد. | This category already exists. | هذه الفئة موجودة مسبقاً. | Bu kategori zaten var. | Diese Kategorie existiert bereits. | Cette catégorie existe déjà. | 该类别已存在。 | このカテゴリは既に存在します。 | 이미 있는 분류입니다.
این نام قبلاً وجود دارد. | This name already exists. | هذا الاسم موجود مسبقاً. | Bu ad zaten var. | Dieser Name existiert bereits. | Ce nom existe déjà. | 该名称已存在。 | この名前は既に存在します。 | 이미 있는 이름입니다.
جستجو و فیلتر | Search & Filter | بحث وتصفية | Ara ve Filtrele | Suchen & Filtern | Rechercher et filtrer | 搜索与筛选 | 検索とフィルター | 검색 및 필터
مبلغ باید بیشتر از صفر باشد. | The amount must be greater than zero. | يجب أن يكون المبلغ أكبر من صفر. | Tutar sıfırdan büyük olmalıdır. | Der Betrag muss größer als null sein. | Le montant doit être supérieur à zéro. | 金额必须大于零。 | 金額は0より大きくしてください。 | 금액은 0보다 커야 합니다.
تاریخ نامعتبر است. نمونه: {} | Invalid date. Example: {} | تاريخ غير صالح. مثال: {} | Geçersiz tarih. Örnek: {} | Ungültiges Datum. Beispiel: {} | Date invalide. Exemple : {} | 日期无效。示例：{} | 無効な日付です。例：{} | 날짜가 올바르지 않습니다. 예: {}
مرتب‌سازی: | Sort: | الترتيب: | Sıralama: | Sortierung: | Trier : | 排序： | 並べ替え： | 정렬:
ترتیب دستی | Manual order | ترتيب يدوي | Manuel sıralama | Manuelle Reihenfolge | Ordre manuel | 手动排序 | 手動順序 | 수동 정렬
اعمال | Apply | تطبيق | Uygula | Anwenden | Appliquer | 应用 | 適用 | 적용
گزارش ماهانه — خلاصه مالی | Monthly report — Financial summary | التقرير الشهري — الملخص المالي | Aylık rapor — Mali özet | Monatsbericht — Finanzübersicht | Rapport mensuel — Résumé financier | 月度报告 — 财务摘要 | 月次レポート — 財務概要 | 월간 보고서 — 재무 요약
گزارش ماهانه — هزینه‌ها | Monthly report — Expenses | التقرير الشهري — المصروفات | Aylık rapor — Giderler | Monatsbericht — Ausgaben | Rapport mensuel — Dépenses | 月度报告 — 费用 | 月次レポート — 支出 | 월간 보고서 — 지출
گزارش ماهانه — درآمدهای متفرقه | Monthly report — Miscellaneous income | التقرير الشهري — الإيرادات المتنوعة | Aylık rapor — Diğer gelirler | Monatsbericht — Sonstige Einnahmen | Rapport mensuel — Revenus divers | 月度报告 — 其他收入 | 月次レポート — その他の収入 | 월간 보고서 — 기타 수입
گزارش سالانه — درآمدهای متفرقه | Annual report — Miscellaneous income | التقرير السنوي — الإيرادات المتنوعة | Yıllık rapor — Diğer gelirler | Jahresbericht — Sonstige Einnahmen | Rapport annuel — Revenus divers | 年度报告 — 其他收入 | 年次レポート — その他の収入 | 연간 보고서 — 기타 수입
Excel سالانه — درآمدهای متفرقه | Annual Excel — Miscellaneous income | Excel السنوي — الإيرادات المتنوعة | Yıllık Excel — Diğer gelirler | Jahres-Excel — Sonstige Einnahmen | Excel annuel — Revenus divers | 年度 Excel — 其他收入 | 年次 Excel — その他の収入 | 연간 Excel — 기타 수입
گزارش ماهانه — دریافتی‌ها | Monthly report — Receipts | التقرير الشهري — المقبوضات | Aylık rapor — Tahsilatlar | Monatsbericht — Einnahmen | Rapport mensuel — Encaissements | 月度报告 — 收款 | 月次レポート — 受取 | 월간 보고서 — 수입액
گزارش سالانه — خلاصه مالی | Annual report — Financial summary | التقرير السنوي — الملخص المالي | Yıllık rapor — Mali özet | Jahresbericht — Finanzübersicht | Rapport annuel — Résumé financier | 年度报告 — 财务摘要 | 年次レポート — 財務概要 | 연간 보고서 — 재무 요약
گزارش سالانه — روند ماهانه | Annual report — Monthly trend | التقرير السنوي — الاتجاه الشهري | Yıllık rapor — Aylık eğilim | Jahresbericht — Monatsverlauf | Rapport annuel — Tendance mensuelle | 年度报告 — 月度趋势 | 年次レポート — 月別推移 | 연간 보고서 — 월별 추이
گزارش سالانه — هزینه‌ها بر اساس دسته‌بندی | Annual report — Expenses by category | التقرير السنوي — المصروفات حسب الفئة | Yıllık rapor — Kategoriye göre giderler | Jahresbericht — Ausgaben nach Kategorie | Rapport annuel — Dépenses par catégorie | 年度报告 — 按类别统计费用 | 年次レポート — カテゴリ別支出 | 연간 보고서 — 분류별 지출
گزارش سالانه — دریافتی‌ها | Annual report — Receipts | التقرير السنوي — المقبوضات | Yıllık rapor — Tahsilatlar | Jahresbericht — Einnahmen | Rapport annuel — Encaissements | 年度报告 — 收款 | 年次レポート — 受取 | 연간 보고서 — 수입액
گزارش سالانه — هزینه‌ها | Annual report — Expenses | التقرير السنوي — المصروفات | Yıllık rapor — Giderler | Jahresbericht — Ausgaben | Rapport annuel — Dépenses | 年度报告 — 费用 | 年次レポート — 支出 | 연간 보고서 — 지출
گزارش بدهکاران — جدول بدهکاران | Debtors report — Debtors table | تقرير المدينين — جدول المدينين | Borçlular raporu — Borçlular tablosu | Schuldnerbericht — Schuldnertabelle | Rapport des débiteurs — Tableau des débiteurs | 欠款人报告 — 欠款人表格 | 未払い者レポート — 未払い者一覧 | 미납자 보고서 — 미납자 표
Excel سالانه — خلاصه ماهانه | Annual Excel — Monthly summary | Excel السنوي — الملخص الشهري | Yıllık Excel — Aylık özet | Jahres-Excel — Monatsübersicht | Excel annuel — Résumé mensuel | 年度 Excel — 月度摘要 | 年次 Excel — 月次概要 | 연간 Excel — 월별 요약
Excel سالانه — دریافتی‌ها | Annual Excel — Receipts | Excel السنوي — المقبوضات | Yıllık Excel — Tahsilatlar | Jahres-Excel — Einnahmen | Excel annuel — Encaissements | 年度 Excel — 收款 | 年次 Excel — 受取 | 연간 Excel — 수입액
Excel سالانه — هزینه‌ها | Annual Excel — Expenses | Excel السنوي — المصروفات | Yıllık Excel — Giderler | Jahres-Excel — Ausgaben | Excel annuel — Dépenses | 年度 Excel — 费用 | 年次 Excel — 支出 | 연간 Excel — 지출
مبلغ از کم به زیاد | Amount: Low to High | المبلغ: من الأقل إلى الأعلى | Tutar: Artan | Betrag: Aufsteigend | Montant : croissant | 金额：从低到高 | 金額：昇順 | 금액: 낮은순
مبلغ از زیاد به کم | Amount: High to Low | المبلغ: من الأعلى إلى الأقل | Tutar: Azalan | Betrag: Absteigend | Montant : décroissant | 金额：从高到低 | 金額：降順 | 금액: 높은순
تاریخ از قدیم به جدید | Date: Oldest to Newest | التاريخ: من الأقدم إلى الأحدث | Tarih: Eskiden yeniye | Datum: Älteste zuerst | Date : du plus ancien au plus récent | 日期：从早到晚 | 日付：古い順 | 날짜: 오래된순
تاریخ از جدید به قدیم | Date: Newest to Oldest | التاريخ: من الأحدث إلى الأقدم | Tarih: Yeniden eskiye | Datum: Neueste zuerst | Date : du plus récent au plus ancien | 日期：从晚到早 | 日付：新しい順 | 날짜: 최신순
بر اساس واحدها | By unit | حسب الوحدة | Daireye göre | Nach Einheit | Par logement | 按单元 | 部屋別 | 세대별
مانده از کم به زیاد | Remaining: Low to High | المتبقي: من الأقل إلى الأعلى | Kalan: Artan | Restbetrag: Aufsteigend | Solde : croissant | 余额：从低到高 | 残額：昇順 | 잔액: 낮은순
مانده از زیاد به کم | Remaining: High to Low | المتبقي: من الأعلى إلى الأقل | Kalan: Azalan | Restbetrag: Absteigend | Solde : décroissant | 余额：从高到低 | 残額：降順 | 잔액: 높은순
بر اساس دسته‌بندی | By category | حسب الفئة | Kategoriye göre | Nach Kategorie | Par catégorie | 按类别 | カテゴリ別 | 분류별
بر اساس عنوان | By title | حسب العنوان | Başlığa göre | Nach Titel | Par Titel | 按标题 | タイトル別 | 제목별
بر اساس نوع هزینه | By expense type | حسب نوع المصروف | Gider türüne göre | Nach Ausgabenart | Par type de dépense | 按费用类型 | 費用種別 | 지출 유형별
بر اساس نوع پرداخت | By payment type | حسب نوع الدفع | Ödeme türüne göre | Nach Zahlungsart | Par type de paiement | 按付款类型 | 支払種別 | 납부 유형별
موجودی از کم به زیاد | Balance: Low to High | الرصيد: من الأقل إلى الأعلى | Bakiye: Artan | Kontostand: Aufsteigend | Solde : croissant | 余额：从低到高 | 残高：昇順 | 잔액: 낮은순
موجودی از زیاد به کم | Balance: High to Low | الرصيد: من الأعلى إلى الأقل | Bakiye: Azalan | Kontostand: Absteigend | Solde : décroissant | 余额：从高到低 | 残高：降順 | 잔액: 높은순
مجموع از کم به زیاد | Total: Low to High | الإجمالي: من الأقل إلى الأعلى | Toplam: Artan | Summe: Aufsteigend | Total : croissant | 总计：从低到高 | 合計：昇順 | 합계: 낮은순
مجموع از زیاد به کم | Total: High to Low | الإجمالي: من الأعلى إلى الأقل | Toplam: Azalan | Summe: Absteigend | Total : décroissant | 总计：从高到低 | 合計：降順 | 합계: 높은순
بر اساس نام | By name | حسب الاسم | Ada göre | Nach Name | Par nom | 按名称 | 名前順 | 이름순
بر اساس حساب | By account | حسب الحساب | Hesaba göre | Nach Konto | Par compte | 按账户 | 口座別 | 계좌별
درآمدهای متفرقه | Miscellaneous Income | الإيرادات المتنوعة | Diğer Gelirler | Sonstige Einnahmen | Revenus divers | 其他收入 | その他の収入 | 기타 수입
درآمد متفرقه | Miscellaneous income | دخل متنوع | Diğer gelir | Sonstige Einnahme | Revenu divers | 其他收入 | その他の収入 | 기타 수입
ثبت درآمد جدید | Add Income | إضافة دخل جديد | Yeni Gelir Ekle | Neue Einnahme erfassen | Ajouter un revenu | 添加收入 | 収入を追加 | 수입 추가
ویرایش درآمد متفرقه | Edit Miscellaneous Income | تعديل الإيرادات المتنوعة | Diğer Geliri Düzenle | Sonstige Einnahme bearbeiten | Modifier le revenu divers | 编辑其他收入 | その他の収入を編集 | 기타 수입 수정
ثبت درآمد متفرقه | Record Miscellaneous Income | تسجيل دخل متنوع | Diğer Gelir Kaydet | Sonstige Einnahme erfassen | Enregistrer un revenu divers | 记录其他收入 | その他の収入を記録 | 기타 수입 기록
مجموع درآمد متفرقه: {} تومان | Total miscellaneous income: {} Toman | إجمالي الإيرادات المتنوعة: {} تومان | Toplam diğer gelir: {} Toman | Sonstige Einnahmen gesamt: {} Toman | Total des revenus divers : {} tomans | 其他收入总额：{} 土曼 | その他の収入合計：{} トマン | 기타 수입 합계: {} 토만
درآمد انتخاب‌شده حذف شود؟ | Delete the selected income? | هل تريد حذف الدخل المحدد؟ | Seçilen gelir silinsin mi? | Ausgewählte Einnahme löschen? | Supprimer le revenu sélectionné ? | 删除所选收入？ | 選択した収入を削除しますか？ | 선택한 수입을 삭제할까요?
منبع درآمد | Income Source | مصدر الدخل | Gelir Kaynağı | Einnahmequelle | Source du revenu | 收入来源 | 収入源 | 수입 출처
تاریخ دریافت | Date Received | تاريخ الاستلام | Alınma Tarihi | Eingangsdatum | Date de réception | 收款日期 | 受取日 | 수령일
حساب مقصد | Destination Account | الحساب المستلم | Hedef Hesap | Zielkonto | Compte destinataire | 收款账户 | 入金先口座 | 입금 계좌
واریز به حساب | Deposit to Account | إيداع في الحساب | Hesaba Yatır | Auf Konto einzahlen | Verser sur le compte | 存入账户 | 口座に入金 | 계좌에 입금

مدیریت دسته‌بندی‌ها | Manage Categories | إدارة الفئات | Kategorileri Yönet | Kategorien verwalten | Gérer les catégories | 管理类别 | カテゴリを管理 | 분류 관리
دسته‌بندی منبع درآمد | Income Source Categories | فئات مصادر الدخل | Gelir Kaynağı Kategorileri | Einnahmequellen-Kategorien | Catégories de sources de revenus | 收入来源类别 | 収入源カテゴリ | 수입원 분류
منابع درآمد | Income Sources | مصادر الدخل | Gelir Kaynakları | Einnahmequellen | Sources de revenus | 收入来源 | 収入源 | 수입원
افزودن منبع درآمد | Add Income Source | إضافة مصدر دخل | Gelir Kaynağı Ekle | Einnahmequelle hinzufügen | Ajouter une source de revenu | 添加收入来源 | 収入源を追加 | 수입원 추가
ویرایش منبع درآمد | Edit Income Source | تعديل مصدر الدخل | Gelir Kaynağını Düzenle | Einnahmequelle bearbeiten | Modifier la source de revenu | 编辑收入来源 | 収入源を編集 | 수입원 수정
نام منبع درآمد | Income Source Name | اسم مصدر الدخل | Gelir Kaynağı Adı | Name der Einnahmequelle | Nom de la source de revenu | 收入来源名称 | 収入源名 | 수입원 이름
درآمد پیدا نشد. | Income not found. | لم يتم العثور على الدخل. | Gelir bulunamadı. | Einnahme nicht gefunden. | Revenu introuvable. | 未找到收入记录。 | 収入が見つかりません。 | 수입 내역을 찾을 수 없습니다.
وارد کردن اطلاعات قدیمی از فایل‌های JSON انجام نشد؛ هیچ بخشی از واردسازی ناقص ذخیره نشده است.\nجزئیات خطا: {} | Importing legacy data from JSON files failed; no incomplete import was saved.\nError details: {} | فشل استيراد البيانات القديمة من ملفات JSON؛ لم يتم حفظ أي استيراد غير مكتمل.\nتفاصيل الخطأ: {} | Eski JSON verilerinin içe aktarılması başarısız oldu; eksik içe aktarma kaydedilmedi.\nHata ayrıntıları: {} | Der Import alter JSON-Daten ist fehlgeschlagen; es wurden keine unvollständigen Daten gespeichert.\nFehlerdetails: {} | L’importation des anciennes données JSON a échoué ; aucune importation incomplète n’a été enregistrée.\nDétails de l’erreur : {} | 从旧 JSON 文件导入数据失败；未保存任何不完整的导入内容。\n错误详情：{} | 古い JSON ファイルからのデータのインポートに失敗しました。不完全なデータは保存されていません。\nエラーの詳細：{} | 이전 JSON 데이터 가져오기에 실패했습니다. 불완전한 가져오기는 저장되지 않았습니다.\n오류 세부정보: {}
این منبع درآمد در {} درآمد استفاده شده است.\nابتدا این درآمدها به «سایر» منتقل می‌شوند.\nادامه می‌دهید؟ | This income source is used in {} income entries.\nThese entries will first be moved to “Other”.\nContinue? | يُستخدم مصدر الدخل هذا في {} من قيود الدخل.\nسيتم نقل هذه القيود أولاً إلى «أخرى».\nهل تريد المتابعة؟ | Bu gelir kaynağı {} gelir kaydında kullanılıyor.\nBu kayıtlar önce “Diğer” kategorisine taşınacak.\nDevam edilsin mi? | Diese Einnahmequelle wird in {} Einnahmen verwendet.\nDiese Einträge werden zuerst zu „Sonstige“ verschoben.\nFortfahren? | Cette source de revenus est utilisée dans {} écritures.\nCes écritures seront d’abord transférées vers « Autre ».\nContinuer ? | 此收入来源用于 {} 条收入记录。\n这些记录将先转移到“其他”。\n是否继续？ | この収入源は {} 件の収入記録で使用されています。\nこれらの記録は先に「その他」へ移動されます。\n続行しますか？ | 이 수입 출처는 {}개의 수입 항목에서 사용 중입니다.\n해당 항목은 먼저 “기타”로 이동됩니다.\n계속하시겠습니까?
راهنما | Help | مساعدة | Yardım | Hilfe | Aide | 帮助 | ヘルプ | 도움말
گزارش خطاها | Error Logs | سجلات الأخطاء | Hata kayıtları | Fehlerprotokolle | Journaux d’erreurs | 错误日志 | エラーログ | 오류 로그
برای این حساب بدهیِ تسویه‌نشده‌ای وجود ندارد. | There is no outstanding debt for this account. | لا توجد ديون مستحقة غير مسددة لهذا الحساب. | Bu hesap için ödenmemiş borç bulunmuyor. | Für dieses Konto bestehen keine offenen Schulden. | Aucun impayé n’est dû pour ce compte. | 此账户没有未结清的欠款。 | この口座に未精算の未払い金はありません。 | 이 계정에는 미결제 부채가 없습니다.
سال یا ماه معتبر نیست. | Invalid year or month. | السنة أو الشهر غير صالح. | Yıl veya ay geçersiz. | Jahr oder Monat ist ungültig. | Année ou mois invalide. | 年份或月份无效。 | 年または月が無効です。 | 연도 또는 월이 올바르지 않습니다.
تنظیمات پیشرفته ساختمان | Advanced Building Settings | إعدادات المبنى المتقدمة | Gelişmiş Bina Ayarları | Erweiterte Gebäudeeinstellungen | Paramètres avancés du bâtiment | 高级楼宇设置 | 建物の詳細設定 | 고급 건물 설정
درآمد متفرقه از {} | Miscellaneous income from {} | إيرادات متنوعة من {} | {} kaynaklı diğer gelir | Sonstige Einnahmen von {} | Revenus divers de {} | 来自 {} 的其他收入 | {} からのその他の収入 | {}에서 발생한 기타 수입
عادی (Normal) | Normal | عادي | Normal | Normal | Normal | 普通 | 標準 | 보통
بزرگ (Large) | Large | كبير | Büyük | Groß | Grand | 大 | 大 | 크게
روشن | Light | فاتح | Açık | Hell | Clair | 浅色 | ライト | 밝게
تیره | Dark | داكن | Koyu | Dunkel | Sombre | 深色 | ダーク | 어둡게
از ابتدای همان ماه؛ دیگر شارژ نگیرد | From the beginning of that month; no further charge | من بداية الشهر نفسه؛ لا تُفرض رسوم بعد ذلك | Aynı ayın başından itibaren; artık aidat alınmasın | Ab Monatsbeginn; keine weiteren Gebühren | Dès le début du mois ; ne plus facturer | 从该月初开始，不再收取费用 | その月の初めから請求しない | 해당 월 초부터 더 이상 부과하지 않음
تا پایان همین ماه شارژ شود؛ از ماه بعد متوقف شود | Charge through this month; stop from next month | تُفرض الرسوم حتى نهاية هذا الشهر؛ وتتوقف من الشهر التالي | Bu ayın sonuna kadar aidat alınsın; gelecek aydan itibaren durdurulsun | Bis Monatsende berechnen; ab dem Folgemonat stoppen | Facturer jusqu’à la fin du mois, puis arrêter le mois suivant | 收取至本月底；从下个月起停止 | 今月末まで請求し、翌月から停止 | 이번 달 말까지 부과하고 다음 달부터 중단
مبلغ نمی‌تواند منفی باشد. | Amount cannot be negative. | لا يمكن أن يكون المبلغ سالبًا. | Tutar negatif olamaz. | Der Betrag darf nicht negativ sein. | Le montant ne peut pas être négatif. | 金额不能为负数。 | 金額を負にすることはできません。 | 금액은 음수일 수 없습니다.
ترتیب پیش‌فرض جدول‌ها در هر نوع خروجی را جداگانه انتخاب کنید. | Choose the default table order separately for each export type. | اختر ترتيب الجدول الافتراضي بشكل منفصل لكل نوع تصدير. | Her dışa aktarma türü için varsayılan tablo sırasını ayrı seçin. | Wählen Sie die Standardtabellenreihenfolge für jeden Exporttyp separat. | Choisissez séparément l’ordre par défaut des tableaux pour chaque type d’exportation. | 为每种导出类型分别选择默认表格顺序。 | 出力形式ごとに既定の表順を選択してください。 | 내보내기 유형별 기본 표 순서를 각각 선택하세요.
ذخیره کلیه تغییرات تنظیمات | Save All Settings | حفظ جميع الإعدادات | Tüm ayarları kaydet | Alle Einstellungen speichern | Enregistrer tous les paramètres | 保存所有设置 | すべての設定を保存 | 모든 설정 저장
ترتیب پیش‌فرض برنامه | Application Default Order | الترتيب الافتراضي للتطبيق | Uygulama Varsayılan Sırası | Standardreihenfolge der Anwendung | Ordre par défaut de l’application | 程序默认顺序 | アプリの既定順序 | 앱 기본 순서
گزارش چندماهه — خلاصه مالی | Multi-month report — Financial summary | تقرير عدة أشهر — الملخص المالي | Çok aylı rapor — Mali özet | Mehrmonatsbericht — Finanzübersicht | Rapport multi-mois — Résumé financier | 多月报告 — 财务摘要 | 複数月レポート — 財務概要 | 여러 달 보고서 — 재무 요약
گزارش چندماهه — روند ماهانه | Multi-month report — Monthly trend | تقرير عدة أشهر — الاتجاه الشهري | Çok aylı rapor — Aylık eğilim | Mehrmonatsbericht — Monatsverlauf | Rapport multi-mois — Tendance mensuelle | 多月报告 — 月度趋势 | 複数月レポート — 月別推移 | 여러 달 보고서 — 월별 추이
گزارش چندماهه — هزینه‌ها بر اساس دسته‌بندی | Multi-month report — Expenses by category | تقرير عدة أشهر — المصروفات حسب الفئة | Çok aylı rapor — Kategoriye göre giderler | Mehrmonatsbericht — Ausgaben nach Kategorie | Rapport multi-mois — Dépenses par catégorie | 多月报告 — 按类别统计费用 | 複数月レポート — カテゴリ別支出 | 여러 달 보고서 — 분류별 지출
گزارش چندماهه — دریافتی‌ها | Multi-month report — Receipts | تقرير عدة أشهر — المقبوضات | Çok aylı rapor — Tahsilatlar | Mehrmonatsbericht — Einnahmen | Rapport multi-mois — Encaissements | 多月报告 — 收款 | 複数月レポート — 受取 | 여러 달 보고서 — 수입액
گزارش چندماهه — هزینه‌ها | Multi-month report — Expenses | تقرير عدة أشهر — المصروفات | Çok aylı rapor — Giderler | Mehrmonatsbericht — Ausgaben | Rapport multi-mois — Dépenses | 多月报告 — 费用 | 複数月レポート — 支出 | 여러 달 보고서 — 지출
گزارش چندماهه — درآمدهای متفرقه | Multi-month report — Miscellaneous income | تقرير عدة أشهر — الإيرادات المتنوعة | Çok aylı rapor — Diğer gelirler | Mehrmonatsbericht — Sonstige Einnahmen | Rapport multi-mois — Revenus divers | 多月报告 — 其他收入 | 複数月レポート — その他の収入 | 여러 달 보고서 — 기타 수입
PDF ماهانه | Monthly PDF | PDF شهري | Aylık PDF | Monats-PDF | PDF mensuel | 月度 PDF | 月次 PDF | 월간 PDF
PDF سالانه | Annual PDF | PDF سنوي | Yıllık PDF | Jahres-PDF | PDF annuel | 年度 PDF | 年次 PDF | 연간 PDF
PDF بدهکاران | Debtors PDF | PDF المدينين | Borçlular PDF | Schuldner-PDF | PDF des débiteurs | 欠款人 PDF | 未払い者 PDF | 미납자 PDF
Excel سالانه | Annual Excel | Excel سنوي | Yıllık Excel | Jahres-Excel | Excel annuel | 年度 Excel | 年次 Excel | 연간 Excel
گزارش مالی چندماهه PDF | Multi-month Financial Report (PDF) | تقرير مالي لعدة أشهر PDF | Çok Aylı Mali Rapor (PDF) | Mehrmonatiger Finanzbericht (PDF) | Rapport financier sur plusieurs mois (PDF) | 多月财务报告（PDF） | 複数月財務レポート（PDF） | 여러 달 재무 보고서(PDF)
انتخاب ماه‌های گزارش | Select report months | اختر أشهر التقرير | Rapor aylarını seçin | Berichtsmonate auswählen | Sélectionner les mois du rapport | 选择报告月份 | レポート対象月を選択 | 보고서 월 선택
حداقل یک ماه را انتخاب کنید. | Select at least one month. | اختر شهراً واحداً على الأقل. | En az bir ay seçin. | Wählen Sie mindestens einen Monat aus. | Sélectionnez au moins un mois. | 请至少选择一个月份。 | 少なくとも1か月を選択してください。 | 최소 한 달을 선택하세요.
انتخاب همه | Select all | تحديد الكل | Tümünü seç | Alle auswählen | Tout sélectionner | 全选 | すべて選択 | 모두 선택
لغو انتخاب همه | Clear all | إلغاء تحديد الكل | Seçimi temizle | Auswahl aufheben | Tout désélectionner | 全部取消 | すべて解除 | 모두 선택 해제
سال گزارش | Report year | سنة التقرير | Rapor yılı | Berichtsjahr | Année du rapport | 报告年份 | レポート年 | 보고 연도
گزارش مالی ماه‌های انتخاب‌شده سال {} | Financial report for selected months of {} | التقرير المالي للأشهر المحددة من {} | {} yılının seçilen ayları için mali rapor | Finanzbericht für die ausgewählten Monate {} | Rapport financier pour les mois sélectionnés de {} | {}年所选月份的财务报告 | {}年の選択月の財務レポート | {}년 선택한 달의 재무 보고서
سایر | Other | أخرى | Diğer | Sonstige | Autre | 其他 | その他 | 기타
وارد کردن اطلاعات قدیمی از فایل‌های JSON انجام نشد؛ جزئیات خطا: {} | Failed to import legacy JSON data; details: {} | فشل استيراد بيانات JSON القديمة؛ التفاصيل: {} | Eski JSON verileri içe aktarılamadı; ayrıntılar: {} | Alte JSON-Daten konnten nicht importiert werden; Details: {} | Échec de l’importation des anciennes données JSON ; détails : {} | 导入旧 JSON 数据失败；详情：{} | 旧 JSON データのインポートに失敗しました。詳細：{} | 이전 JSON 데이터를 가져오지 못했습니다. 세부 정보: {}
مبلغ باید عدد صحیح باشد؛ اعشار مجاز نیست. | Amount must be a whole number; decimals are not allowed. | يجب أن يكون المبلغ عددًا صحيحًا؛ الكسور العشرية غير مسموح بها. | Tutar tam sayı olmalıdır; ondalık değerlere izin verilmez. | Der Betrag muss eine ganze Zahl sein; Dezimalstellen sind nicht zulässig. | Le montant doit être un nombre entier ; les décimales ne sont pas autorisées. | 金额必须为整数；不允许小数。 | 金額は整数である必要があります。小数は使用できません。 | 금액은 정수여야 하며 소수는 허용되지 않습니다.
"""



class I18n:
    def __init__(self):
        self.lang = "fa"
        self._tables = {}

    def set_language(self, lang):
        # توجه: هماهنگی فونت UI مسئولیت App است (متد App._apply_ui_font)؛ I18n فقط زبان را نگه می‌دارد.
        # آزمون دستی: تغییر زبان باید فقط self.lang را عوض کند و App ظاهر را جداگانه هماهنگ کند.
        self.lang = lang if lang == "fa" or lang in _LANG_ORDER else "fa"

    @property
    def rtl(self):
        return self.lang in RTL_LANGS

    def _build_table(self):
        """جدول ترجمه‌ی زبان غیرفارسی را می‌سازد؛ کش در _table مدیریت می‌شود."""
        column = _LANG_ORDER.index(self.lang) + 1
        table = {}
        for number, line in enumerate(_RAW.strip().splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip().replace("\\n", "\n") for p in line.split(" | ")]
            if len(parts) != 9:
                AppLogger.warning(
                    f"I18n row {number} ignored: expected 9 columns, got {len(parts)}"
                )
                continue
            normalized_key = _norm_key(parts[0])
            if normalized_key in table:
                AppLogger.warning(
                    f"I18n row {number} ignored: duplicate key {parts[0]!r}"
                )
                continue
            table[normalized_key] = parts[column]
        return table

    def _table(self):
        # حتی جدول خالی فارسی هم یک بار ساخته و در کش نگهداری می‌شود.
        # آزمون دستی: دو بار _table() را برای fa و en فراخوانی کنید؛ شیء جدول هر زبان باید یکسان بماند.
        if self.lang not in self._tables:
            self._tables[self.lang] = {} if self.lang == "fa" else self._build_table()
        return self._tables[self.lang]

    def t(self, key, *args):
        # برای فارسی و سایر زبان‌ها فقط از جدول ترجمه استفاده می‌شود.
        text = self._table().get(_norm_key(key), key)
        if args:
            try:
                text = text.format(*args)
            except Exception as exc:
                AppLogger.warning(f"I18n format fallback for {key!r}: {exc}")
                # در خطای قالب‌بندی نیز همان مقدار جدول ترجمه یا کلید اصلی برگردانده می‌شود.
                text = self._table().get(_norm_key(key), key)
                try:
                    text = text.format(*args)
                except Exception as fallback_exc:
                    AppLogger.warning(f"I18n Persian fallback format failed: {fallback_exc}")
                    # مسیر جایگزین نهایی نیز بدون جایگزینی واژه‌ای عمل می‌کند.
                    text = self._table().get(_norm_key(key), key)
                    text = text.replace("{", "").replace("}", "")
        return text


i18n = I18n()
T = i18n.t


def _validate_raw_i18n():
    """تمام ردیف‌های ترجمه را در شروع برنامه بررسی می‌کند و فقط هشدار می‌دهد.

    آزمون دستی: یک ردیف ۸ستونی یا یک کلید تکراری به _RAW اضافه کنید؛ هشدار باید ثبت شود.
    """
    seen = set()
    for number, line in enumerate(_RAW.strip().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(" | ")]
        if len(parts) != 9:
            AppLogger.warning(
                f"I18n row {number} invalid: expected 9 columns, got {len(parts)}"
            )
            continue
        key = _norm_key(parts[0])
        if not key:
            AppLogger.warning(f"I18n row {number} invalid: empty key")
        elif any(not part for part in parts[1:]):
            AppLogger.warning(f"I18n row {number} invalid: empty translation column")
        elif key in seen:
            AppLogger.warning(f"I18n row {number} invalid: duplicate key {parts[0]!r}")
        else:
            seen.add(key)


def month_name(month):
    return T(MONTHS[month - 1])


# ----------------------------------------------------------------------
#  لایه‌ی داده (SQLite)
# ----------------------------------------------------------------------
# دو حساب مستقل‌اند؛ هرکدام مبلغ و ریزمبالغ واحدی خود را دارند،
# اما الگوریتم محاسبه و انتقال بدهی/بستانکاری برای هر دو یکسان است.
ASSESS = {KIND_CHARGE: ("charge_per_unit", "unit_charges"),
          KIND_CONTRIB: ("payment_per_unit", "unit_payments")}
ZERO_FLOW = (0, 0, 0, 0, 0, 0)   # شارژ، پرداختی، هزینه‌های دو حساب، درآمدهای دو حساب


# نبودن default با None تفاوت دارد؛ None صریح باید به‌عنوان مقدار پیش‌فرض حفظ شود.
_UNSET = object()


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



def run_self_tests():
    """آزمون‌های داخلی؛ فقط با --test اجرا می‌شود و نتیجه را در messagebox نشان می‌دهد."""
    failures = []
    checks = [
        ("تبدیل تاریخ ۲۰۲۴/۰۳/۲۰", lambda: gregorian_to_jalali(2024, 3, 20) == (1403, 1, 1)),
        ("تبدیل تاریخ ۲۰۲۴/۰۳/۲۱", lambda: gregorian_to_jalali(2024, 3, 21) == (1403, 1, 2)),
        ("تاریخ شمسی با ممیز", lambda: parse_shamsi("1405/02/15") == (1405, 2, 15)),
        ("تاریخ فارسی با خط تیره", lambda: parse_shamsi("۱۴۰۵-۲-۱۵") == (1405, 2, 15)),
        ("رد ماه نامعتبر", lambda: parse_shamsi("1405/13/01") is None),
        ("اسفند کبیسه", lambda: days_in_month(1403, 12) == 30),
        ("اسفند غیرکبیسه", lambda: days_in_month(1404, 12) == 29),
        ("تبدیل رقم فارسی", lambda: normalize_digits("۱۲۳۴") == "1234"),
        ("تبدیل مبلغ", lambda: parse_money("۱,۲۳۴,۵۶۷") == 1234567),
    ]
    for label, test in checks:
        try:
            if not test():
                failures.append(f"{label}: نتیجه نادرست")
        except Exception as exc:
            failures.append(f"{label}: {type(exc).__name__}: {exc}")

    temp_path = None
    db = None
    try:
        fd, temp_path = tempfile.mkstemp(prefix="building_manager_test_", suffix=".sqlite3")
        os.close(fd)
        original_json_dirs = JSON_DIRS[:]
        JSON_DIRS.clear()
        try:
            db = Database(temp_path)
        finally:
            JSON_DIRS[:] = original_json_dirs
        new_id = db.save_unit(None, {
            "number": "TEST-1", "floor": "1", "status": ST_OWNER,
            "owner": "آزمون", "owner_phone": "", "tenant": "",
            "tenant_phone": "", "notes": "", "active": True
        }, 1405, 2)
        loaded = db.unit(new_id)
        if not loaded or loaded["number"] != "TEST-1":
            failures.append("ذخیره و خواندن واحد: داده بازیابی نشد")
    except Exception as exc:
        failures.append(f"ذخیره و خواندن دیتابیس موقت: {type(exc).__name__}: {exc}")
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
        if temp_path:
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.remove(temp_path + suffix)
                except OSError:
                    pass

    try:
        root = tk.Tk()
        root.withdraw()
        if failures:
            messagebox.showerror("نتیجه آزمون‌ها", "برخی آزمون‌ها ناموفق بودند:\n\n" + "\n".join(failures), parent=root)
        else:
            messagebox.showinfo("نتیجه آزمون‌ها", "✅ همه‌ی تست‌ها موفق بودند", parent=root)
        root.destroy()
    except Exception as exc:
        AppLogger.exception(f"Could not display self-test result: {exc}")


def _mark_startup_complete():
    global _STARTUP_COMPLETE
    _STARTUP_COMPLETE = True


def main():
    global _STARTUP_COMPLETE
    prepare_storage()
    # اعتبارسنجی تاریخ و ترجمه پیش از ساخت UI، خطاهای پایه را از همان شروع آشکار می‌کند.
    # آزمون دستی: اجرا کنید؛ نباید پیام _self_test_jalali failed در app.log ثبت شود.
    _self_test_jalali()
    _self_test_parse_money()
    _self_test_migrate_income_backfill()
    _validate_raw_i18n()
    if "--test" in sys.argv[1:]:
        run_self_tests()
        return
    app = App()
    # FIX(4): enable the global Tk error dialog as soon as the root window exists.
    _STARTUP_COMPLETE = True
    # نمایش خطای واردسازی در main از ازدواج هشدار تکراری با callback شروع جلوگیری می‌کند.
    # آزمون دستی: واردسازی JSON خراب را شبیه‌سازی کنید؛ فقط در صورت وجود import_error هشدار ببینید.
    if app.db.import_error:
        detail = app.db.import_error
        messagebox.showwarning(
            T("هشدار"),
            translate_error("json-import-failed").format(detail),
            parent=app,
        )
        app.db.import_error = None
    # بعد از ساخته‌شدن پنجره، خطاهای رخ‌داده در callbackها باید به messagebox هدایت شوند.
    # آزمون دستی: یک خطای کنترل‌شده پس از شروع UI ایجاد کنید؛ باید پنجره‌ی خطا نمایش داده شود.
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # خطاهای مرحله‌ی راه‌اندازی علاوه بر فایل گزارش، در کنسول هم نمایش داده می‌شوند.
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
        try:
            sys.stderr.flush()
        except Exception:
            pass
        AppLogger.exception(f"Application startup failed: {exc}")
        try:
            messagebox.showerror(
                "خطای اجرای برنامه",
                "برنامه اجرا نشد. جزئیات خطا در کنسول و فایل گزارش ذخیره شده است."
            )
        except Exception:
            pass


# ======================================================================
# تست‌های دستی پیشنهادی
# ۱) برنامه را با دیتابیس خالی اجرا کنید؛ باید بدون خطای migration باز شود.
# ۲) دو واحد با شماره‌های ۱ و ۳ و یک واحد بدون شماره بسازید؛ واحد سوم باید شماره ۲ بگیرد.
# ۳) چند واحد بدون شماره اضافه کنید و برنامه را دوباره اجرا کنید؛ شماره‌های قبلی نباید تغییر کنند.
# ۴) برای سال‌های ۱۳۹۹، ۱۴۰۳ و ۱۴۰۸ اسفند ۳۰روزه و برای ۱۴۰۴ و ۱۴۰۷ اسفند ۲۹روزه بررسی شود.
# ۵) در مبلغ، 1.5 و ۱٫۵ وارد کنید؛ پیام «مبلغ باید عدد صحیح باشد» نمایش داده شود.
# ۶) یک منبع درآمد دارای NBSP و ZWNJ ثبت کنید؛ گزینه‌ی منبع باید تمیز و یکتا شود.
# ۷) زبان را بین فارسی و انگلیسی تغییر دهید؛ فونت رابط باید مطابق انتخاب خودکار قبلی سیستم باشد.
# ۸) در زبان فارسی یک PDF و یک Excel بسازید و نمایش متن‌ها را بررسی کنید.
# ۹) یک JSON قدیمی خراب را برای واردسازی قرار دهید؛ هشدار همراه جزئیات خطا باید نمایش داده شود.
# ======================================================================
