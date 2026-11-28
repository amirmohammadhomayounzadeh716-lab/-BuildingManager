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
APP_VERSION = "18.7"
MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
          "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
SEASONS = [("بهار", 0), ("تابستان", 3), ("پاییز", 6), ("زمستان", 9)]
DEFAULT_CATEGORIES = ["آب", "برق", "گاز", "آسانسور", "نظافت", "تعمیرات",
                      "نگهبانی", "شارژ/قبوض", "بیمه", "سایر"]

# مقادیری که داخل دیتابیس ذخیره می‌شوند (همیشه فارسی؛ هرگز ترجمه نمی‌شوند)
KIND_CHARGE = "شارژ"
KIND_CONTRIB = "پرداختی"
LEGACY_ST_VACANT, ST_OWNER, ST_TENANT = "خالی", "مالک", "مستأجر"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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



__all__ = [name for name in globals() if not name.startswith('__')]
