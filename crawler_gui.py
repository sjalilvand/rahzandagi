# -*- coding: utf-8 -*-
"""
سایت‌کاو ۳.۳ — رابط گرافیکی
====================================================
تغییرهای نسخه ۳.۳ نسبت به ۳.۲:
  • رفع گیر کردن روی صفحات «کد ملی / کد پرونده / رهگیری»: این صفحات دیگر
    صفحه ورود تشخیص داده نمی‌شوند؛ برنامه دیگر مدام کد ملی امتحان نمی‌کند
  • دکمه‌ی «⏭ رد کردن صفحه فعلی»: هر لحظه که صفحه‌ای به دلایل مختلف گیر کرد،
    با این دکمه صفحه رها می‌شود و خزش به صفحه بعدی می‌رود
  • تشخیص قوی‌تر صفحات فیلتر: بررسی داخل iframeها، بی‌اثر شدن جدول‌های
    اطلاعاتی کوچک (مثل پنل کاربر)، و بررسی دوباره برای سایت‌های React/Angular
  • «رد شدن خودکار از صفحات فیلتر» پیش‌فرض روشن است (حتی با تنظیمات قدیمی)

تغییرهای نسخه ۳.۲:
  • رد شدن خودکار از صفحات فیلتر + دکمه‌های «ادامه/رد کردن» درون مرورگر

تغییرهای نسخه ۳.۱:
  • کپی/برش/چسباندن در همه‌ی فیلدها: راست‌کلیک + Ctrl+V/C/X/A
  • پنجره‌ی کد پیامکی همیشه-رو با شمارش‌معکوس و دکمه «خودم در مرورگر وارد کردم»
  • تنظیمات فرم بین اجراها خودکار ذخیره و بازیابی می‌شود

اجرا:  python crawler_gui.py     (یا دوبار کلیک روی run_gui.bat)
"""

import json
import os
import queue
import sys
import threading
import traceback

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

PROG_DIR = os.path.dirname(os.path.abspath(__file__))
if PROG_DIR not in sys.path:
    sys.path.insert(0, PROG_DIR)

import crawler  # noqa: E402  (همان پوشه)
from crawler import OTP_IN_BROWSER  # noqa: E402

SETTINGS_FILE = os.path.join(PROG_DIR, "gui_settings.json")


# ---------------------------------------------------------------- کپی/چسباندن همگانی
# میان‌برهای Ctrl+V و Ctrl+C فقط وقتی کار می‌کنند که چیدمان صفحه‌کلید انگلیسی باشد؛
# با چیدمان فارسی، Tk سمبل کلید دیگری می‌بیند و میان‌بر اجرا نمی‌شود.
# راه‌حل: کار با «کد فیزیکی کلید» (event.keycode) — مستقل از چیدمان:
#   ویندوز: V=86، C=67، X=88، A=65، Z=90، Insert=45
def _clipboard_get(w):
    try:
        return w.clipboard_get()
    except Exception:
        return None


def _entry_copy(w):
    try:
        s = w.selection_get()
    except Exception:
        s = w.get()
    if s:
        w.clipboard_clear()
        w.clipboard_append(s)


def _entry_cut(w):
    _entry_copy(w)
    try:
        if w.selection_present():
            w.delete("sel.first", "sel.last")
    except Exception:
        pass


def _entry_paste(w):
    data = _clipboard_get(w)
    if data is None:
        return
    try:
        if w.selection_present():
            w.delete("sel.first", "sel.last")
    except Exception:
        pass
    try:
        pos = w.index("insert")
        w.insert(pos, data)
    except Exception:
        pass


def _entry_selall(w):
    try:
        w.selection_range(0, "end")
        w.icursor("end")
    except Exception:
        pass


def _entry_del(w):
    try:
        if w.selection_present():
            w.delete("sel.first", "sel.last")
        else:
            pos = w.index("insert")
            w.delete(pos)
    except Exception:
        pass


def _text_copy(w):
    try:
        s = w.get("sel.first", "sel.last")
        if s:
            w.clipboard_clear()
            w.clipboard_append(s)
    except Exception:
        pass


def _text_cut(w):
    _text_copy(w)
    try:
        w.delete("sel.first", "sel.last")
    except Exception:
        pass


def _text_paste(w):
    data = _clipboard_get(w)
    if data is None:
        return
    try:
        w.delete("sel.first", "sel.last")
    except Exception:
        pass
    try:
        w.insert("insert", data)
    except Exception:
        pass


def _text_selall(w):
    try:
        w.tag_add("sel", "1.0", "end-1c")
    except Exception:
        pass


def _is_entrylike(w):
    return isinstance(w, (ttk.Entry, tk.Entry, ttk.Spinbox, tk.Spinbox))


def _entry_undo(w):
    try:
        w.event_generate("<<Undo>>")
    except Exception:
        pass


def _on_key(w, e):
    """میان‌برها بر اساس کد فیزیکی کلید — مستقل از چیدمان فارسی/انگلیسی"""
    ctrl = bool(e.state & 0x0004)
    shift = bool(e.state & 0x0001)
    k = getattr(e, "keycode", 0) or 0
    entry = _is_entrylike(w)
    if not (ctrl or shift):
        return None
    try:
        if ctrl and k == 86:            # V
            (_entry_paste if entry else _text_paste)(w)
            return "break"
        if ctrl and k == 67:            # C
            (_entry_copy if entry else _text_copy)(w)
            return "break"
        if ctrl and k == 88:            # X
            (_entry_cut if entry else _text_cut)(w)
            return "break"
        if ctrl and k == 65:            # A
            (_entry_selall if entry else _text_selall)(w)
            return "break"
        if ctrl and k == 90:            # Z
            if entry:
                _entry_undo(w)
            return "break"
        if k == 45 and ctrl:            # Ctrl+Insert = کپی
            (_entry_copy if entry else _text_copy)(w)
            return "break"
        if k == 45 and shift:           # Shift+Insert = چسباندن
            (_entry_paste if entry else _text_paste)(w)
            return "break"
    except Exception:
        pass
    return None


def _show_menu(w, e):
    entry = _is_entrylike(w)
    editable = True
    try:
        editable = str(w.cget("state")) != "disabled"
    except Exception:
        pass
    m = tk.Menu(w, tearoff=0, font=("Tahoma", 9))
    if entry:
        copy_f, cut_f, paste_f, sel_f = _entry_copy, _entry_cut, _entry_paste, _entry_selall
    else:
        copy_f, cut_f, paste_f, sel_f = _text_copy, _text_cut, _text_paste, _text_selall
    has_sel = False
    try:
        has_sel = bool(w.selection_present()) if entry else bool(w.tag_ranges("sel"))
    except Exception:
        pass
    m.add_command(label="کپی", command=lambda: copy_f(w), state="normal" if has_sel else "disabled")
    if editable:
        m.add_command(label="برش", command=lambda: cut_f(w), state="normal" if has_sel else "disabled")
        m.add_command(label="چسباندن", command=lambda: paste_f(w),
                      state="normal" if _clipboard_get(w) is not None else "disabled")
        m.add_separator()
        m.add_command(label="انتخاب همه", command=lambda: sel_f(w))
    try:
        m.tk_popup(e.x_root, e.y_root)
    finally:
        try:
            m.grab_release()
        except Exception:
            pass


def enable_clipboard(w):
    """راست‌کلیک + میان‌برهای کپی/چسباندن را روی یک ویجت فعال می‌کند"""
    try:
        w.bind("<Control-KeyPress>", lambda e: _on_key(w, e), add=True)
        # حالت چیدمان انگلیسی: میان‌بر اختصاصی دقیق‌تر است و اولویت دارد
        for seq in ("<Control-v>", "<Control-V>", "<Control-c>", "<Control-C>",
                    "<Control-x>", "<Control-X>", "<Control-a>", "<Control-A>",
                    "<Control-z>", "<Control-Z>"):
            try:
                w.bind(seq, lambda e: _on_key(w, e), add=True)
            except Exception:
                pass
        w.bind("<Button-3>", lambda e: _show_menu(w, e), add=True)
    except Exception:
        pass


# ---------------------------------------------------------------- جریان خروجی به پنجره
class QueueStream:
    """جایگزین stdout — خط‌ها را به صف پیام رابط گرافیکی می‌فرستد"""

    def __init__(self, q):
        self.q = q
        self._buf = ""

    def write(self, s):
        try:
            self._buf += s
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                self.q.put(("log", line))
        except Exception:
            pass
        return len(s)

    def flush(self):
        pass


# ---------------------------------------------------------------- قلاب‌های گرافیکی برای هسته خزنده
class GuiHooks:
    """همان قرارداد UIHooks هسته — ولی درخواست‌ها را به نخ اصلی رابط گرافیکی می‌فرستد.
    انتظار پاسخ با گام ۱ثانیه‌ای است تا «توقف» هم در حین انتظار کار کند."""

    def __init__(self, app):
        self.app = app
        self.stopped = False

    def _ask(self, kind, payload, on_stop):
        resp = queue.Queue()
        self.app.msg_q.put((kind, payload, resp))
        while True:
            try:
                return resp.get(timeout=1.0)
            except queue.Empty:
                if self.stopped:
                    return on_stop

    def ask_otp(self, text):
        return self._ask("otp", text, None)          # توقف → انصراف از ورود

    def filter_pause(self, url, page=None):
        """انتظار برای «ادامه/رد شدن»: پاسخ از هر کدام زودتر برسد پذیرفته می‌شود —
        ۱) دکمه‌های درون مرورگر (نوار شناور پایین صفحه)
        ۲) نوار «منتظر شما» در رابط گرافیکی
        ۳) دکمه «توقف» برنامه"""
        import time as _t
        resp = queue.Queue()
        self.app.msg_q.put(("filter", url, resp))
        while True:
            if page is not None:
                try:
                    ans = page.evaluate(crawler.JS_PAUSE_ANSWER)
                    if ans in ("continue", "skip"):
                        return ans
                except Exception:
                    pass
            try:
                return resp.get_nowait()
            except queue.Empty:
                pass
            if self.stopped:
                return "skip"
            _t.sleep(0.4)

    def progress(self, done, total, url):
        self.app.msg_q.put(("progress", done, total, url))

    def skip_now(self):
        """فرمان «رد کردن صفحه فعلی» — اگر کاربر دکمه را زده باشد True و مصرف می‌شود"""
        try:
            v = bool(self.app._skip_flag)
            self.app._skip_flag = False
            return v
        except Exception:
            return False


# ---------------------------------------------------------------- پنجره کد تأیید دومعلی
class OTPDialog(tk.Toplevel):
    """پنجره دریافت کد پیامکی — همیشه روی همه پنجره‌ها، با شمارش‌معکوس و سه دکمه:
    «تأیید و ادامه» = برنامه خودش کد را در سایت ثبت می‌کند
    «خودم در مرورگر وارد کردم» = برنامه فقط منتظر موفقیت ورود می‌ماند
    «رد کردن» = انصراف از ورود"""

    TIMEOUT_S = 600   # ۱۰ دقیقه فرصت پاسخ — بعد از آن پنجره خودش بسته می‌شود

    def __init__(self, master, text, resp_q):
        super().__init__(master)
        self.resp_q = resp_q
        self.left = self.TIMEOUT_S
        self.title("ورود دومعلی — کد تأیید")
        self.configure(bg="#f5f6fa")
        self.resizable(False, False)
        frm = ttk.Frame(self, padding=18)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="🔐 " + (text or "کد تأیید را وارد کنید"),
                  font=("Tahoma", 11, "bold"), wraplength=430,
                  justify="right").pack(anchor="e", pady=(0, 8))
        ttk.Label(frm, text="کدی که با پیامک/ایمیل دریافت کرده‌اید (می‌توانید با Ctrl+V بچسبانید):",
                  wraplength=430, justify="right").pack(anchor="e")
        self.ent = ttk.Entry(frm, width=24, font=("Tahoma", 13), justify="center")
        self.ent.pack(pady=8, ipady=4)
        enable_clipboard(self.ent)
        self.ent.focus_force()
        self.lbl_timer = ttk.Label(frm, text="", foreground="#8a6d00")
        self.lbl_timer.pack(anchor="e")
        btns = ttk.Frame(frm)
        btns.pack(pady=(4, 0))
        ttk.Button(btns, text="تأیید و ادامه", command=self._ok).pack(side="right", padx=4)
        ttk.Button(btns, text="خودم در مرورگر وارد کردم — ادامه بده",
                   command=self._in_browser).pack(side="right", padx=4)
        ttk.Button(btns, text="رد کردن", command=self._cancel).pack(side="right", padx=4)
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.transient(master)
        try:
            x = master.winfo_rootx() + max(0, master.winfo_width() // 2 - 260)
            y = master.winfo_rooty() + 160
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass
        # همیشه روِ همه‌ی پنجره‌ها (مرورگر جلویش نباشد) + قفل مؤديت مطمئن
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass
        self.lift()
        self._grab()
        self.after(400, self._grab)      # یک‌بار دیگر بعد از نمایان شدن
        self.after(200, lambda: self.ent.focus_force())
        self._tick()

    def _grab(self):
        try:
            self.grab_set()
        except Exception:
            pass
        try:
            self.lift()
        except Exception:
            pass

    def _tick(self):
        if not self.winfo_exists():
            return
        self.left -= 1
        m, s = divmod(max(0, self.left), 60)
        self.lbl_timer.configure(text=f"⏳ {m:02d}:{s:02d} تا بستن خودکار پنجره")
        if self.left <= 0:
            self._cancel()
            return
        self.after(1000, self._tick)

    def _answer(self, v):
        try:
            self.resp_q.put(v)
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def _ok(self):
        self._answer(self.ent.get().strip() or None)

    def _in_browser(self):
        self._answer(OTP_IN_BROWSER)

    def _cancel(self):
        self._answer(None)


# ---------------------------------------------------------------- پنجره اصلی
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("سایت‌کاو — نسخه ۳.۳ (رابط گرافیکی)")
        self.geometry("880x760")
        self.minsize(760, 640)
        self.msg_q = queue.Queue()
        self.worker = None
        self.crawling = False
        self._skip_flag = False   # فرمان «رد کردن صفحه فعلی» (نسخه ۳.۳)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", font=("Tahoma", 10))
        style.configure("TButton", padding=6)
        style.configure("Start.TButton", font=("Tahoma", 11, "bold"), foreground="#0a6b2d")
        style.configure("Stop.TButton", font=("Tahoma", 11, "bold"), foreground="#8b1a1a")

        self._build_ui()
        self._load_settings()
        self.after(120, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------ ساخت رابط
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # --- ورود به سامانه ---
        lf_login = ttk.LabelFrame(text=" ۱) ورود به سامانه ", padding=8)
        lf_login.pack(fill="x", **pad)
        lf_login.columnconfigure(1, weight=1)

        ttk.Label(lf_login, text="آدرس سامانه:").grid(row=0, column=0, sticky="e", padx=4, pady=3)
        self.e_url = ttk.Entry(lf_login)
        self.e_url.grid(row=0, column=1, sticky="we", padx=4, pady=3)
        self.e_url.insert(0, "https://")

        ttk.Label(lf_login, text="نام کاربری / موبایل:").grid(row=1, column=0, sticky="e", padx=4, pady=3)
        self.e_user = ttk.Entry(lf_login)
        self.e_user.grid(row=1, column=1, sticky="we", padx=4, pady=3)

        ttk.Label(lf_login, text="رمز عبور:").grid(row=2, column=0, sticky="e", padx=4, pady=3)
        self.e_pass = ttk.Entry(lf_login, show="●")
        self.e_pass.grid(row=2, column=1, sticky="we", padx=4, pady=3)

        self.v_manual = tk.BooleanVar(value=False)
        ttk.Checkbutton(lf_login, variable=self.v_manual,
                        text="ورود دستی در پنجره مرورگر (کپچا یا ورود دومعلی پیچیده — خودم در مرورگر وارد می‌شوم)"
                        ).grid(row=3, column=0, columnspan=2, sticky="e", padx=4, pady=3)

        # --- محدوده خزش ---
        lf_scope = ttk.LabelFrame(text=" ۲) چه صفحاتی خزیده شود؟ ", padding=8)
        lf_scope.pack(fill="x", **pad)
        lf_scope.columnconfigure(1, weight=1)

        ttk.Label(lf_scope, text="فقط این صفحات\n(هر خط یک عبارت از آدرس؛\nخالی = همه صفحات):",
                  justify="right").grid(row=0, column=0, sticky="ne", padx=4, pady=3)
        self.t_only = scrolledtext.ScrolledText(lf_scope, height=3, font=("Tahoma", 9), wrap="word")
        self.t_only.grid(row=0, column=1, sticky="we", padx=4, pady=3)

        ttk.Label(lf_scope, text="حداکثر کل صفحات:").grid(row=1, column=0, sticky="e", padx=4, pady=3)
        self.s_maxpages = ttk.Spinbox(lf_scope, from_=5, to=100000, width=8)
        self.s_maxpages.set(500)
        self.s_maxpages.grid(row=1, column=1, sticky="w", padx=4, pady=3)

        ttk.Label(lf_scope, text="حداکثر صفحات هر فهرست\n(صفحه‌بندی):").grid(row=2, column=0, sticky="e", padx=4, pady=3)
        self.s_maxlist = ttk.Spinbox(lf_scope, from_=1, to=5000, width=8)
        self.s_maxlist.set(100)
        self.s_maxlist.grid(row=2, column=1, sticky="w", padx=4, pady=3)

        ttk.Label(lf_scope, text="تأخیر بین صفحات (میلی‌ثانیه):").grid(row=3, column=0, sticky="e", padx=4, pady=3)
        self.s_delay = ttk.Spinbox(lf_scope, from_=0, to=10000, increment=100, width=8)
        self.s_delay.set(800)
        self.s_delay.grid(row=3, column=1, sticky="w", padx=4, pady=3)

        # --- ذخیره‌سازی ---
        lf_store = ttk.LabelFrame(text=" ۳) محل و نوع ذخیره‌سازی ", padding=8)
        lf_store.pack(fill="x", **pad)
        lf_store.columnconfigure(1, weight=1)

        ttk.Label(lf_store, text="پوشه اصلی خروجی:").grid(row=0, column=0, sticky="e", padx=4, pady=3)
        row = ttk.Frame(lf_store)
        row.grid(row=0, column=1, sticky="we", padx=4, pady=3)
        row.columnconfigure(0, weight=1)
        self.e_out = ttk.Entry(row)
        self.e_out.grid(row=0, column=0, sticky="we")
        self.e_out.insert(0, os.path.join(PROG_DIR, "خروجی"))
        ttk.Button(row, text="انتخاب پوشه…", command=self._pick_dir).grid(row=0, column=1, padx=(6, 0))

        ttk.Label(lf_store, text="زیرپوشه اسکرین‌شات‌ها:").grid(row=1, column=0, sticky="e", padx=4, pady=3)
        self.e_shots = ttk.Entry(lf_store, width=24)
        self.e_shots.insert(0, "screenshots")
        self.e_shots.grid(row=1, column=1, sticky="w", padx=4, pady=3)

        ttk.Label(lf_store, text="زیرپوشه کد HTML صفحات:").grid(row=2, column=0, sticky="e", padx=4, pady=3)
        self.e_html = ttk.Entry(lf_store, width=24)
        self.e_html.insert(0, "html")
        self.e_html.grid(row=2, column=1, sticky="w", padx=4, pady=3)

        ttk.Label(lf_store, text="زیرپوشه CSS و جاوااسکریپت و قالب‌ها:").grid(row=3, column=0, sticky="e", padx=4, pady=3)
        self.e_assets = ttk.Entry(lf_store, width=24)
        self.e_assets.insert(0, "assets")
        self.e_assets.grid(row=3, column=1, sticky="w", padx=4, pady=3)

        chkrow = ttk.Frame(lf_store)
        chkrow.grid(row=4, column=0, columnspan=2, sticky="e", padx=4, pady=3)
        self.v_shots = tk.BooleanVar(value=True)
        self.v_assets = tk.BooleanVar(value=True)
        self.v_hidden = tk.BooleanVar(value=False)
        ttk.Checkbutton(chkrow, variable=self.v_shots, text="ذخیره اسکرین‌شات").pack(side="right", padx=6)
        ttk.Checkbutton(chkrow, variable=self.v_assets,
                        text="ذخیره CSS/JS/تصاویر هر صفحه").pack(side="right", padx=6)
        ttk.Checkbutton(chkrow, variable=self.v_hidden,
                        text="مرورگر پنهان باشد (بدون پنجره)").pack(side="right", padx=6)

        # --- حالت‌های ویژه ---
        lf_special = ttk.LabelFrame(text=" ۴) حالت‌های ویژه ", padding=8)
        lf_special.pack(fill="x", **pad)
        lf_special.columnconfigure(1, weight=1)

        self.v_pause = tk.BooleanVar(value=False)
        ttk.Checkbutton(lf_special, variable=self.v_pause, command=self._toggle_pause,
                        text="توقف پیش از برداشت صفحات: اول فیلترها را خودم در مرورگر اعمال می‌کنم، بعد «ادامه» را می‌زنم"
                        ).grid(row=0, column=0, columnspan=2, sticky="e", padx=4, pady=3)
        ttk.Label(lf_special, text="محدوده توقف (عبارت آدرس؛ ** = همه صفحات):").grid(
            row=1, column=0, sticky="e", padx=4, pady=3)
        self.e_pause_pat = ttk.Entry(lf_special, width=30, state="disabled")
        self.e_pause_pat.insert(0, "**")
        self.e_pause_pat.grid(row=1, column=1, sticky="w", padx=4, pady=3)

        self.v_fresh = tk.BooleanVar(value=True)
        ttk.Checkbutton(lf_special, variable=self.v_fresh,
                        text="شروع از صفر (دیتابیس قبلی به نسخه پشتیبان منتقل شود)"
                        ).grid(row=2, column=0, columnspan=2, sticky="e", padx=4, pady=3)

        self.v_skipfilter = tk.BooleanVar(value=True)
        ttk.Checkbutton(lf_special, variable=self.v_skipfilter,
                        text="رد شدن خودکار از صفحات فیلتر (کد ملی / کد پرونده / کد رهگیری و مانند آن — فقط لینک‌هایشان دنبال می‌شود)"
                        ).grid(row=3, column=0, columnspan=2, sticky="e", padx=4, pady=3)

        # --- دکمه‌ها و نوار پیشرفت ---
        bar = ttk.Frame(padding=(8, 2))
        bar.pack(fill="x")
        self.btn_start = ttk.Button(bar, text="▶  شروع خزش", style="Start.TButton", command=self._start)
        self.btn_start.pack(side="right", padx=4)
        self.btn_stop = ttk.Button(bar, text="■  توقف", style="Stop.TButton", command=self._stop,
                                   state="disabled")
        self.btn_stop.pack(side="right", padx=4)
        self.btn_skip = ttk.Button(bar, text="⏭  رد کردن صفحه فعلی", command=self._skip_now,
                                   state="disabled")
        self.btn_skip.pack(side="right", padx=4)
        ttk.Button(bar, text="باز کردن پوشه خروجی", command=self._open_out).pack(side="left", padx=4)

        self.pb = ttk.Progressbar(self, mode="determinate")
        self.pb.pack(fill="x", padx=10, pady=(2, 0))
        self.lbl_status = ttk.Label(text="آماده است — تنظیمات را پر کنید و «شروع خزش» را بزنید.",
                                    foreground="#333")
        self.lbl_status.pack(fill="x", padx=12, pady=(2, 4))

        # --- نوار توقف فیلتر (در زمان خزش ظاهر می‌شود) ---
        self.fr_filter = ttk.LabelFrame(text=" ⏸ منتظر شما ", padding=8)
        self.lbl_furl = ttk.Label(self.fr_filter, text="", foreground="#08427c", wraplength=780)
        self.lbl_furl.pack(anchor="e", pady=(0, 4))
        frow = ttk.Frame(self.fr_filter)
        frow.pack(anchor="e")
        ttk.Button(frow, text="✔ فیلترها را اعمال کردم — ادامه بده", command=lambda: self._filter_ans("continue")
                   ).pack(side="right", padx=4)
        ttk.Button(frow, text="✖ از این صفحه رد شو", command=lambda: self._filter_ans("skip")
                   ).pack(side="right", padx=4)
        # هنوز pack نشده — فقط هنگام توقف فیلتر نمایش داده می‌شود
        self._filter_resp = None

        # --- لاگ ---
        lf_log = ttk.LabelFrame(text=" گزارش زنده خزش ", padding=4)
        lf_log.pack(fill="both", expand=True, padx=8, pady=8)
        self.txt = scrolledtext.ScrolledText(lf_log, font=("Tahoma", 9), state="disabled", wrap="word",
                                             background="#101418", foreground="#d8dee9")
        self.txt.pack(fill="both", expand=True)

        # کپی/چسباندن در همه‌ی فیلدها + انتخاب متن در گزارش
        for w in (self.e_url, self.e_user, self.e_pass, self.e_out, self.e_shots,
                  self.e_html, self.e_assets, self.e_pause_pat,
                  self.s_maxpages, self.s_maxlist, self.s_delay):
            enable_clipboard(w)
        enable_clipboard(self.t_only)
        enable_clipboard(self.txt)   # فقط کپی از گزارش

        self._log("راهنما: برای کپی/چسباندن در هر فیلد، راست‌کلیک کنید یا از Ctrl+V / Ctrl+C استفاده کنید"
                  " (با چیدمان فارسی هم کار می‌کند).")

    # ------------------------------------------------ کمکی‌ها
    def _log(self, line):
        self.txt.configure(state="normal")
        self.txt.insert("end", line + "\n")
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def _toggle_pause(self):
        self.e_pause_pat.configure(state="normal" if self.v_pause.get() else "disabled")

    def _skip_now(self):
        """دکمه «رد کردن صفحه فعلی» — هر لحظه از خزش قابل استفاده است (نسخه ۳.۳)"""
        if not self.crawling:
            return
        self._skip_flag = True
        self.lbl_status.configure(text="دستور «رد کردن صفحه» ثبت شد — صفحه فعلی رها می‌شود و خزش ادامه پیدا می‌کند...")
        self._log("⏭ درخواست رد شدن از صفحه فعلی ثبت شد.")

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.e_out.get() or PROG_DIR,
                                    title="پوشه اصلی خروجی را انتخاب کنید")
        if d:
            self.e_out.delete(0, "end")
            self.e_out.insert(0, d)

    def _open_out(self):
        d = self.e_out.get().strip()
        if not os.path.isdir(d):
            messagebox.showinfo("پوشه خروجی", "هنوز پوشه خروجی ساخته نشده است. اول یک خزش اجرا کنید.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(d)  # noqa
            elif sys.platform == "darwin":
                os.system(f'open "{d}" &')
            else:
                os.system(f'xdg-open "{d}" &')
        except Exception as e:
            messagebox.showerror("خطا", f"باز کردن پوشه ممکن نشد:\n{e}")

    # ------------------------------------------------ ذخیره/بازیابی تنظیمات فرم
    def _settings_dict(self):
        return {
            "url": self.e_url.get(), "user": self.e_user.get(),
            "manual": self.v_manual.get(),
            "only": self.t_only.get("1.0", "end").rstrip("\n"),
            "maxpages": self.s_maxpages.get(), "maxlist": self.s_maxlist.get(),
            "delay": self.s_delay.get(),
            "out": self.e_out.get(), "shots": self.e_shots.get(),
            "html": self.e_html.get(), "assets": self.e_assets.get(),
            "shots_on": self.v_shots.get(), "assets_on": self.v_assets.get(),
            "hidden": self.v_hidden.get(),
            "pause": self.v_pause.get(), "pause_pat": self.e_pause_pat.get(),
            "fresh": self.v_fresh.get(), "skipfilter": self.v_skipfilter.get(),
        }

    def _apply_settings(self, s):
        try:
            if s.get("url"):
                self.e_url.delete(0, "end")
                self.e_url.insert(0, s["url"])
            if s.get("user"):
                self.e_user.insert(0, s["user"])
            self.v_manual.set(bool(s.get("manual", False)))
            if s.get("only"):
                self.t_only.insert("1.0", s["only"])
            for key, ent in (("maxpages", self.s_maxpages), ("maxlist", self.s_maxlist),
                             ("delay", self.s_delay)):
                if s.get(key):
                    ent.set(s[key])
            if s.get("out"):
                self.e_out.delete(0, "end")
                self.e_out.insert(0, s["out"])
            for key, ent in (("shots", self.e_shots), ("html", self.e_html),
                             ("assets", self.e_assets)):
                if s.get(key):
                    ent.delete(0, "end")
                    ent.insert(0, s[key])
            self.v_shots.set(bool(s.get("shots_on", True)))
            self.v_assets.set(bool(s.get("assets_on", True)))
            self.v_hidden.set(bool(s.get("hidden", False)))
            self.v_pause.set(bool(s.get("pause", False)))
            self._toggle_pause()
            if s.get("pause_pat"):
                self.e_pause_pat.delete(0, "end")
                self.e_pause_pat.insert(0, s["pause_pat"])
            self.v_fresh.set(bool(s.get("fresh", True)))
            self.v_skipfilter.set(bool(s.get("skipfilter", True)))
        except Exception:
            pass

    def _save_settings(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._settings_dict(), f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def _load_settings(self):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                s = json.load(f)
            self._apply_settings(s)
        except Exception:
            pass

    def _on_close(self):
        self._save_settings()
        self.destroy()

    # ------------------------------------------------ پاسخ به قلاب‌ها (از نخ خزنده)
    def _ask_otp(self, text, resp_q):
        try:
            OTPDialog(self, text, resp_q)
        except Exception:
            # اگر پنجره به هر دلیل ساخته نشد، خزنده قفل نشود و مسیر جایگزین برود
            try:
                resp_q.put(None)
            except Exception:
                pass

    def _show_filter(self, url, resp_q):
        self._filter_resp = resp_q
        self.lbl_furl.configure(text="آدرس صفحه: " + url)
        self.fr_filter.pack(fill="x", padx=10, pady=4)
        self.lbl_status.configure(text="⏸ در مرورگر فیلترها را اعمال کنید و بعد «ادامه» را بزنید.")
        self.lift()

    def _filter_ans(self, what):
        if self._filter_resp is not None:
            try:
                self._filter_resp.put(what)
            except Exception:
                pass
            self._filter_resp = None
        self.fr_filter.pack_forget()

    # ------------------------------------------------ صف پیام‌ها
    def _poll(self):
        try:
            while True:
                item = self.msg_q.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._log(item[1])
                elif kind == "progress":
                    _, done, total, url = item
                    self.pb.configure(maximum=max(1, total), value=done)
                    self.lbl_status.configure(text=f"صفحه {done} از {total}: {url}")
                elif kind == "otp":
                    self._ask_otp(item[1], item[2])
                elif kind == "filter":
                    self._show_filter(item[1], item[2])
                elif kind == "done":
                    self._finish(item[1])
        except queue.Empty:
            pass
        except Exception:
            pass
        self.after(120, self._poll)

    # ------------------------------------------------ ساخت تنظیمات از فرم
    def _build_config(self, out_dir):
        site_url = self.e_url.get().strip()
        if site_url and not site_url.startswith(("http://", "https://")):
            site_url = "https://" + site_url
        only_lines = [l.strip() for l in self.t_only.get("1.0", "end").splitlines() if l.strip()]
        pause_on = self.v_pause.get()
        pause_pat = self.e_pause_pat.get().strip() if pause_on else ""
        pause_list = [pause_pat] if pause_pat else (["**"] if pause_on else [])

        def sub(e, default):
            v = e.get().strip() or default
            return os.path.join(out_dir, v)

        cfg = {
            "site": {
                "start_urls": [site_url],
                "login_url": None,
                "username": self.e_user.get().strip(),
                "password": self.e_pass.get(),
                "manual_login": False,
            },
            "crawl": {
                "max_pages": int(float(self.s_maxpages.get() or 500)),
                "max_pages_per_list": int(float(self.s_maxlist.get() or 100)),
                "delay_ms": int(float(self.s_delay.get() or 800)),
                "timeout_ms": 30000,
                "resume": True,
                "only_patterns": only_lines,
                "pause_urls": pause_list,
                "skip_filter_pages": bool(self.v_skipfilter.get()),
            },
            "pagination": {"mode": "auto"},
            "extraction": {
                "save_html": True,
                "save_screenshots": bool(self.v_shots.get()),
                "save_texts": True,
                "create_dataset_tables": True,
                "save_assets": bool(self.v_assets.get()),
                "capture_api_json": True,
                "viewport_width": 1366,
                "viewport_height": 900,
            },
            "export": {"excel": True, "csv": False, "per_page_excel": True},
            "browser": {},
            "output": {
                "db_path": os.path.join(out_dir, "site_data.db"),
                "html_dir": sub(self.e_html, "html"),
                "screenshots_dir": sub(self.e_shots, "screenshots"),
                "assets_dir": sub(self.e_assets, "assets"),
                "excel_path": os.path.join(out_dir, "export.xlsx"),
                "excel_dir": os.path.join(out_dir, "excel-per-page"),
                "session_file": os.path.join(out_dir, "session.json"),
                "log_file": os.path.join(out_dir, "crawl.log"),
            },
        }
        return cfg

    # ------------------------------------------------ شروع / توقف / پایان
    def _start(self):
        if self.crawling:
            return
        site_url = self.e_url.get().strip()
        if not site_url:
            messagebox.showwarning("نقص ورودی", "آدرس سامانه را وارد کنید.")
            return
        out_dir = self.e_out.get().strip() or os.path.join(PROG_DIR, "خروجی")
        try:
            os.makedirs(out_dir, exist_ok=True)
            cfg = self._build_config(out_dir)
            # برای مراجعه بعدی، تنظیمات در پوشه خروجی هم ذخیره می‌شود
            with open(os.path.join(out_dir, "config.json"), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("خطا در تنظیمات", f"تنظیمات ساخته نشد:\n{e}")
            return
        self._save_settings()

        opts = {
            "fresh": bool(self.v_fresh.get()),
            "headed": not bool(self.v_hidden.get()),
            "manual": bool(self.v_manual.get()),
        }
        if self.v_pause.get() and self.v_hidden.get():
            opts["headed"] = True   # توقف فیلتر نیاز به مرورگر مرئی دارد

        self.crawling = True
        self._skip_flag = False
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_skip.configure(state="normal")
        self.lbl_status.configure(text="در حال اجرا...")
        crawler.HOOKS = GuiHooks(self)
        self.worker = threading.Thread(target=self._worker, args=(cfg, out_dir, opts), daemon=True)
        self.worker.start()

    def _worker(self, cfg, out_dir, opts):
        old_stdout = sys.stdout
        sys.stdout = QueueStream(self.msg_q)
        try:
            res = crawler.run_crawl(cfg, base_dir=out_dir, fresh=opts["fresh"],
                                    headed=opts["headed"], manual=opts["manual"])
        except Exception as e:
            res = {"ok": False, "error": "exception", "hint": str(e)}
            self.msg_q.put(("log", traceback.format_exc(limit=4)))
        finally:
            sys.stdout = old_stdout
        self.msg_q.put(("done", res))

    def _stop(self):
        try:
            crawler.HOOKS.stopped = True
            self.lbl_status.configure(text="درخواست توقف ثبت شد — پس از صفحه فعلی (یا پاسخ پنجره باز) متوقف می‌شود...")
        except Exception:
            pass

    def _finish(self, res):
        self.crawling = False
        self._skip_flag = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        try:
            self.btn_skip.configure(state="disabled")
        except Exception:
            pass
        if self._filter_resp is not None:
            self._filter_ans("skip")
        if res.get("ok"):
            self.lbl_status.configure(
                text=f"✔ پایان — {res.get('pages', 0)} صفحه، {res.get('tables', 0)} جدول، "
                     f"{res.get('rows', 0)} ردیف — خروجی‌ها در پوشه خروجی آماده است.")
            self._log("=" * 60)
            self._log(f"پایان موفق: {res.get('pages', 0)} صفحه | {res.get('tables', 0)} جدول | "
                      f"{res.get('rows', 0)} ردیف")
            self._log(f"اکسل کل: {os.path.join(self.e_out.get().strip(), 'export.xlsx')}")
            self._log(f"اکسل هر صفحه: {res.get('excel_dir', '')}")
            messagebox.showinfo("پایان خزش",
                                f"خزش با موفقیت پایان یافت.\n\n"
                                f"صفحات: {res.get('pages', 0)}\nجداول: {res.get('tables', 0)}\n"
                                f"ردیف‌ها: {res.get('rows', 0)}\n\n"
                                f"خروجی‌ها:\n{res.get('excel_dir', '')}\n"
                                f"{res.get('shots_dir', '')}")
        else:
            err_map = {
                "login_failed": "ورود انجام نشد. یوزر/پسورد را بررسی کنید یا «ورود دستی» را انتخاب کنید.",
                "blocked": "دسترسی توسط فایروال سازمانی مسدود شد (راه‌حل‌ها در لاگ آمده است).",
                "cdp_failed": "اتصال به کروم شما برقرار نشد.",
                "no_start_urls": "آدرس سامانه وارد نشده است.",
            }
            msg = err_map.get(res.get("error"), "خطای غیرمنتظره.")
            self.lbl_status.configure(text="✖ " + msg)
            self._log("خطا: " + msg)
            if res.get("hint"):
                self._log("جزئیات: " + str(res["hint"])[:600])
            messagebox.showerror("خزش ناتمام", msg + ("\n\nجزئیات: " + str(res.get("hint", ""))[:400]))


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
