from .app import *

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


__all__ = [name for name in globals() if not name.startswith('__')]
