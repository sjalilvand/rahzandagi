#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
سایت‌کاو — نمایشگر وب داده‌ها (نسخه ۳.۴)
=========================================
برنامه‌ای فلسکی و زیبا برای خواندن و نمایش کامل داده‌های ذخیره‌شده توسط خزنده:

  • داشبورد گرافیکی (آمار، نمودار، آخرین صفحه‌ها)
  • صفحه‌های خزیده‌شده + متن‌ها + لینک‌ها + تصویر صفحه
  • جدول‌های HTML استخراج‌شده با نمای جدولی
  • مجموعه‌داده‌ها (ds_*) با جست‌وجو، صفحه‌بندی و خروجی اکسل/CSV
  • گالری تصاویر (اسکرین‌شات‌ها و فایل‌های سایت)
  • مرورگر فایل‌های HTML ذخیره‌شده (نمایش واقعی داخل برنامه)
  • جست‌وجوی سراسری، لاگ خزش و پاسخ‌های API
  • ساخت دوباره‌ی خروجی اکسل کامل (وقتی export.xlsx خالی مانده)

اجرا:            python viewer.py           →  http://127.0.0.1:5002
گزینه‌ها:        --db مسیر دیتابیس   --out پوشه خروجی   --port 5002   --host 127.0.0.1
                                              --no-browser  (باز کردن خودکار مرورگر را خاموش می‌کند)
"""

import argparse
import io
import json
import os
import re
import sqlite3
import sys
import threading
import time
import webbrowser
from datetime import datetime

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_file, send_from_directory, url_for)

APP_NAME = "سایت‌کاو | نمایشگر داده‌ها"
VERSION = "۳.۴"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(APP_DIR, "viewer_settings.json")

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp", ".ico"}
PAGE_SIZE = 100
GALLERY_PAGE = 60

app = Flask(__name__)
app.secret_key = "saitkav-viewer-" + str(os.getpid())
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
app.config["JSON_AS_ASCII"] = False

# ------------------------------------------------------------------ مسیرها
DB_PATH = None
OUT_DIR = None


def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(s):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def find_db(cli_db=None):
    """پیدا کردن خودکار site_data.db — ترتیب: آرگومان ← تنظیمات ← مسیرهای پیش‌فرض"""
    cands = []
    if cli_db:
        cands.append(cli_db)
    st = load_settings()
    if st.get("db_path"):
        cands.append(st["db_path"])
    cands += [
        os.path.join(APP_DIR, "site_data.db"),
        os.path.join(APP_DIR, "خروجی", "site_data.db"),
        os.path.join(APP_DIR, "output", "site_data.db"),
        os.path.join(os.path.expanduser("~"), "Desktop", "خروجی", "site_data.db"),
    ]
    for c in cands:
        try:
            if c and os.path.isfile(c):
                return os.path.abspath(c)
        except Exception:
            continue
    return None


def db_size_str(path):
    try:
        n = os.path.getsize(path)
        for unit in ("بایت", "کیلوبایت", "مگابایت", "گیگابایت"):
            if n < 1024 or unit == "گیگابایت":
                return f"{n:,.0f} {unit}" if unit == "بایت" else f"{n:,.1f} {unit}"
            n /= 1024
    except Exception:
        return "—"
    return "—"


# ------------------------------------------------------------------ دیتابیس
def get_db():
    if not DB_PATH:
        abort(503)
    if "db" not in g:
        try:
            g.db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=4)
            g.db.row_factory = sqlite3.Row
        except Exception:
            abort(503)
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass


def q1(sql, args=()):
    try:
        return get_db().execute(sql, args).fetchone()
    except Exception:
        return None


def qall(sql, args=()):
    try:
        return get_db().execute(sql, args).fetchall()
    except Exception:
        return []


def safe_table(name):
    """نام جدول ds_* فقط از فهرست datasets پذیرفته می‌شود (ضد تزریق)"""
    if not re.fullmatch(r"[\w\u0600-\u06FF]+", name or ""):
        return None
    row = q1("SELECT sqlite_table FROM datasets WHERE sqlite_table=?", (name,))
    return row["sqlite_table"] if row else None


def norm_rel(rel):
    r"""مسیر نسبی ذخیره‌شده در db (با بک‌اسلش ویندوز) → مسیر امن برای serving"""
    if not rel:
        return None
    rel = rel.replace("\\", "/").lstrip("/")
    full = os.path.normpath(os.path.join(OUT_DIR or "", rel))
    try:
        if os.path.isfile(full) and os.path.abspath(full).startswith(os.path.abspath(OUT_DIR or "")):
            return rel
    except Exception:
        pass
    return None


def table_count(name):
    try:
        return get_db().execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    except Exception:
        return 0


# ------------------------------------------------------------------ گالری
_gallery_cache = {"key": None, "items": []}


def gallery_items():
    key = (OUT_DIR, int(os.path.getmtime(OUT_DIR)) if os.path.isdir(OUT_DIR) else 0)
    if _gallery_cache["key"] == key:
        return _gallery_cache["items"]
    items = []
    if OUT_DIR and os.path.isdir(OUT_DIR):
        for sub in sorted(os.listdir(OUT_DIR)):
            d = os.path.join(OUT_DIR, sub)
            if not os.path.isdir(d):
                continue
            for root, _dirs, files in os.walk(d):
                for fn in files:
                    ext = os.path.splitext(fn)[1].lower()
                    if ext not in IMG_EXT:
                        continue
                    full = os.path.join(root, fn)
                    try:
                        stt = os.stat(full)
                    except Exception:
                        continue
                    rel = os.path.relpath(full, OUT_DIR).replace("\\", "/")
                    items.append({"rel": rel, "name": fn, "folder": sub,
                                  "size": stt.st_size, "mtime": stt.st_mtime})
    items.sort(key=lambda x: -x["mtime"])
    _gallery_cache["key"] = key
    _gallery_cache["items"] = items
    return items


def list_html_files():
    out = []
    if OUT_DIR and os.path.isdir(OUT_DIR):
        for sub in ("html", "pages"):
            d = os.path.join(OUT_DIR, sub)
            if os.path.isdir(d):
                for fn in sorted(os.listdir(d)):
                    if fn.lower().endswith(".html"):
                        full = os.path.join(d, fn)
                        try:
                            stt = os.stat(full)
                        except Exception:
                            continue
                        out.append({"rel": f"{sub}/{fn}", "name": fn, "folder": sub,
                                    "size": stt.st_size, "mtime": stt.st_mtime})
    out.sort(key=lambda x: -x["mtime"])
    return out


# ------------------------------------------------------------------ کمکی‌های نمایش
def human_size(n):
    for unit in ("بایت", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "بایت" else f"{n:,.1f} {unit}"
        n /= 1024.0
    return f"{n:,.1f} GB"


app.jinja_env.filters["hsize"] = human_size


def _pdate(s):
    try:
        if isinstance(s, (int, float)) and s > 0:
            return datetime.fromtimestamp(s).strftime("%Y-%m-%d %H:%M:%S")
        return (str(s or "").replace("T", " ").replace("Z", "")[:19]) or "—"
    except Exception:
        return "—"


app.jinja_env.filters["pdate"] = _pdate


def paginate(items, page, per):
    total = len(items)
    pages = max(1, (total + per - 1) // per)
    page = min(max(1, page), pages)
    return items[(page - 1) * per: page * per], page, pages, total


def sheet_unique(used, name):
    t = re.sub(r"[\[\]:*?/\\]", "_", (name or ""))[:31] or "Sheet"
    t2, k = t, 2
    while t2 in used:
        t2 = f"{t[:28]}_{k}"
        k += 1
    used.add(t2)
    return t2


def xlsx_response(sheets, filename):
    """sheets: [(title, headers, rows, widths_from_data)] → فایل اکسل برای دانلود"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except Exception:
        abort(500, "کتابخانه openpyxl نصب نیست:  pip install openpyxl")
    wb = Workbook()
    wb.remove(wb.active)
    used = set()
    hdr_fill = PatternFill("solid", fgColor="0E7490")
    hdr_font = Font(bold=True, color="FFFFFF")
    for title, headers, rows in sheets:
        ws = wb.create_sheet(sheet_unique(used, title))
        ws.sheet_view.rightToLeft = True
        ws.append(list(headers))
        for c in ws[1]:
            c.font = hdr_font
            c.fill = hdr_fill
            c.alignment = Alignment(horizontal="center")
        for r in rows:
            ws.append(["" if v is None else v for v in r])
        ws.freeze_panes = "A2"
        for i, h in enumerate(headers, start=1):
            wds = [len(str(h))] + [len(str(r[i - 1])) for r in rows[:300] if i - 1 < len(r)]
            ws.column_dimensions[get_column_letter(i)].width = min(55, max(10, (max(wds) if wds else 10) + 4))
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    from flask import Response
    return Response(
        bio.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"})


def csv_response(headers, rows, filename):
    import csv as _csv
    bio = io.StringIO()
    w = _csv.writer(bio)
    w.writerow(headers)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    from flask import Response
    return Response("\ufeff" + bio.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"})


def rebuild_full_export():
    """ساخت دوباره‌ی export.xlsx کامل — حتی اگر خزش نیمه‌کاره مانده باشد"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    db = get_db()
    now = datetime.now().isoformat(timespec="seconds")
    sheets = []
    n_pages = q1("SELECT COUNT(*) c FROM pages")["c"]
    n_texts = q1("SELECT COUNT(*) c FROM page_texts")["c"]
    n_tables = q1("SELECT COUNT(*) c FROM html_tables")["c"]
    n_rows = q1("SELECT COUNT(*) c FROM table_rows")["c"]
    n_links = q1("SELECT COUNT(*) c FROM links")["c"]
    ds = qall("SELECT * FROM datasets ORDER BY id")
    ds_total = sum(table_count(d["sqlite_table"]) for d in ds)
    sheets.append(("خلاصه",
                   ["شرح", "تعداد", "زمان"],
                   [["صفحه‌های خزیده‌شده", n_pages, now],
                    ["متن‌های برداشت‌شده", n_texts, ""],
                    ["جدول‌های HTML", n_tables, ""],
                    ["ردیف‌های جدول", n_rows, ""],
                    ["لینک‌ها", n_links, ""],
                    ["مجموعه‌داده‌ها", len(ds), ""],
                    ["کل ردیف‌های داده", ds_total, ""]]))
    sheets.append(("صفحه‌ها",
                   ["شناسه", "آدرس", "عنوان", "وضعیت HTTP", "زمان", "جدول‌ها", "متن‌ها", "فایل HTML", "اسکرین‌شات"],
                   [[p["id"], p["url"], p["title"], p["http_status"], p["crawled_at"],
                     p["n_tables"], p["n_texts"], (p["html_file"] or "").replace("\\", "/"),
                     (p["screenshot_file"] or "").replace("\\", "/")]
                    for p in qall("SELECT * FROM pages ORDER BY id")]))
    dss = []
    for d in ds:
        name = d["sqlite_table"]
        cols = [r[1] for r in db.execute(f'PRAGMA table_info("{name}")').fetchall() if r[1] != "_id"]
        if not cols:
            continue
        sel = ", ".join(f'"{c}"' for c in cols)
        rows = db.execute(f'SELECT {sel} FROM "{name}"').fetchall()
        dss.append([name, len(rows), len(cols), d["source_url"] or "", d["created_at"] or ""])
        sheets.append((name, cols, rows))
    sheets.append(("مجموعه‌داده‌ها", ["جدول", "ردیف‌ها", "ستون‌ها", "منبع (URL)", "زمان ساخت"], dss))
    sheets.append(("جدول‌های HTML",
                   ["شناسه", "صفحه", "عنوان/کپشن", "ردیف‌ها", "ستون‌ها", "جدول داده", "سرستون‌ها"],
                   [[t["id"], t["page_id"], t["caption"], t["n_rows"], t["n_cols"],
                     t["dataset_table"] or "", t["headers_json"] or ""]
                    for t in qall("SELECT * FROM html_tables ORDER BY id")]))
    sheets.append(("لینک‌ها", ["صفحه", "متن لینک", "آدرس"],
                   [[l["page_id"], l["text"], l["url"]] for l in qall("SELECT * FROM links ORDER BY id")]))
    texts = qall("SELECT page_id, kind, content FROM page_texts ORDER BY page_id, id")
    sheets.append(("متن‌ها", ["صفحه", "نوع", "متن"], [[t["page_id"], t["kind"], t["content"]] for t in texts]))

    wb = Workbook()
    wb.remove(wb.active)
    used = set()
    hdr_fill = PatternFill("solid", fgColor="0E7490")
    hdr_font = Font(bold=True, color="FFFFFF")
    for title, headers, rows in sheets:
        ws = wb.create_sheet(sheet_unique(used, title))
        ws.sheet_view.rightToLeft = True
        ws.append(list(headers))
        for c in ws[1]:
            c.font = hdr_font
            c.fill = hdr_fill
            c.alignment = Alignment(horizontal="center")
        for r in rows:
            ws.append(["" if v is None else v for v in r])
        ws.freeze_panes = "A2"
        for i, h in enumerate(headers, start=1):
            wds = [len(str(h))] + [len(str(r[i - 1])) for r in rows[:300] if i - 1 < len(r)]
            ws.column_dimensions[get_column_letter(i)].width = min(55, max(10, (max(wds) if wds else 10) + 4))
    path = os.path.join(OUT_DIR, "export.xlsx")
    wb.save(path)
    return path, len(sheets) - 1


# ------------------------------------------------------------------ مسیرها
@app.context_processor
def ctx():
    return dict(APP_NAME=APP_NAME, VERSION=VERSION, DB_PATH=DB_PATH,
                OUT_DIR=OUT_DIR, DB_SIZE=db_size_str(DB_PATH) if DB_PATH else "—",
                cur_page=lambda: request.endpoint or "")


@app.route("/")
def dashboard():
    if not DB_PATH:
        return render_template("setup.html")
    stats = {
        "pages": q1("SELECT COUNT(*) c FROM pages")["c"] or 0,
        "main_pages": q1("SELECT COUNT(*) c FROM pages WHERE page_state=0")["c"] or 0,
        "texts": q1("SELECT COUNT(*) c FROM page_texts")["c"] or 0,
        "tables": q1("SELECT COUNT(*) c FROM html_tables")["c"] or 0,
        "trows": q1("SELECT COUNT(*) c FROM table_rows")["c"] or 0,
        "links": q1("SELECT COUNT(*) c FROM links")["c"] or 0,
        "datasets": q1("SELECT COUNT(*) c FROM datasets")["c"] or 0,
    }
    ds = qall("SELECT * FROM datasets ORDER BY id")
    ds_rows = []
    for d in ds:
        ds_rows.append({"name": d["sqlite_table"], "src": d["source_url"],
                        "rows": table_count(d["sqlite_table"]),
                        "cols": len(json.loads(d["headers_json"] or "[]"))})
    ds_rows.sort(key=lambda x: -x["rows"])
    stats["drows"] = sum(r["rows"] for r in ds_rows)
    recent = qall("SELECT * FROM pages WHERE page_state=0 AND title IS NOT NULL "
                  "ORDER BY crawled_at DESC, id DESC LIMIT 10")
    kinds = qall("SELECT kind, COUNT(*) n FROM page_texts GROUP BY kind ORDER BY n DESC")
    statuses = qall("SELECT COALESCE(http_status, -1) s, COUNT(*) n FROM pages WHERE page_state=0 GROUP BY s ORDER BY n DESC")
    last = q1("SELECT MAX(crawled_at) m FROM pages")
    gallery_n = len(gallery_items())
    html_n = len(list_html_files())
    export_path = os.path.join(OUT_DIR, "export.xlsx") if OUT_DIR else None
    export_info = None
    if export_path and os.path.isfile(export_path):
        export_info = {"size": os.path.getsize(export_path), "mtime": os.path.getmtime(export_path)}
        # اگر فقط سرستون خلاصه داشته باشد، «خالی» شناخته می‌شود
        try:
            import openpyxl
            wb = openpyxl.load_workbook(export_path, read_only=True)
            export_info["sheets"] = len(wb.sheetnames)
            ws = wb[wb.sheetnames[0]]
            export_info["empty"] = (ws.max_row or 1) < 2
            wb.close()
        except Exception:
            export_info["sheets"] = 0
            export_info["empty"] = True
    top_links = qall("SELECT url, COUNT(*) n FROM links GROUP BY url ORDER BY n DESC LIMIT 8")
    return render_template("dashboard.html", stats=stats, ds_rows=ds_rows[:10], recent=recent,
                           kinds=kinds, statuses=statuses, last=last["m"] if last else None,
                           gallery_n=gallery_n, html_n=html_n, export_info=export_info,
                           top_links=top_links)


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        global DB_PATH, OUT_DIR
        ndb = request.form.get("db_path", "").strip().strip('"')
        nout = request.form.get("out_dir", "").strip().strip('"')
        if ndb and os.path.isfile(ndb):
            DB_PATH = os.path.abspath(ndb)
            if not nout:
                nout = os.path.dirname(DB_PATH)
            save_settings({"db_path": DB_PATH, "out_dir": os.path.abspath(nout) if nout else ""})
            if nout and os.path.isdir(nout):
                OUT_DIR = os.path.abspath(nout)
            flash("تنظیمات ذخیره شد. ✅", "ok")
            return redirect(url_for("dashboard"))
        flash("فایل دیتابیس پیدا نشد — مسیر را بررسی کنید.", "err")
    return render_template("settings.html")


@app.route("/pages")
def pages():
    if not DB_PATH:
        return redirect(url_for("dashboard"))
    pg = request.args.get("page", 1, type=int)
    qs = request.args.get("q", "").strip()
    state = request.args.get("state", "", type=str)
    where, args = [], []
    if qs:
        where.append("(title LIKE ? OR url LIKE ?)")
        args += [f"%{qs}%"] * 2
    if state == "main":
        where.append("page_state=0")
    elif state.isdigit():
        where.append("page_state=?")
        args.append(int(state))
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    total = q1(f"SELECT COUNT(*) c FROM pages {wsql}", args)["c"] or 0
    pages_n = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    pg = min(max(1, pg), pages_n)
    rows = qall(f"SELECT * FROM pages {wsql} ORDER BY id LIMIT ? OFFSET ?",
                args + [PAGE_SIZE, (pg - 1) * PAGE_SIZE])
    return render_template("pages.html", rows=rows, page=pg, pages_n=pages_n, total=total,
                           q=qs, state=state)


@app.route("/page/<int:pid>")
def page_detail(pid):
    if not DB_PATH:
        return redirect(url_for("dashboard"))
    p = q1("SELECT * FROM pages WHERE id=?", (pid,))
    if not p:
        abort(404)
    texts = qall("SELECT * FROM page_texts WHERE page_id=? ORDER BY id", (pid,))
    groups = {}
    for t in texts:
        groups.setdefault(t["kind"], []).append(t)
    order = ["h1", "h2", "h3", "h4", "p", "li", "meta"]
    grouped = [(k, groups[k]) for k in order if k in groups] + \
              [(k, v) for k, v in groups.items() if k not in order]
    tables = qall("SELECT * FROM html_tables WHERE page_id=? ORDER BY table_index", (pid,))
    links = qall("SELECT * FROM links WHERE page_id=? ORDER BY id", (pid,))
    shot = norm_rel(p["screenshot_file"])
    htmlf = norm_rel(p["html_file"])
    ptexts = []
    for t in tables:
        dsn = t["dataset_table"]
        ptexts.append({"t": t, "rows": (q1(f"SELECT COUNT(*) c FROM table_rows WHERE table_id=?", (t["id"],))["c"]
                                        if True else 0)})
    return render_template("page.html", p=p, grouped=grouped, tables=ptexts, links=links,
                           shot=shot, htmlf=htmlf, n_texts=len(texts))


@app.route("/tables")
def tables():
    if not DB_PATH:
        return redirect(url_for("dashboard"))
    pg = request.args.get("page", 1, type=int)
    qs = request.args.get("q", "").strip()
    where, args = [], []
    if qs:
        where.append("(caption LIKE ? OR dataset_table LIKE ? OR headers_json LIKE ?)")
        args += [f"%{qs}%"] * 3
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    total = q1(f"SELECT COUNT(*) c FROM html_tables {wsql}", args)["c"] or 0
    pages_n = max(1, (total + 50 - 1) // 50)
    pg = min(max(1, pg), pages_n)
    rows = qall(f"""SELECT t.*, p.title page_title, p.url page_url,
                    (SELECT COUNT(*) FROM table_rows r WHERE r.table_id=t.id) real_rows
                    FROM html_tables t LEFT JOIN pages p ON p.id=t.page_id
                    {wsql.replace('caption', 't.caption').replace('dataset_table', 't.dataset_table')
                         .replace('headers_json', 't.headers_json')}
                    ORDER BY t.id LIMIT 50 OFFSET ?""", args + [(pg - 1) * 50])
    return render_template("tables.html", rows=rows, page=pg, pages_n=pages_n, total=total, q=qs)


@app.route("/table/<int:tid>")
def table_detail(tid):
    if not DB_PATH:
        return redirect(url_for("dashboard"))
    t = q1("""SELECT t.*, p.title page_title, p.url page_url, p.id pid
              FROM html_tables t LEFT JOIN pages p ON p.id=t.page_id WHERE t.id=?""", (tid,))
    if not t:
        abort(404)
    try:
        headers = json.loads(t["headers_json"] or "[]")
    except Exception:
        headers = []
    pg = request.args.get("page", 1, type=int)
    total = q1("SELECT COUNT(*) c FROM table_rows WHERE table_id=?", (tid,))["c"] or 0
    pages_n = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    pg = min(max(1, pg), pages_n)
    rws = qall("SELECT data_json FROM table_rows WHERE table_id=? ORDER BY row_index LIMIT ? OFFSET ?",
               (tid, PAGE_SIZE, (pg - 1) * PAGE_SIZE))
    rows = []
    for r in rws:
        try:
            cells = json.loads(r["data_json"])
        except Exception:
            cells = [r["data_json"]]
        if len(cells) < len(headers):
            cells += [""] * (len(headers) - len(cells))
        rows.append(cells[:len(headers)] if headers else cells)
    return render_template("table.html", t=t, headers=headers, rows=rows, page=pg,
                           pages_n=pages_n, total=total)


@app.route("/export/table/<int:tid>.<fmt>")
@app.route("/export/table/<int:tid>.<fmt>", endpoint="export_table")
def export_table(tid, fmt="xlsx"):
    t = q1("SELECT * FROM html_tables WHERE id=?", (tid,))
    if not t:
        abort(404)
    try:
        headers = json.loads(t["headers_json"] or "[]")
    except Exception:
        headers = []
    if not headers:
        headers = [f"ستون {i+1}" for i in range(t["n_cols"] or 1)]
    rows = []
    for r in qall("SELECT data_json FROM table_rows WHERE table_id=? ORDER BY row_index", (tid,)):
        try:
            cells = json.loads(r["data_json"])
        except Exception:
            cells = [r["data_json"]]
        if len(cells) < len(headers):
            cells += [""] * (len(headers) - len(cells))
        rows.append(cells[:len(headers)])
    fname = re.sub(r"[^\w\u0600-\u06FF.-]+", "_", t["caption"] or f"table-{tid}")[:40] or f"table-{tid}"
    if fmt == "csv":
        return csv_response(headers, rows, f"{fname}.csv")
    return xlsx_response([(fname, headers, rows)], f"{fname}.xlsx")


@app.route("/datasets")
def datasets():
    if not DB_PATH:
        return redirect(url_for("dashboard"))
    ds = qall("SELECT * FROM datasets ORDER BY id")
    rows = []
    for d in ds:
        name = d["sqlite_table"]
        rows.append({"d": d, "name": name, "n": table_count(name),
                     "cols": len(json.loads(d["headers_json"] or "[]"))})
    rows.sort(key=lambda x: -x["n"])
    total_rows = sum(r["n"] for r in rows)
    return render_template("datasets.html", rows=rows, total_rows=total_rows)


@app.route("/dataset/<name>")
def dataset_detail(name):
    tbl = safe_table(name)
    if not tbl:
        abort(404)
    d = q1("SELECT * FROM datasets WHERE sqlite_table=?", (tbl,))
    cols = [r[1] for r in get_db().execute(f'PRAGMA table_info("{tbl}")').fetchall() if r[1] != "_id"]
    total = table_count(tbl)
    qs = request.args.get("q", "").strip()
    pg = request.args.get("page", 1, type=int)
    where, args = "", []
    if qs:
        conds = [f'"{c}" LIKE ?' for c in cols]
        where = "WHERE " + " OR ".join(conds)
        args = [f"%{qs}%"] * len(cols)
    pages_n = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    pg = min(max(1, pg), pages_n)
    sel = ", ".join(f'"{c}"' for c in cols) or "*"
    rows = qall(f'SELECT {sel} FROM "{tbl}" {where} LIMIT ? OFFSET ?',
                args + [PAGE_SIZE, (pg - 1) * PAGE_SIZE])
    return render_template("dataset.html", d=d, name=tbl, cols=cols, rows=rows, page=pg,
                           pages_n=pages_n, total=total, q=qs)


@app.route("/export/dataset/<name>.<fmt>")
def export_dataset(name, fmt="xlsx"):
    tbl = safe_table(name)
    if not tbl:
        abort(404)
    cols = [r[1] for r in get_db().execute(f'PRAGMA table_info("{tbl}")').fetchall() if r[1] != "_id"]
    sel = ", ".join(f'"{c}"' for c in cols) or "*"
    rows = get_db().execute(f'SELECT {sel} FROM "{tbl}"').fetchall()
    rows = [tuple(r) for r in rows]
    fname = re.sub(r"[^\w\u0600-\u06FF.-]+", "_", tbl)[:40] or tbl
    if fmt == "csv":
        return csv_response(cols, rows, f"{fname}.csv")
    return xlsx_response([(tbl, cols, rows)], f"{fname}.xlsx")


@app.route("/gallery")
def gallery():
    items = gallery_items()
    folder = request.args.get("dir", "")
    if folder:
        items = [i for i in items if i["folder"] == folder]
    folders = sorted({i["folder"] for i in gallery_items()})
    pg = request.args.get("page", 1, type=int)
    pageitems, pg, pages_n, total = paginate(items, pg, GALLERY_PAGE)
    return render_template("gallery.html", items=pageitems, page=pg, pages_n=pages_n,
                           total=total, folders=folders, folder=folder)


@app.route("/files")
def files():
    items = list_html_files()
    pg = request.args.get("page", 1, type=int)
    pageitems, pg, pages_n, total = paginate(items, pg, 50)
    return render_template("files.html", items=pageitems, page=pg, pages_n=pages_n, total=total)


@app.route("/files/view")
def file_view():
    rel = request.args.get("path", "")
    if not norm_rel(rel):
        abort(404)
    name = os.path.basename(rel)
    return render_template("fileview.html", rel=rel, name=name)


@app.route("/output/<path:rel>")
def output_file(rel):
    if not OUT_DIR:
        abort(404)
    return send_from_directory(OUT_DIR, rel)


@app.route("/search")
def search():
    if not DB_PATH:
        return redirect(url_for("dashboard"))
    qs = request.args.get("q", "").strip()
    res = {"pages": [], "texts": [], "links": [], "tables": []}
    if qs:
        like = f"%{qs}%"
        res["pages"] = qall("SELECT * FROM pages WHERE title LIKE ? OR url LIKE ? "
                            "ORDER BY id LIMIT 40", (like, like))
        res["texts"] = qall("""SELECT t.*, p.title page_title FROM page_texts t
                               LEFT JOIN pages p ON p.id=t.page_id
                               WHERE t.content LIKE ? ORDER BY t.id LIMIT 60""", (like,))
        res["links"] = qall("""SELECT l.*, p.title page_title FROM links l
                               LEFT JOIN pages p ON p.id=l.page_id
                               WHERE l.text LIKE ? OR l.url LIKE ? ORDER BY l.id LIMIT 40""",
                            (like, like))
        res["tables"] = qall("""SELECT t.*, p.title page_title FROM html_tables t
                                LEFT JOIN pages p ON p.id=t.page_id
                                WHERE t.caption LIKE ? OR t.headers_json LIKE ?
                                ORDER BY t.id LIMIT 30""", (like, like))
    n = sum(len(v) for v in res.values())
    return render_template("search.html", q=qs, res=res, n=n)


@app.route("/logs")
def logs():
    if not DB_PATH:
        return redirect(url_for("dashboard"))
    rows = qall("SELECT * FROM crawl_log ORDER BY id DESC LIMIT 600")
    return render_template("logs.html", rows=rows)


@app.route("/api-responses")
def api_responses():
    if not DB_PATH:
        return redirect(url_for("dashboard"))
    rows = qall("SELECT * FROM api_responses ORDER BY id DESC LIMIT 100")
    pretty = []
    for r in rows:
        body = r["body"] or ""
        fmt = "text"
        try:
            v = json.loads(body)
            body = json.dumps(v, ensure_ascii=False, indent=2)
            fmt = "json"
        except Exception:
            pass
        pretty.append(dict(r, body=body[:60000], fmt=fmt))
    return render_template("api.html", rows=pretty)


@app.route("/export", methods=["GET"])
def export_center():
    if not DB_PATH:
        return redirect(url_for("dashboard"))
    ds = qall("SELECT * FROM datasets ORDER BY id")
    rows = []
    for d in ds:
        rows.append({"name": d["sqlite_table"], "src": d["source_url"], "n": table_count(d["sqlite_table"])})
    export_path = os.path.join(OUT_DIR, "export.xlsx") if OUT_DIR else None
    info = None
    if export_path and os.path.isfile(export_path):
        info = {"size": os.path.getsize(export_path), "mtime": os.path.getmtime(export_path)}
    return render_template("export.html", rows=rows, info=info, tables_n=q1("SELECT COUNT(*) c FROM html_tables")["c"])


@app.route("/export/build", methods=["POST"])
def export_build():
    if not DB_PATH:
        return redirect(url_for("dashboard"))
    try:
        path, nsheets = rebuild_full_export()
        flash(f"خروجی اکسل کامل ساخته شد ✅ — {nsheets} شیت در «{os.path.basename(OUT_DIR)}/export.xlsx»", "ok")
    except Exception as e:
        flash(f"ساخت خروجی ناموفق بود: {e}", "err")
    return redirect(url_for("export_center"))


@app.route("/api/stats")
def api_stats():
    if not DB_PATH:
        return jsonify({})
    return jsonify({
        "pages": q1("SELECT COUNT(*) c FROM pages")["c"],
        "texts": q1("SELECT COUNT(*) c FROM page_texts")["c"],
        "tables": q1("SELECT COUNT(*) c FROM html_tables")["c"],
        "links": q1("SELECT COUNT(*) c FROM links")["c"],
    })


# ------------------------------------------------------------------ خطاها
@app.errorhandler(404)
def nf(e):
    return render_template("error.html", code=404,
                           msg="صفحه‌ای که می‌خواستید پیدا نشد."), 404


@app.errorhandler(500)
def ie(e):
    return render_template("error.html", code=500,
                           msg="خطای داخلی — احتمالاً دیتابیس در دسترس نیست یا فرمت داده متفاوت است."), 500


# ------------------------------------------------------------------ اصلی
def main():
    global DB_PATH, OUT_DIR
    ap = argparse.ArgumentParser(description="نمایشگر وب داده‌های سایت‌کاو")
    ap.add_argument("--db", help="مسیر فایل site_data.db")
    ap.add_argument("--out", help="پوشه‌ی خروجی (شامل html/ و screenshots/)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5002)
    ap.add_argument("--no-browser", action="store_true", help="باز شدن خودکار مرورگر")
    args = ap.parse_args()

    DB_PATH = find_db(args.db)
    if DB_PATH:
        out = args.out or load_settings().get("out_dir") or os.path.dirname(DB_PATH)
        OUT_DIR = os.path.abspath(out) if out and os.path.isdir(out) else os.path.dirname(DB_PATH)
    elif args.out and os.path.isdir(args.out):
        OUT_DIR = os.path.abspath(args.out)

    url = f"http://{args.host}:{args.port}"
    print("=" * 62)
    print(f"  سایت‌کاو — نمایشگر داده‌ها (نسخه {VERSION})")
    print(f"  آدرس:  {url}")
    print(f"  دیتابیس:  {DB_PATH or 'پیدا نشد!'}")
    print(f"  پوشه خروجی:  {OUT_DIR or '—'}")
    print("  برای بستن: Ctrl+C")
    print("=" * 62, flush=True)
    if not args.no_browser:
        threading.Timer(1.2, lambda: _open_browser(url)).start()
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False, threaded=True)


def _open_browser(url):
    try:
        webbrowser.open(url)
    except Exception:
        pass


if __name__ == "__main__":
    main()
