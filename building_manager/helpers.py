from .runtime import *

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


def _raise_self_test_failures(name, failures):
    """Make smoke-test failures visible to CI and callers instead of logging and continuing."""
    if failures:
        details = "; ".join(failures)
        AppLogger.warning(f"{name} failed: {details}")
        raise AssertionError(f"{name} failed: {details}")


def _self_test_jalali():
    """Run calendar boundary checks and fail loudly if any assertion is false."""
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
        ("JDN 1403/12/29 to 1404/01/01 must differ by 2", lambda: _jalali_to_jdn(1404, 1, 1) - _jalali_to_jdn(1403, 12, 29) == 2),
        ("JDN 1403/12/30 to 1404/01/01 must differ by 1", lambda: _jalali_to_jdn(1404, 1, 1) - _jalali_to_jdn(1403, 12, 30) == 1),
        ("days_in_month(1403, 12) must be 30", lambda: days_in_month(1403, 12) == 30),
        ("days_in_month(1404, 12) must be 29", lambda: days_in_month(1404, 12) == 29),
        ("parse_shamsi 1405/01/01", lambda: parse_shamsi("1405/01/01") == (1405, 1, 1)),
        ("parse_shamsi Persian digits in 1405", lambda: parse_shamsi("۱۴۰۵/۱۲/۲۹") == (1405, 12, 29)),
        ("1405 Esfand has 29 days", lambda: days_in_month(1405, 12) == 29),
        ("1405/12/30 is invalid", lambda: parse_shamsi("1405/12/30") is None),
    )
    failures = []
    for label, check in tests:
        try:
            if not check():
                failures.append(label)
        except Exception as exc:
            failures.append(f"{label}: {type(exc).__name__}: {exc}")
    _raise_self_test_failures("_self_test_jalali", failures)


def _self_test_parse_money():
    """Verify accepted whole-toman formats and expected validation errors."""
    checks = (
        ("1,5", "money-decimal-not-allowed"),
        ("1,234", 1234),
        ("1,234,567", 1234567),
        ("1,2345", "money-decimal-not-allowed"),
        ("۱۲٬۳۴۵", 12345),
        ("1٫5", "money-decimal-not-allowed"),
        ("12 345", 12345),
        ("1234", 1234),
        ("50000", 50000),
        ("1 2", "money-decimal-not-allowed"),
        ("", 0),
        ("abc", "ValueError"),
    )
    failures = []
    for raw, expected in checks:
        try:
            actual = parse_money(raw)
        except Exception as exc:
            valid_error = (
                str(exc) == expected if expected == "money-decimal-not-allowed"
                else isinstance(exc, ValueError) if expected == "ValueError"
                else False
            )
            if not valid_error:
                failures.append(f"{raw!r}: unexpected {type(exc).__name__}: {exc}")
        else:
            if isinstance(expected, str):
                failures.append(f"{raw!r}: expected {expected} error, got {actual!r}")
            elif actual != expected:
                failures.append(f"{raw!r}: got {actual!r}, expected {expected!r}")
    _raise_self_test_failures("_self_test_parse_money", failures)


def _self_test_migrate_income_backfill():
    """Verify legacy income migration and fail if the backfilled period is wrong."""
    connection = None
    failures = []
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
            failures.append("expected income period (1405, 2)")
    except Exception as exc:
        failures.append(f"{type(exc).__name__}: {exc}")
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
    _raise_self_test_failures("_self_test_migrate_income_backfill", failures)


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



__all__ = [name for name in globals() if not name.startswith('__')]
