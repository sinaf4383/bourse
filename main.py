"""ورودی اصلی. مثال‌ها:
    python main.py init
    python main.py fetch --symbols فولاد شبندر وبملت
    python main.py fetch --limit 50
    python main.py fetch --all
    python main.py import-csv مسیر/پوشه
    python main.py status
"""
import argparse
import db
import data_source as ds


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    f = sub.add_parser("fetch")
    f.add_argument("--symbols", nargs="+")
    f.add_argument("--limit", type=int, help="فقط N نماد اول (برای تست)")
    f.add_argument("--all", action="store_true")
    f.add_argument("--force", action="store_true")
    c = sub.add_parser("import-csv")
    c.add_argument("folder")
    sub.add_parser("status")
    a = p.parse_args()

    db.init_db()
    if a.cmd == "init":
        print("دیتابیس آماده شد.")
    elif a.cmd == "fetch":
        if a.symbols:
            syms = a.symbols
        elif a.all or a.limit:
            syms = ds.list_symbols()
            if a.limit:
                syms = syms[: a.limit]
        else:
            p.error("یکی از --symbols / --limit / --all رو بده")
        ok, fail = ds.fetch_many(syms, force=a.force)
        print(f"تموم شد: {ok} موفق، {fail} خطا")
    elif a.cmd == "import-csv":
        print(f"{ds.import_csv_folder(a.folder)} ردیف وارد شد.")
    elif a.cmd == "status":
        n, rows, d0, d1 = db.summary()
        print(f"نمادها: {n} | ردیف‌ها: {rows} | بازه: {d0} تا {d1}")


if __name__ == "__main__":
    main()
