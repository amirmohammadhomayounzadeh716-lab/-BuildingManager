"""Windows/Python entry point for BuildingManager."""
from building_manager.entrypoint import *

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
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
