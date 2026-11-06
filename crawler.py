# -*- coding: utf-8 -*-
"""
سایت‌کاو — ابزار خزش هوشمند سایت‌های دارای لاگین
====================================================
این برنامه با مرورگر واقعی کرومیوم (بدون سر) وارد سایت شما می‌شود و:
  ۱) ورود هوشمند: اول از سشن ذخیره‌شده (session.json) استفاده می‌کند؛
     اگر منقضی شده باشد با یوزر/پسوردِ config.json دوباره لاگین می‌کند.
     برای سایت‌های دارای کپچا/پیامک از حالت --manual استفاده کنید.
  ۲) همه صفحات مجاز سایت را پیمایش می‌کند (BFS) و صفحه‌بندی را خودکار تشخیص می‌دهد:
     دکمه «بعدی»، شماره صفحه، پارامتر ?page= و اسکرول بی‌نهایت.
  ۳) از هر صفحه: همه جداول، متن‌ها و تیترها، HTML کامل و اسکرین‌شات را برمی‌دارد.
  ۴) همه داده‌ها را در دیتابیس SQLite ذخیره می‌کند (به‌همراه جدول داده‌ی ساختاریافته).
  ۵) امنیت داده: لینک‌های عملیاتی (حذف/بازیابی/ستاره/ارسال/خروج/...) و مسیرهای ajax
     به‌عنوان صفحه باز نمی‌شوند تا اتفاقاً داده‌ی شما تغییر نکند.
  ۶) ردیف‌های تکراری بین صفحات یک فهرست حذف می‌شوند و داده‌ی همه‌ی صفحات آن فهرست
     حتی با صفحه‌بندی ?page=2 در یک جدول واحد ds_* ادغام می‌شود.
  ۷) پاسخ JSON درخواست‌های AJAX سایت (API واقعی داده) در جدول api_responses ضبط می‌شود.
  ۸) خروجی Excel (export.xlsx) و CSV برای همه جداول داده + ثبت کامل لاگ در فایل.
  ۹) رابط گرافیکی: python crawler_gui.py — ورود آدرس/یوزر/پسورد، انتخاب پوشه خروجی،
     ورود دومعلی (کد پیامکی)، توقف برای اعمال فیلتر، اکسل جداگانه برای هر صفحه.
  ۱۰) جداول و لینک‌های داخل iframe هم برداشت می‌شوند (پنل‌های React/Angular/Vue).

اجرای سریع:
    python crawler_gui.py                 → رابط گرافیکی (پیشنهاد ما)
    python crawler.py                     → اجرای عادی طبق config.json
    python crawler.py --manual            → لاگین دستی در پنجره مرورگر
    python crawler.py --headed            → مرورگر قابل مشاهده
    python crawler.py --login             → لاگین مجدد اجباری (سشن تازه)
    python crawler.py --fresh             → شروع دیتابیس از صفر
    python crawler.py --max-pages 50      → سقف تعداد صفحات
    python crawler.py --export-only       → فقط ساخت خروجی Excel/CSV از دیتابیس موجود
    python crawler.py --cdp               → اتصال به کروم واقعی خودتان (برای فایروال سازمانی)
نکته: این ابزار را فقط روی سامانه‌هایی استفاده کنید که مالک آن هستید یا
مجاز به برداشت داده از آن‌ها هستید.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import deque
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, unquote

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------------------------------------------------------- پیام‌های فارسی
def info(s): print(f"   [i] {s}", flush=True)
def ok(s):   print(f"   [+] {s}", flush=True)
def warn(s): print(f"   [!] {s}", flush=True)
def err(s):  print(f"   [خطا] {s}", flush=True)
def head(s): print("\n" + "=" * 60 + f"\n{s}\n" + "=" * 60, flush=True)

def short(e, n=140):
    return str(e).replace("\n", " ")[:n]

# ---------------------------------------------------------------- تشخیص فایروال سازمانی
BLOCK_TITLE_MARKERS = ("block", "denied", "forbidden", "403")
BLOCK_BODY_MARKERS = ("web page blocked", "attack id", "message id", "access denied",
                      "دسترسی مسدود", "دسترسی شما مسدود", "blocked by")
BLOCK_SOLUTIONS = r"""
   راه‌حل‌ها (به ترتیب امتحان کنید):
   ۱) بهترین راه — استفاده از کروم واقعی خودتان (نشست واقعی مرورگر شما):
      الف) کروم را با این دستور باز کنید (در CMD یا Run):
          "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%TEMP%\cw-profile"
      ب) سپس اجرا کنید:  python crawler.py --cdp
      (اگر لازم شد در همان پنجره کروم دستی وارد شوید و اجرا را با --cdp --manual تکرار کنید)
   ۲) در config.json مقدار browser.channel را روی "chrome" بگذارید
      (از کروم نصب‌شده سیستم استفاده می‌شود؛ برای Edge: "msedge")
   ۳) اجرای:  python crawler.py --manual   (پنجره مرورگر واقعی و قابل مشاهده)
   ۴) اگر شبکه شرکت پروکسی دارد، در config.json تنظیم browser.proxy را پر کنید
   ۵) با مدیر شبکه تماس بگیرید و شماره Attack ID صفحه مسدود را بگویید تا دامنه سایت شما whitelist شود
   بعد از رفع مشکل، یک بار با --fresh اجرا کنید تا صفحه خطای قبلی از دیتابیس پاک شود.
"""

# ---------------------------------------------------------------- قلاب‌های رابط گرافیکی
class UIHooks:
    """پل ارتباطی با رابط گرافیکی؛ در حالت خط فرمان همه تهی هستند.
    ask_otp(text)  → هنگام ورود دومعلی، کد را از کاربر می‌گیرد (رشته یا None)
    filter_pause(url, page) → قبل از برداشت صفحه منتظر «ادامه» یا «رد شدن» کاربر می‌ماند؛
                              پاسخ می‌تواند از رابط گرافیکی یا از دکمه‌های درون مرورگر بیاید
    progress(done, total, url) → پیشرفت خزش را به رابط گرافیکی می‌دهد
    stopped → اگر True شود، خزش پس از صفحه فعلی متوقف می‌شود
    نکته: اعضا attribute کلاس‌اند نه نمونه — تا زیرکلاس‌ها بتوانند متد تعریف کنند"""

    ask_otp = None
    filter_pause = None
    progress = None
    stopped = False

HOOKS = UIHooks()

# پاسخ ویژه‌ی قلاب ask_otp: کاربر خودش کد را در پنجره مرورگر وارد کرده/می‌کند
OTP_IN_BROWSER = "__IN_BROWSER__"

# ---------------------------------------------------------------- ثابت‌ها
NON_HTML_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp", ".tif", ".tiff",
    ".pdf", ".zip", ".rar", ".7z", ".gz", ".tar",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
    ".mp3", ".mp4", ".avi", ".mkv", ".mov", ".wav", ".flv",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".css", ".js", ".json", ".xml", ".rss",
}
TRACK_PARAMS = re.compile(r"^(utm_|fbclid|gclid|msclkid|phpsessid|jsessionid|aspnetsessionid|sid$|sessionid$|_s$)", re.I)

# کلیدهای پارامترِ «عملیات» — URLهایی با چنین پارامتری نباید به‌عنوان صفحه باز شوند
# (در خروجی واقعی دیده شد که ?trash=257 پیام را به سطل زباله می‌برد!)
ACTION_QUERY_KEYS = {
    "trash", "restore", "unstar", "star", "fwd", "repto", "compose",
    "delete", "del", "delid", "remove", "removeid", "erase",
    "logout", "signout", "logoff",
    "activate", "deactivate", "approve", "reject", "confirm",
    "send", "submit", "resend", "cancel",
    "read", "unread", "markread", "seen",
    "download", "export", "print", "pay", "refund",
}
# پارامترهای صفحه‌بندی — برای ادغام داده‌ی صفحات مختلف یک فهرست
PAGE_PARAMS = {"page", "p", "pg", "pagenumber", "pageindex", "pagenum", "start"}

# کلیدواژه‌های صفحه‌های فیلتر/جست‌وجو (کد ملی، کد پرونده، کد رهگیری و ...)
# — این صفحات داده‌ی برداشتنی ندارند؛ پیش‌فرض رد می‌شوند (فقط لینک‌هایشان دنبال می‌شود)
DEFAULT_FILTER_KEYWORDS = [
    "کد ملی", "کدملی", "national code", "nationalcode", "national_id",
    "کد پرونده", "شماره پرونده", "شناسه پرونده", "file number", "case number",
    "کد رهگیری", "کدپیگیری", "کد پیگیری", "شماره پیگیری", "tracking", "follow code",
    "کد پیگیری‌شده",
]
# الگوهای حذف همیشگی (به تنظیمات کاربر اضافه می‌شوند؛ "ajax" جداگانه کنترل می‌شود)
BUILTIN_EXCLUDE = ["logout", "logoff", "signout", "خروج"]

# ---------------------------------------------------------------- قطعه‌کدهای جاوااسکریپت (درون مرورگر اجرا می‌شوند)
# تشخیص فرم لاگین و علامت‌گذاری فیلد نام‌کاربری / رمز / دکمه ورود
JS_DETECT_LOGIN = r"""
() => {
  const vis = el => el && el.getClientRects().length > 0;
  const pws = [...document.querySelectorAll('input[type=password]')].filter(vis);
  if (!pws.length) {
    // ورود موبایل‌محور: صفحه اول فقط یک فیلد (موبایل/کد ملی/ایمیل) + دکمه ورود دارد
    const forms = [...document.querySelectorAll('form')];
    forms.push(document);
    for (const form of forms) {
      const flds = [...form.querySelectorAll('input')].filter(el =>
          !['hidden','checkbox','radio','file','submit','button','image','reset']
            .includes((el.type || 'text').toLowerCase()) && !el.disabled && !el.readOnly && vis(el));
      if (flds.length !== 1) continue;
      const f = flds[0];
      const t = (f.type || 'text').toLowerCase();
      const meta = ((f.name || '') + ' ' + (f.id || '') + ' ' + (f.placeholder || '')).toLowerCase();
      const strong = t === 'tel' || (f.getAttribute('autocomplete') || '') === 'tel'
        || /mobile|phone|موبایل|تلفن همراه|شماره موبایل|کد ملی|کدملی|نام کاربری|شناسه کاربری|ایمیل|username|user[- _]?id|login/.test(meta);
      if (!strong) continue;
      const btns = [...form.querySelectorAll('button, input[type=submit], [role=button]')].filter(vis);
      const submit = btns.find(b => (b.getAttribute('type') || '').toLowerCase() === 'submit')
                   || btns.find(b => b.tagName === 'BUTTON') || btns[0] || null;
      if (!submit) continue;
      const btxt = ((submit.innerText || submit.value || '') + '').toLowerCase();
      if (!/ورود|ثبت|ادامه|دریافت|مرحله|login|sign[- _]?in|continue|send|next|بعدی/.test(btxt)) continue;
      f.setAttribute('data-cw-user', '1');
      submit.setAttribute('data-cw-submit', '1');
      return {hasPassword: false, mobileOnly: true, userMarked: true, submitMarked: true};
    }
    return {hasPassword: false};
  }
  const pw = pws[0];
  const form = pw.closest('form') || document;
  const badT = ['password','hidden','checkbox','radio','file','submit','button','image','reset'];
  const cands = [...form.querySelectorAll('input')].filter(el =>
      !badT.includes((el.type || 'text').toLowerCase()) && !el.disabled && !el.readOnly && vis(el));
  let user = cands.find(el => el.getBoundingClientRect().top <= pw.getBoundingClientRect().top + 2) || cands[0] || null;
  const prefer = cands.find(c =>
      /user|email|login|mobile|username|account|نام|کاربر|ایمیل|موبایل|کد|شناسه|حساب/i
        .test((c.name || '') + (c.id || '') + (c.placeholder || '')));
  if (prefer) user = prefer;
  const btns = [...form.querySelectorAll('button, input[type=submit], [role=button]')].filter(vis);
  let submit = btns.find(b => (b.getAttribute('type') || '').toLowerCase() === 'submit')
             || btns.find(b => b.tagName === 'BUTTON') || btns[0] || null;
  if (user) user.setAttribute('data-cw-user', '1');
  pw.setAttribute('data-cw-pass', '1');
  if (submit) submit.setAttribute('data-cw-submit', '1');
  return {hasPassword: true, userMarked: !!user, submitMarked: !!submit};
}
"""

# یافتن و علامت‌گذاری بهترین دکمه «بعدی / بیشتر»
JS_FIND_NEXT_MARK = r"""
() => {
  const clean = t => (t == null ? '' : String(t)).replace(/[\s\u200c]+/g, ' ').trim();
  const vis = el => {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const NEXT_WORDS = ['next', 'next page', 'older', 'older posts', 'next ›', 'next »',
                      'بعدی', 'بعد', 'صفحه بعد', 'صفحه بعدی', 'گذر به صفحه بعد'];
  const MORE_WORDS = ['load more', 'view more', 'see more', 'show more', 'load more posts',
                      'بیشتر', 'نمایش بیشتر', 'مشاهده بیشتر', 'بارگذاری بیشتر', 'موارد بیشتر'];
  const SYMS = ['>', '>>', '»', '›', '→', '->', '▶', '▸'];
  const els = Array.from(document.querySelectorAll('a, button, input[type=submit], [role=button]'));
  let best = null, bestScore = 0;
  els.forEach(el => {
    const txt = clean(el.innerText || el.value || '').toLowerCase();
    const title = clean((el.getAttribute('title') || '') + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase();
    const rel = (el.getAttribute('rel') || '').toLowerCase();
    const cls = (typeof el.className === 'string' ? el.className : '').toLowerCase();
    const id = (el.id || '').toLowerCase();
    let s = 0;
    if (rel === 'next') s += 12;
    if (NEXT_WORDS.indexOf(txt) >= 0) s += 10;
    else if (MORE_WORDS.indexOf(txt) >= 0) s += 8;
    else if (SYMS.indexOf(txt) >= 0) s += 6;
    if (/(^|[^a-z])(next|nextpage|pagedown|pagination-next|btn-next|lbtnnext)([^a-z]|$)/.test(cls + ' ' + id)) s += 6;
    if (title.indexOf('next') >= 0 || title.indexOf('بعد') >= 0) s += 6;
    if (s <= 0) return;
    if (el.disabled || el.getAttribute('aria-disabled') === 'true' ||
        el.closest('.disabled, [disabled], [aria-disabled="true"], li.disabled, a.disabled')) s = -1;
    if (!vis(el)) s = -1;
    if (s > bestScore) { bestScore = s; best = el; }
  });
  if (best && bestScore >= 5) {
    best.setAttribute('data-cw-next', '1');
    return {found: true, score: bestScore, text: clean(best.innerText || best.value || '').slice(0, 40)};
  }
  return {found: false};
}
"""

# لینک‌های شماره صفحه (۱، ۲، ۳ ...)
JS_NUMBERED = r"""
() => Array.from(document.querySelectorAll('a[href]'))
      .map(a => ({href: a.href, t: (a.innerText || '').trim()}))
      .filter(x => /^[0-9]{1,4}$/.test(x.t) && x.href && x.href.indexOf('javascript:') !== 0)
"""

# استخراج همه جداول مرئی صفحه
JS_TABLES = r"""
() => {
  const clean = t => (t == null ? '' : String(t)).replace(/[\s\u200c]+/g, ' ').trim();
  const vis = el => {
    const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && el.getClientRects().length > 0;
  };
  const out = [];
  document.querySelectorAll('table').forEach(tb => {
    if (tb.parentElement && tb.parentElement.closest('table')) return;
    if (!vis(tb)) return;
    const rows = Array.from(tb.rows).map(tr => Array.from(tr.cells).map(c => clean(c.innerText)));
    if (!rows.length) return;
    let headers = null, hidx = -1;
    if (tb.tHead && tb.tHead.rows.length) {
      headers = Array.from(tb.tHead.rows[0].cells).map(c => clean(c.innerText));
      hidx = 0;
    } else {
      for (let i = 0; i < rows.length; i++) {
        const tr = tb.rows[i];
        const ths = Array.from(tr.cells).filter(c => c.tagName === 'TH');
        if (ths.length && ths.length === tr.cells.length && rows[i].some(x => x !== '')) {
          headers = rows[i]; hidx = i; break;
        }
      }
    }
    const dataRows = hidx >= 0 ? rows.slice(hidx + 1) : rows;
    if (!dataRows.length) return;
    const cap = tb.caption ? clean(tb.caption.innerText)
              : (tb.getAttribute('aria-label') || tb.id || '');
    out.push({caption: cap, headers: headers, rows: dataRows.slice(0, 5000)});
  });
  return out;
}
"""

# استخراج متن‌ها و تیترهای اصلی صفحه
JS_TEXTS = r"""
() => {
  const clean = t => (t == null ? '' : String(t)).replace(/[\s\u200c]+/g, ' ').trim();
  const vis = el => {
    const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden';
  };
  const out = [];
  const push = (k, el) => {
    const t = clean(el.innerText);
    if (t.length >= 2 && t.length <= 3000) out.push({k: k, t: t});
  };
  document.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach(h => { if (vis(h)) push('h' + h.tagName.substring(1), h); });
  document.querySelectorAll('p').forEach(p => { if (vis(p) && !p.querySelector('p')) push('p', p); });
  document.querySelectorAll('li').forEach(li => {
    if (!vis(li)) return;
    if (li.querySelector('li') || li.querySelector('table')) return;
    const kids = [...li.children].filter(c => c.tagName !== 'UL' && c.tagName !== 'OL');
    if (kids.length === 1 && kids[0].tagName === 'A') return;
    if (li.innerText.length < 500) push('li', li);
  });
  const md = document.querySelector('meta[name="description"]');
  if (md && md.content) out.unshift({k: 'meta', t: clean(md.content)});
  return out.slice(0, 600);
}
"""

JS_LINKS = r"""
() => Array.from(document.querySelectorAll('a[href]'))
      .map(a => ({href: a.href, text: ((a.innerText || a.title || '').replace(/[\s\u200c]+/g, ' ').trim()).slice(0, 120)}))
"""

# فایل‌های ظاهری صفحه برای ذخیره: CSS، جاوااسکریپت، تصاویر + بلوک‌های درون‌خطی
JS_ASSETS = r"""
() => {
  const out = [];
  const seen = new Set();
  const add = (u, kind) => { if (u && !seen.has(u)) { seen.add(u); out.push({url: u, kind: kind}); } };
  document.querySelectorAll('link[rel~="stylesheet"][href]').forEach(l => add(l.href, 'css'));
  document.querySelectorAll('link[rel*="icon"][href]').forEach(l => add(l.href, 'img'));
  document.querySelectorAll('script[src]').forEach(s => add(s.src, 'js'));
  document.querySelectorAll('img[src]').forEach(i => add(i.src, 'img'));
  document.querySelectorAll('style').forEach((s, i) => {
    if (s.textContent && s.textContent.length > 10) out.push({inline: s.textContent, kind: 'css', idx: i});
  });
  document.querySelectorAll('script:not([src])').forEach((s, i) => {
    if (s.textContent && s.textContent.length > 10 && s.textContent.length < 300000)
      out.push({inline: s.textContent, kind: 'js', idx: i});
  });
  return out.slice(0, 120);
}
"""

# تشخیص فیلد کد تأیید (مرحله دوم ورود دومعلی) — فقط وقتی فرم رمز مرئی نیست
# سخت‌گیرانه: واژه‌ی کلی «code» تنها کافی نیست (کد ملی/کد پستی اشتباه گرفته نمی‌شود)
JS_OTP_FIELD = r"""
() => {
  const vis = el => el && el.getClientRects().length > 0 && !el.disabled && !el.readOnly;
  const pws = [...document.querySelectorAll('input[type=password]')].filter(vis);
  if (pws.length) return {found: false};   // هنوز در فرم اول (رمز) هستیم
  const NEG = /پستی|postal|zip|ملی|national|تخفیف|discount|پیگیری|tracking|سریال|serial|پروژه|project|اقتصادی|economic|شهر|کشور/i;
  const POS = /otp|one[- _]?time|verification|verify|confirm[- _]?code|verification[- _]?code|sms[- _]?code|رمز\s*یکبار|رمز\s*یک\s*بار|کد\s*تأیید|کد\s*تایید|کد\s*پیامکی|کد\s*فعال\s*سازی|کد\s*فعالسازی|کد\s*امنیت|تایید\s*پیامکی|تأیید\s*پیامکی/i;
  const MILD = /کد|code/i;
  const badT = ['hidden','checkbox','radio','file','submit','button','image','reset'];
  const cands = [...document.querySelectorAll('input')].filter(el => {
    if (!vis(el)) return false;
    const t = (el.type || 'text').toLowerCase();
    if (badT.includes(t)) return false;
    if (el.hasAttribute('data-cw-user')) return false;   // خود فیلد موبایل صفحه اول
    const meta = ((el.name || '') + ' ' + (el.id || '') + ' ' + (el.placeholder || '') + ' '
                  + (el.getAttribute('autocomplete') || '') + ' '
                  + (el.getAttribute('aria-label') || '')).toLowerCase();
    if (NEG.test(meta)) return false;
    if ((el.getAttribute('autocomplete') || '') === 'one-time-code') return true;
    const numeric = el.getAttribute('inputmode') === 'numeric'
                  || t === 'tel'
                  || /[\d۰-۹]/.test(el.getAttribute('pattern') || '');
    if (POS.test(meta)) return true;
    return MILD.test(meta) && numeric;   // «کد/code» فقط اگر فیلد عددی باشد
  });
  // جعبه‌های رقم‌به‌رقم (هر جعبه maxlength=1) بدون نامِ otp هم باید شناسایی شوند
  const boxes = [...document.querySelectorAll('input')].filter(el =>
    vis(el) && el.getAttribute('maxlength') === '1' && !badT.includes((el.type || 'text').toLowerCase()));
  if (!cands.length && boxes.length < 3) return {found: false};
  // باید شبیه صفحه کد باشد: ورودی‌های متنی کم + دکمه‌ای با متن تایید/ورود
  const textish = [...document.querySelectorAll('input')].filter(el =>
    vis(el) && !badT.includes((el.type || 'text').toLowerCase()));
  if (textish.length > 6) return {found: false};
  const el = cands.length ? cands[0] : boxes[0];
  el.setAttribute('data-cw-otp', '1');
  const form = el.closest('form') || document;
  const btns = [...form.querySelectorAll('button, input[type=submit], [role=button]')].filter(vis);
  let submit = btns.find(b => (b.getAttribute('type') || '').toLowerCase() === 'submit')
             || btns.find(b => b.tagName === 'BUTTON') || btns[0] || null;
  const btnText = submit ? ((submit.innerText || submit.value || '') + '') : '';
  if (!/تایید|تأیید|ورود|ثبت|ادامه|دریافت|بررسی|confirm|verify|login|continue|submit|send|check|ok/i.test(btnText))
    return {found: false};
  if (submit) submit.setAttribute('data-cw-otp-submit', '1');
  return {found: true, type: el.type || 'text', name: el.name || el.id || '', boxes: boxes.length};
}
"""

# تعداد جعبه‌های تکی کد (یک رقم در هر جعبه)
JS_OTP_BOXES = r"""
() => [...document.querySelectorAll('input')]
      .filter(el => el.getClientRects().length > 0 && !el.disabled && !el.readOnly
                    && (el.getAttribute('maxlength') === '1' || el.getAttribute('size') === '1'))
      .length
"""

# پخش ارقام کد بین جعبه‌ها (سازگار با React/Vue با ست‌کننده بومی مقدار)
JS_OTP_FILL = r"""
(code) => {
  const vis = el => el && el.getClientRects().length > 0 && !el.disabled && !el.readOnly;
  let boxes = [...document.querySelectorAll('input')]
    .filter(el => vis(el) && (el.getAttribute('maxlength') === '1' || el.getAttribute('size') === '1'));
  if (!boxes.length) boxes = [...document.querySelectorAll('[data-cw-otp]')];
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  const setv = (el, v) => {
    try { el.focus(); } catch (e) {}
    setter.call(el, v);
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
  };
  if (boxes.length >= code.length) boxes.slice(0, code.length).forEach((el, i) => setv(el, code[i]));
  else if (boxes.length) setv(boxes[0], code);
  return boxes.length;
}
"""

JS_SCROLL_BOTTOM = "() => { window.scrollTo(0, document.body.scrollHeight); }"
JS_SCROLL_TOP = "() => { window.scrollTo(0, 0); }"
JS_SCROLL_METRICS = r"""
() => ({
  h: Math.max(document.body ? document.body.scrollHeight : 0,
              document.documentElement ? document.documentElement.scrollHeight : 0),
  vh: window.innerHeight || 0,
  items: document.querySelectorAll('table tr, ul li, ol li, article, div[class*=item], div[class*=card]').length
})
"""
JS_PAGE_SIG = "() => (document.body ? document.body.innerText : '').slice(0, 20000)"
JS_PAGE_META = "() => ({title: document.title || '', len: (document.body ? document.body.innerText : '').length})"
JS_BLOCK_SNIPPET = "() => (document.body ? document.body.innerText : '').slice(0, 3000)"
JS_UNMARK = "() => { document.querySelectorAll('[data-cw-next]').forEach(e => e.removeAttribute('data-cw-next')); }"

# امضای ردیف‌های جدول — تشخیص اینکه کلیک «بعدی» داده‌ی تازه آورده یا محتوای تکراری
JS_ROWS_SIG = r"""
() => {
  const clean = t => (t == null ? '' : String(t)).replace(/[\s\u200c]+/g, ' ').trim();
  const parts = [];
  document.querySelectorAll('table').forEach(tb => {
    if (tb.parentElement && tb.parentElement.closest('table')) return;
    const s = getComputedStyle(tb);
    if (s.display === 'none' || s.visibility === 'hidden') return;
    Array.from(tb.rows).forEach(tr => {
      if (!tr.getClientRects().length) return;   // ردیف پنهان (صفحه‌بندی درونی) نباید شمرده شود
      const cells = Array.from(tr.cells).map(c => clean(c.innerText));
      if (cells.some(x => x !== '')) parts.push(cells.join('|'));
    });
  });
  return parts.join('\n').slice(0, 500000);
}
"""

# کلیک جایگزین با رویدادهای جاوااسکریپت — وقتی کلیک عادی روی دکمه timeout می‌خورد
JS_CLICK_NEXT = r"""
(el) => {
  if (!el) return false;
  try { el.scrollIntoView({block: 'center'}); } catch (e) {}
  const r = el.getBoundingClientRect();
  const opts = {bubbles: true, cancelable: true, view: window,
                clientX: r.left + r.width / 2, clientY: r.top + r.height / 2};
  ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(t => {
    try {
      if (t.indexOf('pointer') === 0 && window.PointerEvent) el.dispatchEvent(new PointerEvent(t, opts));
      else el.dispatchEvent(new MouseEvent(t, opts));
    } catch (e) {}
  });
  if (typeof el.click === 'function') { try { el.click(); } catch (e) {} }
  return true;
}
"""

# ---------------------------------------------------------------- ابزارهای URL
def norm(u):
    """نرمال‌سازی URL برای یکتاسازی؛ اگر تنها پارامتر صفحه page=1 باشد حذف می‌شود"""
    try:
        p = urlsplit(u)
        scheme = p.scheme.lower()
        host = p.netloc.lower()
        path = p.path or "/"
        if path != "/":
            path = path.rstrip("/") or "/"
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACK_PARAMS.match(k)]
        if len(q) == 1 and q[0][0].lower() in ("page", "p", "pg", "pagenumber", "pageindex") and q[0][1] == "1":
            q = []
        q.sort()
        return urlunsplit((scheme, host, path, urlencode(q), ""))
    except Exception:
        return u

def pag_base(u):
    """URL پایه برای ادغام داده‌ی صفحات مختلف یک فهرست:
    پارامتر صفحه‌ی عددی (?page=2 و امثالش) حذف می‌شود تا جدول ds_* یکی شود"""
    try:
        p = urlsplit(u)
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not (k.lower() in PAGE_PARAMS and (v.strip() == "" or v.strip().isdigit()))]
        q.sort()
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", urlencode(q), ""))
    except Exception:
        return u

def dirbase(u):
    """پوشه پایه URL برای تشخیص لینک‌های شماره صفحه هم‌خانواده"""
    return urlsplit(u).path.rsplit("/", 1)[0]

def page_slug(url):
    """اسلاگ یکتای هر صفحه (برای نام فایل اکسل و پوشه assets) — سازگار با ویندوز"""
    p = urlsplit(url)
    seg = [s for s in (p.path or "").split("/") if s]
    slug = re.sub(r"[^\w\u0600-\u06FF-]", "", seg[-1] if seg else "page")[:32] or "page"
    if seg and seg[-1].isdigit() and len(seg) >= 2:
        # مثلا detail/2 → detail-2 (خواناتر)
        parent = re.sub(r"[^\w\u0600-\u06FF-]", "", seg[-2])[:24]
        slug = f"{parent}-{seg[-1]}" if parent else slug
    h = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{h}"

def fname_for(url, ext):
    """نام فایل یکتا از روی URL (اسلاگ + هش) — سازگار با ویندوز"""
    return page_slug(url) + ext

def _clean_ident(s):
    s = re.sub(r"[\s\u200c]+", "_", str(s).strip())
    s = re.sub(r"[^\w\u0600-\u06FF]", "", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s

def col_names(headers, ncols):
    """ساخت نام ستون‌های یکتا از روی هدر جدول"""
    cols, seen = [], {}
    for i in range(ncols):
        h = headers[i] if headers and i < len(headers) else ""
        name = _clean_ident(h)[:48] or f"col_{i+1}"
        if name[0].isdigit():
            name = "c_" + name
        k = seen.get(name, 0) + 1
        seen[name] = k
        if k > 1:
            name = f"{name}_{k}"
        cols.append(name)
    return cols

def with_param(url, key, val):
    p = urlsplit(url)
    q = dict(parse_qsl(p.query, keep_blank_values=True))
    q[key] = val
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))

# ---------------------------------------------------------------- دیتابیس
DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    page_state INTEGER NOT NULL DEFAULT 0,
    title TEXT,
    crawled_at TEXT,
    http_status INTEGER,
    html_file TEXT,
    screenshot_file TEXT,
    pagination_info TEXT,
    n_tables INTEGER DEFAULT 0,
    n_texts INTEGER DEFAULT 0,
    UNIQUE(url, page_state)
);
CREATE TABLE IF NOT EXISTS page_texts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL,
    kind TEXT,
    content TEXT
);
CREATE TABLE IF NOT EXISTS html_tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL,
    table_index INTEGER,
    caption TEXT,
    headers_json TEXT,
    n_rows INTEGER,
    n_cols INTEGER,
    dataset_table TEXT
);
CREATE TABLE IF NOT EXISTS table_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id INTEGER NOT NULL,
    row_index INTEGER,
    data_json TEXT
);
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL,
    url TEXT,
    text TEXT
);
CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sqlite_table TEXT UNIQUE,
    source_url TEXT,
    table_index INTEGER,
    headers_json TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS api_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    page_url TEXT,
    method TEXT,
    url TEXT,
    status INTEGER,
    content_type TEXT,
    body TEXT
);
CREATE TABLE IF NOT EXISTS crawl_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    level TEXT,
    message TEXT
);
"""

def db_get_page(db, url, page_state):
    return db.execute("SELECT id FROM pages WHERE url=? AND page_state=?", (url, page_state)).fetchone()

def db_insert_page(db, url, page_state, title, http_status, html_file, shot_file, pag_info, n_tables, n_texts):
    row = db_get_page(db, url, page_state)
    if row:
        return row[0]
    cur = db.execute(
        "INSERT INTO pages(url, page_state, title, crawled_at, http_status, html_file, screenshot_file,"
        " pagination_info, n_tables, n_texts) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (url, page_state, title, datetime.now().isoformat(timespec="seconds"),
         http_status, html_file, shot_file, pag_info, n_tables, n_texts))
    return cur.lastrowid

def db_log(db, level, message):
    try:
        db.execute("INSERT INTO crawl_log(ts, level, message) VALUES (?,?,?)",
                   (datetime.now().isoformat(timespec="seconds"), level, message[:500]))
        db.commit()
    except Exception:
        pass

# ---------------------------------------------------------------- وضعیت مشترک اجرا
class State:
    def __init__(self, cfg, db, base_dir):
        self.cfg = cfg
        self.db = db
        self.base_dir = base_dir
        crawl = cfg.get("crawl", {})
        ex = cfg.get("extraction", {})
        pg = cfg.get("pagination", {})
        self.delay = max(0, int(crawl.get("delay_ms", 700))) / 1000.0
        self.timeout = int(crawl.get("timeout_ms", 30000))
        self.max_pages = int(crawl.get("max_pages", 200))
        self.max_list_pages = int(crawl.get("max_pages_per_list", 100))
        # «فقط این صفحات»: اگر پر باشد، فقط URLهایی که یکی از این عبارت‌ها را دارند خزیده می‌شوند
        self.only_patterns = [str(x).strip().lower() for x in (crawl.get("only_patterns") or []) if str(x).strip()]
        # «توقف برای فیلتر»: صفحاتی که قبل از برداشت، کاربر باید فیلترها را در مرورگر اعمال کند
        self.pause_urls = [str(x).strip() for x in (crawl.get("pause_urls") or []) if str(x).strip()]
        # «رد شدن از صفحات فیلتر» (کد ملی/پرونده/رهگیری): فقط لینک‌هایشان دنبال می‌شود، داده ذخیره نمی‌شود
        self.skip_filter_pages = bool(crawl.get("skip_filter_pages", False))
        kw = crawl.get("filter_keywords")
        self.filter_keywords = [str(x) for x in kw] if kw else list(DEFAULT_FILTER_KEYWORDS)
        self.n_filter_skip = 0
        self.exclude = [p for p in crawl.get("exclude_patterns", []) if p] + list(BUILTIN_EXCLUDE)
        if not crawl.get("exclude_ajax", True):
            self.exclude = [p for p in self.exclude if p != "ajax"]
        # اگر کاربر کلیدهای عملیاتی سفارشی داده باشد، جای پیش‌فرض را می‌گیرد
        ak = crawl.get("action_query_keys")
        self.action_keys = set(ak) if ak else set(ACTION_QUERY_KEYS)
        self.stay_prefix = crawl.get("stay_in_prefix")
        self.include_subdomains = bool(crawl.get("include_subdomains", False))
        self.scroll_wait = max(0.3, int(pg.get("scroll_wait_ms", 1000)) / 1000.0)
        self.max_scrolls = int(pg.get("max_scrolls", 80))
        self.save_html = bool(ex.get("save_html", True))
        self.save_shots = bool(ex.get("save_screenshots", True))
        self.save_texts = bool(ex.get("save_texts", True))
        # ذخیره CSS/JS/تصاویر و قالب هر صفحه
        self.save_assets = bool(ex.get("save_assets", True))
        self.max_assets = max(1, int(ex.get("max_assets_per_page", 40)))
        self.datasets_on = bool(ex.get("create_dataset_tables", True))
        self.save_variant_html = bool(ex.get("save_variant_html", False))
        self.api_on = bool(ex.get("capture_api_json", True))
        self.api_body_max = max(4, int(ex.get("max_api_body_kb", 200)))
        self.api_max = max(1, int(ex.get("max_api_records", 400)))
        exx = cfg.get("export", {})
        self.export_excel = bool(exx.get("excel", True))
        self.export_csv = bool(exx.get("csv", True))
        # اکسل جداگانه به نام هر صفحه
        self.per_page_excel = bool(exx.get("per_page_excel", True))
        out = cfg.get("output", {})
        self.html_dir = os.path.join(base_dir, out.get("html_dir", "output/html"))
        self.shot_dir = os.path.join(base_dir, out.get("screenshots_dir", "output/screenshots"))
        self.assets_dir = os.path.join(base_dir, out.get("assets_dir", "output/assets"))
        self.excel_dir = os.path.join(base_dir, out.get("excel_dir", "output/excel"))
        os.makedirs(self.html_dir, exist_ok=True)
        os.makedirs(self.shot_dir, exist_ok=True)
        os.makedirs(self.assets_dir, exist_ok=True)
        self.visited = set()
        self.enqueued = set()
        self.ds_used = set()
        self.ds_map = {}   # نگاشت (URL پایه، شماره جدول) ← نام جدول دیتابیس
        self.ds_rows = {}  # هش ردیف‌های هر ds_* برای حذف تکراری‌ها
        self.ds_cols = {}  # نام ستون‌های هر ds_* (برای صفحات بعدی فهرست)
        self.api_seen = set()
        self.n_api = 0
        self.n_ds_dup = 0
        self.n_action_skip = 0
        self.queue = deque()
        self.enqueue = lambda u: None   # در run() جایگزین می‌شود
        self.manual_login = False
        self.headless = True
        self.cdp_mode = False
        self.n_blocked = 0
        self.n_stored = 0
        self.db_path = ""
        self.cli_start_url = None
        self.extra_starts = []   # صفحه‌ای که سامانه پس از ورود به آن منتقل می‌شود (مثلا داشبورد)
        self.host = ""
        self.start_urls = []
        self.abort_reason = None

    def matches_only(self, nu):
        """آیا این URL طبق «فقط این صفحات» کاربر مجاز است؟ (بدون الگو = همه)"""
        if not self.only_patterns:
            return True
        low = unquote(nu).lower()
        return any(pat == "**" or pat in low for pat in self.only_patterns)

    def allowed_target(self, nu):
        try:
            p = urlsplit(nu)
        except Exception:
            return False
        if p.scheme not in ("http", "https"):
            return False
        host = p.netloc.lower()
        if host != self.host and not (self.include_subdomains and host.endswith("." + self.host)):
            return False
        low = unquote(nu).lower()
        for pat in self.exclude:
            try:
                if re.search(pat, low, re.I):
                    return False
            except re.error:
                if pat.lower() in low:
                    return False
        ext = os.path.splitext(p.path)[1].lower()
        if ext and ext in NON_HTML_EXT:
            return False
        # لینک‌های عملیاتی (حذف/بازیابی/ارسال/…) — باز کردنشان داده را تغییر می‌دهد
        try:
            qs = parse_qsl(p.query, keep_blank_values=True)
        except Exception:
            qs = []
        for k, _v in qs:
            if k.lower() in self.action_keys:
                self.n_action_skip += 1
                return False
        # مسیرهای ajax: قطعه‌ی صفحه‌اند نه صفحه کامل (اگر exclude_ajax روشن باشد)
        if "/ajax" in (p.path or "").lower() and self.exclude_ajax:
            self.n_action_skip += 1
            return False
        if self.stay_prefix:
            pref = self.stay_prefix.rstrip("/") or ""
            path = p.path or "/"
            if pref and not path.startswith(pref):
                return False
        # فقط صفحاتی که کاربر خواسته است (عبارت داخل آدرس؛ "**" یعنی همه)
        return self.matches_only(nu)

# ---------------------------------------------------------------- توابع کمکی مرورگر
def goto(page, url, timeout_ms, attempts=3):
    last = None
    for i in range(attempts):
        try:
            resp = page.goto(url, timeout=timeout_ms, wait_until="load")
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            return resp
        except PWTimeout:
            last = f"وقت‌گذرانی در باز شدن صفحه (تلاش {i+1} از {attempts})"
            warn(last)
        except Exception as e:
            last = e
            warn(f"خطا در باز شدن صفحه: {short(e)}")
        time.sleep(1.0)
    if last:
        err(f"صفحه باز نشد: {short(last)}")
    return None

def page_status(resp):
    try:
        return resp.status if resp else None
    except Exception:
        return None

def is_valid_http(url):
    return bool(url) and url.startswith(("http://", "https://"))

def page_sig(page):
    try:
        s = page.evaluate(JS_PAGE_SIG)
        return hashlib.md5((s or "").encode("utf-8")).hexdigest()
    except Exception:
        return None

def rows_sig(page):
    """امضای ردیف‌های جدول فعلی صفحه — برای توقف هوشمند صفحه‌بندی"""
    try:
        s = page.evaluate(JS_ROWS_SIG) or ""
        return hashlib.md5(s.encode("utf-8")).hexdigest()
    except Exception:
        return None

def scroll_metrics(page):
    try:
        return page.evaluate(JS_SCROLL_METRICS)
    except Exception:
        return None

def looks_error(page):
    try:
        m = page.evaluate(JS_PAGE_META)
        return (m.get("len", 0) < 40) or bool(re.search(r"404|not found|error", (m.get("title") or ""), re.I))
    except Exception:
        return False

def is_login_page(page):
    """فرم ورود: یا رمز + نام‌کاربری، یا فرم موبایل‌محور (ورود دومعلی، مرحله اول)"""
    try:
        d = page.evaluate(JS_DETECT_LOGIN)
        if not d or not d.get("userMarked"):
            return False
        return bool(d.get("hasPassword") or d.get("mobileOnly"))
    except Exception:
        return False

def is_block_page(page):
    """تشخیص صفحه مسدودِ فایروال/فیلتر سازمانی (مثل FortiGate) — چنین صفحه‌ای ذخیره نمی‌شود"""
    try:
        m = page.evaluate(JS_PAGE_META)
        title = (m.get("title") or "").lower()
        if any(k in title for k in BLOCK_TITLE_MARKERS):
            return True
        body = (page.evaluate(JS_BLOCK_SNIPPET) or "").lower()
        return any(k in body for k in BLOCK_BODY_MARKERS)
    except Exception:
        return False

# ---------------------------------------------------------------- ورود (لاگین)
def _save_session(ctx, st):
    try:
        sess = os.path.join(st.base_dir, st.cfg.get("output", {}).get("session_file", "session.json"))
        ctx.storage_state(path=sess)
        ok(f"سشن ذخیره شد: {sess}")
    except Exception as e:
        warn(f"ذخیره سشن ناموفق بود: {short(e)}")

def _detect_on(page):
    try:
        return page.evaluate(JS_DETECT_LOGIN) or {}
    except Exception:
        return {}

def _submit_login_form(page, det, user, passw, site):
    """پر کردن و ارسال فرم ورود — هم حالت رمز و هم حالت موبایل‌محور"""
    us, ps, ss = site.get("username_selector"), site.get("password_selector"), site.get("submit_selector")
    try:
        if det.get("hasPassword"):
            if us and ps:
                page.fill(us, user, timeout=8000)
                page.fill(ps, passw, timeout=8000)
                if ss:
                    page.click(ss, timeout=8000)
                else:
                    page.press(ps, "Enter")
            else:
                if det.get("userMarked"):
                    page.fill("[data-cw-user]", user, timeout=8000)
                page.fill("[data-cw-pass]", passw, timeout=8000)
                if det.get("submitMarked"):
                    try:
                        page.click("[data-cw-submit]", timeout=6000)
                    except Exception:
                        page.press("[data-cw-pass]", "Enter")
                else:
                    page.press("[data-cw-pass]", "Enter")
        else:
            # ورود موبایل‌محور: فقط شماره موبایل/نام کاربری — کد در مرحله بعد گرفته می‌شود
            if us:
                page.fill(us, user, timeout=8000)
            else:
                page.fill("[data-cw-user]", user, timeout=8000)
            if ss:
                page.click(ss, timeout=8000)
            elif det.get("submitMarked"):
                try:
                    page.click("[data-cw-submit]", timeout=6000)
                except Exception:
                    page.press("[data-cw-user]", "Enter")
            else:
                page.press("[data-cw-user]", "Enter")
        return True
    except Exception as e:
        warn(f"خطا در پر کردن فرم ورود: {short(e)}")
        return False

def _wait_after_submit(page, site, wait_s):
    """پس از ثبت فرم ورود: منتظر موفقیت یا ظاهر شدن مرحله کد می‌مانیم.
    خروجی: ok (وارد شدیم) | otp (صفحه کد) | fail"""
    ind = site.get("login_success_indicator")
    deadline = time.time() + max(5, wait_s)
    while time.time() < deadline:
        try:
            if page.is_closed():
                return "fail"
        except Exception:
            return "fail"
        if ind:
            try:
                page.wait_for_selector(ind, timeout=500)
                return "ok"
            except Exception:
                pass
        try:
            # اول کد دومعلی چک می‌شود (صفحه کد دیگر فرم ورود ندارد)
            otp = page.evaluate(JS_OTP_FIELD)
            if otp and otp.get("found"):
                return "otp"
            det = _detect_on(page)
            if not det.get("userMarked"):
                return "ok"   # دیگر فرم ورود نیست = وارد شدیم
        except Exception:
            pass
        time.sleep(0.5)
    # پایان مهلت: اگر همچنان صفحه کد باز است «otp» برگردانیم تا به‌جای تلاش کور، کد جدید پرسیده شود
    try:
        otp = page.evaluate(JS_OTP_FIELD)
        if otp and otp.get("found"):
            return "otp"
    except Exception:
        pass
    try:
        det = _detect_on(page)
        if not det.get("userMarked"):
            return "ok"
    except Exception:
        pass
    return "fail"

# کلیک جاوااسکریپتی روی دکمه ثبت کد — وقتی کلیک عادی روی SPA کار نمی‌کند
JS_CLICK_OTP_SUBMIT = r"""
() => {
  const b = document.querySelector('[data-cw-otp-submit]');
  if (!b) return false;
  try { b.scrollIntoView({block: 'center'}); } catch (e) {}
  const r = b.getBoundingClientRect();
  const o = {bubbles: true, cancelable: true, view: window,
             clientX: r.left + r.width / 2, clientY: r.top + r.height / 2};
  ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(t => {
    try {
      if (t.indexOf('pointer') === 0 && window.PointerEvent) b.dispatchEvent(new PointerEvent(t, o));
      else b.dispatchEvent(new MouseEvent(t, o));
    } catch (e) {}
  });
  try { b.click(); } catch (e) {}
  return true;
}
"""

# ---------------------------------------------------------------- صفحات فیلتر/جست‌وجو (کد ملی، پرونده، رهگیری)
# تشخیص: فیلد مرئی با کلیدواژه فیلتر + دکمه ثبت/جست‌وجو + بدون جدول داده‌ای معنادار
JS_FILTER_PAGE = r"""
(kws) => {
  const vis = el => el && el.getClientRects().length > 0 && !el.disabled && !el.readOnly;
  // جدول داده‌ای معنادار: جدول مرئی با حداقل ۲ ردیف پُر
  let dataTables = 0;
  document.querySelectorAll('table').forEach(tb => {
    if (tb.parentElement && tb.parentElement.closest('table')) return;
    const s = getComputedStyle(tb);
    if (s.display === 'none' || s.visibility === 'hidden') return;
    let rows = 0;
    Array.from(tb.rows).forEach(tr => {
      if (!tr.getClientRects().length) return;
      const cells = Array.from(tr.cells).filter(c => (c.innerText || '').trim() !== '');
      if (cells.length >= 2) rows++;
    });
    if (rows >= 2) dataTables++;
  });
  if (dataTables > 0) return {found: false};   // جدول داده دارد؛ صفحه فیلتر خالی نیست
  const badT = ['hidden','checkbox','radio','file','submit','button','image','reset'];
  for (const el of document.querySelectorAll('input, textarea, select')) {
    if (!vis(el)) continue;
    const t = (el.type || 'text').toLowerCase();
    if (badT.includes(t)) continue;
    let label = '';
    try {
      if (el.labels && el.labels.length) label = el.labels[0].innerText || '';
    } catch (e) {}
    const meta = ((el.name || '') + ' ' + (el.id || '') + ' ' + (el.placeholder || '') + ' '
                  + (el.getAttribute('aria-label') || '') + ' ' + label).toLowerCase();
    const hit = (kws || []).find(k => meta.includes(String(k).toLowerCase()));
    if (!hit) continue;
    // دکمه ثبت/جست‌وجو در همان فرم یا نزدیک فیلد
    const form = el.closest('form') || el.parentElement;
    const btns = [...(form ? form.querySelectorAll('button, input[type=submit], [role=button], a.btn') : [])]
                 .filter(vis);
    const okBtn = btns.some(b => /ثبت|جستجو|جست‌وجو|تایید|تأیید|بررسی|نمایش|استعلام|مشاهده|ادامه|search|submit|find|ok/i
                       .test((b.innerText || b.value || '') + ''));
    if (!okBtn) continue;
    return {found: true, kind: hit};
  }
  return {found: false};
}
"""

# نوار شناور درون مرورگر: دکمه‌های «ادامه» و «رد کردن این صفحه» هنگام توقف فیلتر
JS_PAUSE_OVERLAY = r"""
() => {
  if (document.getElementById('__cw-pause-bar')) return true;
  const bar = document.createElement('div');
  bar.id = '__cw-pause-bar';
  bar.style.cssText = 'position:fixed;bottom:18px;left:18px;z-index:2147483647;direction:rtl;'
    + 'font-family:Tahoma,Vazirmatn,sans-serif;background:#ffffff;border:2px solid #0a6b2d;'
    + 'border-radius:12px;padding:10px 14px;box-shadow:0 6px 20px rgba(0,0,0,.28);'
    + 'display:flex;gap:8px;align-items:center;';
  bar.innerHTML = '<span style="font-size:12px;color:#333;font-weight:bold">⏸ منتظر تصمیم شما:</span>'
    + '<button id="__cw-btn-continue" style="background:#0a6b2d;color:#fff;border:0;border-radius:8px;'
    + 'padding:7px 14px;font-family:Tahoma;font-size:12px;cursor:pointer">✔ ادامه بده</button>'
    + '<button id="__cw-btn-skip" style="background:#8b1a1a;color:#fff;border:0;border-radius:8px;'
    + 'padding:7px 14px;font-family:Tahoma;font-size:12px;cursor:pointer">⏭ رد کردن این صفحه</button>';
  try { document.body.appendChild(bar); } catch (e) { return false; }
  const b1 = document.getElementById('__cw-btn-continue');
  const b2 = document.getElementById('__cw-btn-skip');
  if (b1) b1.onclick = () => { window.__cw_pause_answer = 'continue'; };
  if (b2) b2.onclick = () => { window.__cw_pause_answer = 'skip'; };
  return true;
}
"""
JS_PAUSE_ANSWER = "() => window.__cw_pause_answer || ''"
JS_PAUSE_REMOVE = (r"""() => { const b = document.getElementById('__cw-pause-bar'); """
                   r"""if (b) b.remove(); window.__cw_pause_answer = ''; return true; }""")

def wait_page_answer(page, max_s):
    """انتظار پاسخ کاربر از دکمه‌های درون مرورگر (نوار شناور) — برای حالت خط فرمان
    یا به‌عنوان مسیر موازی رابط گرافیکی؛ خروجی: continue | skip"""
    try:
        page.evaluate(JS_PAUSE_OVERLAY)
    except Exception:
        pass
    t0 = time.time()
    while time.time() - t0 < max(5, max_s):
        try:
            if page.is_closed():
                return "continue"
            ans = page.evaluate(JS_PAUSE_ANSWER)
            if ans in ("continue", "skip"):
                return ans
        except Exception:
            pass
        time.sleep(0.5)
    return "continue"

def _submit_otp(page, code, site):
    """ثبت کد تأیید دومعلی — پشتیبانی از جعبه تکی و جعبه‌های رقم‌به‌رقم (React/Vue هم)
    همیشه قبل از پر کردن، فیلد را دوباره علامت‌گذاری می‌کنیم؛ چون صفحه ممکن است
    بعد از رندر دوباره (React/Angular) المان قبلی را دور ریخته باشد."""
    code = (code or "").strip()
    if not code:
        return False
    try:
        # علامت‌گذاری تازه‌ی فیلد و دکمه (اگر صفحه کد هنوز باز باشد)
        try:
            page.evaluate(JS_OTP_FIELD)
        except Exception:
            pass
        # پر کردن کد — از ست‌کننده بومی + رویداد input/change (سازگار با فریم‌ورک‌ها)
        filled = False
        try:
            filled = bool(page.evaluate(JS_OTP_FILL, code))
        except Exception:
            filled = False
        if not filled:
            try:
                page.fill("[data-cw-otp]", code, timeout=6000)
                filled = True
            except Exception:
                pass
        if not filled:
            warn("فیلد کد تأیید پیدا نشد یا پر نشد.")
            return False
        time.sleep(0.4)
        # ثبت: اول کلیک عادی، بعد کلیک جاوااسکریپتی، در نهایت Enter روی فیلد
        clicked = False
        try:
            page.click("[data-cw-otp-submit]", timeout=3500)
            clicked = True
        except Exception:
            pass
        if not clicked:
            ss = site.get("submit_selector")
            if ss:
                try:
                    page.click(ss, timeout=3500)
                    clicked = True
                except Exception:
                    pass
        if not clicked:
            try:
                if not page.evaluate(JS_CLICK_OTP_SUBMIT):
                    page.press("[data-cw-otp]", "Enter")
            except Exception:
                try:
                    page.press("[data-cw-otp]", "Enter")
                except Exception:
                    pass
        try:
            page.wait_for_load_state("load", timeout=15000)
        except Exception:
            pass
        time.sleep(1.5)
        info("کد تأیید ثبت شد؛ در حال بررسی نتیجه...")
        return True
    except Exception as e:
        warn(f"ثبت کد تأیید ناموفق بود: {short(e)}")
        return False

def do_auto_login(page, ctx, st):
    site = st.cfg.get("site", {})
    user = site.get("username") or ""
    passw = site.get("password") or ""
    if not user:
        err("نام کاربری/موبایل در تنظیمات خالی است؛ آن را وارد کنید یا از ورود دستی استفاده کنید.")
        return False
    if not is_login_page(page):
        lu = site.get("login_url")
        if lu:
            info(f"رفتن به صفحه ورود: {lu}")
            goto(page, lu, st.timeout)
    if not is_login_page(page):
        warn("فرم لاگین در صفحه پیدا نشد؛ login_url را در تنظیمات بررسی کنید.")
        return False

    otp_wait = int(site.get("otp_wait_seconds", 15))
    max_att = int(site.get("login_max_attempts", 5))
    for attempt in range(1, max_att + 1):
        # اگر از تلاش قبلی هنوز صفحه کد باز است، مرحله اول دوباره پر نمی‌شود
        try:
            otp_now = page.evaluate(JS_OTP_FIELD)
        except Exception:
            otp_now = None
        if attempt > 1 and otp_now and otp_now.get("found"):
            res = "otp"
        else:
            det = _detect_on(page)
            if not det.get("userMarked"):
                warn("فرم لاگین ناپدید شد.")
                return False
            _submit_login_form(page, det, user, passw, site)
            try:
                page.wait_for_load_state("load", timeout=15000)
            except Exception:
                pass
            time.sleep(1.2)
            res = _wait_after_submit(page, site, otp_wait)
        if res == "ok":
            ok("ورود با موفقیت انجام شد.")
            _save_session(ctx, st)
            return True
        if res == "otp":
            info("ورود دومعلی تشخیص داده شد — پنجره دریافت کد در برنامه باز شد.")
            if HOOKS.ask_otp is None:
                err("این سامانه ورود دومرحله‌ای (کد پیامکی) دارد؛ رابط گرافیکی را اجرا کنید یا از --manual استفاده کنید.")
                return False
            msg = "کد تأیید پیامک‌شده را وارد کنید"
            if attempt > 1:
                msg += f" — تلاش شماره {attempt}؛ کد قبلی پذیرفته نشد"
            try:
                code = HOOKS.ask_otp(msg)
            except Exception as e:
                warn(f"دریافت کد از رابط گرافیکی ناموفق: {short(e)}")
                code = None
            if code == OTP_IN_BROWSER:
                # کاربر خودش کد را در پنجره مرورگر وارد می‌کند — فقط منتظر موفقیت می‌مانیم
                info("خودتان کد را در پنجره‌ی مرورگر وارد و تأیید کنید (سقف ۳ دقیقه)...")
                t0 = time.time()
                done = False
                while time.time() - t0 < 180:
                    try:
                        if page.is_closed():
                            break
                        o = page.evaluate(JS_OTP_FIELD)
                        if not (o and o.get("found")):
                            done = True
                            break
                    except Exception:
                        done = True
                        break
                    time.sleep(1.0)
                if done:
                    ok("ورود با موفقیت کامل شد.")
                    _save_session(ctx, st)
                    return True
                warn("کد در مرورگر وارد نشد یا صفحه کد همچنان باز است.")
                continue
            if not code:
                warn("کدی وارد نشد؛ ورود ناتمام ماند.")
                return False
            if _submit_otp(page, code, site):
                res2 = _wait_after_submit(page, site, otp_wait)
                if res2 == "ok":
                    ok("ورود دومعلی با موفقیت کامل شد.")
                    _save_session(ctx, st)
                    return True
                if res2 == "otp":
                    warn("کد پذیرفته نشد یا صفحه کد دوباره نمایش داده شد؛ می‌توانید کد جدید وارد کنید.")
                    continue
        info("لاگین کامل نشد؛ تلاش مجدد...")
        try:
            if not is_login_page(page):
                lu = site.get("login_url") or (st.start_urls[0] if st.start_urls else None)
                if lu:
                    goto(page, lu, st.timeout)
        except Exception:
            pass
    err("ورود خودکار ناموفق بود. اگر کپچا یا تایید دومرحله‌ای دارد، از ورود دستی استفاده کنید.")
    return False

def do_manual_login(page, ctx, st):
    site = st.cfg.get("site", {})
    if st.headless:
        err("حالت لاگین دستی به پنجره مرورگر نیاز دارد. با فلگ --manual اجرا کنید.")
        return False
    target = site.get("login_url") or (st.start_urls[0] if st.start_urls else None)
    if target and not is_login_page(page):
        goto(page, target, st.timeout)
    info("در پنجره‌ی مرورگرِ باز شده، دستی وارد حساب شوید (کپچا/پیامک را کامل کنید).")
    info("برنامه به‌محض تشخیص ورود موفق، به‌صورت خودکار ادامه می‌دهد (سقف ۱۰ دقیقه)...")
    t0 = time.time()
    while time.time() - t0 < 600:
        try:
            if page.is_closed():
                return False
            if not is_login_page(page):
                ok("ورود دستی تشخیص داده شد. سشن ذخیره می‌شود...")
                _save_session(ctx, st)
                return True
        except Exception:
            return False
        time.sleep(2)
    err("زمان انتظار برای ورود دستی تمام شد.")
    return False

def do_login_flow(page, ctx, st):
    if st.manual_login:
        return do_manual_login(page, ctx, st)
    return do_auto_login(page, ctx, st)

# ---------------------------------------------------------------- ذخیره فایل‌های ظاهری صفحه (CSS/JS/تصویر)
def save_assets(page, url, st):
    """ذخیره CSS، جاوااسکریپت، تصاویر و قالب‌های صفحه در پوشه assets/<اسلاگ>/
    خروجی: تعداد فایل‌های ذخیره‌شده"""
    if not st.save_assets:
        return 0
    try:
        items = page.evaluate(JS_ASSETS) or []
    except Exception as e:
        warn(f"استخراج فهرست فایل‌های ظاهری ناموفق: {short(e)}")
        return 0
    if not items:
        return 0
    slug = page_slug(url)
    saved, n = [], 0
    inline_i = {"css": 0, "js": 0}
    sub_of = {"css": "css", "js": "js", "img": "img"}
    for it in items:
        if n >= st.max_assets:
            break
        kind = it.get("kind") or "misc"
        sub = sub_of.get(kind, "misc")
        try:
            if it.get("inline"):
                body = it["inline"]
                if len(body) > 300000:
                    continue
                k = kind if kind in inline_i else "misc"
                fname = f"inline_{inline_i[k]}.{k}" if k in inline_i else f"inline_{n}.{kind}"
                if k in inline_i:
                    inline_i[k] += 1
                d = os.path.join(st.assets_dir, slug, sub)
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, fname), "w", encoding="utf-8") as f:
                    f.write(body)
                saved.append(f"{sub}/{fname}")
                n += 1
                continue
            u = it.get("url") or ""
            if not u.startswith(("http://", "https://")):
                continue
            r = page.context.request.get(u, timeout=15000)
            if not r.ok:
                continue
            body = r.body() or b""
            if len(body) > 5 * 1024 * 1024:
                continue
            name = os.path.basename(urlsplit(u).path) or f"file_{n}"
            name = re.sub(r"[^\w\u0600-\u06FF.-]", "_", name)[:80] or f"file_{n}"
            d = os.path.join(st.assets_dir, slug, sub)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, name), "wb") as f:
                f.write(body)
            saved.append(f"{sub}/{name}")
            n += 1
        except Exception:
            continue
    if saved:
        try:
            with open(os.path.join(st.assets_dir, slug, "_files.txt"), "w", encoding="utf-8") as f:
                f.write(f"صفحه: {url}\nزمان: {datetime.now().isoformat(timespec='seconds')}\n\n")
                f.write("\n".join(saved))
        except Exception:
            pass
    return n

# ---------------------------------------------------------------- ذخیره‌سازی یک صفحه
def _row_hash(r):
    """هش یک ردیف برای حذف تکراری‌های بین صفحات فهرست"""
    return hashlib.md5("\x01".join(str(x) for x in r).encode("utf-8")).hexdigest()

def rebuild_datasets(db, st):
    """بازسازی نگاشت datasetها از اجرای قبلی (برای ادامه‌ی خزش) + آماده‌سازی حذف تکراری"""
    try:
        rows = db.execute("SELECT sqlite_table, source_url, table_index FROM datasets").fetchall()
    except Exception:
        return
    for name, src, tidx in rows:
        if not name or not src:
            continue
        st.ds_used.add(name)
        st.ds_map[(pag_base(src), tidx or 0)] = name
        try:
            cols = [r[1] for r in db.execute(f'PRAGMA table_info("{name}")').fetchall() if r[1] != "_id"]
            st.ds_cols[name] = cols
            hset = st.ds_rows.setdefault(name, set())
            if cols:
                sel = ", ".join(f'"{c}"' for c in cols)
                for r in db.execute(f'SELECT {sel} FROM "{name}"'):
                    hset.add(_row_hash(r))
        except Exception:
            pass

def _create_dataset(db, st, url, tidx, headers, ncols, rows):
    """ساخت جدول SQLite واقعی با ستون‌های واقعی؛ داده‌ی همه صفحات یک فهرست
    (چه با دکمه بعدی و چه با ?page=2) در یک جدول ادغام و ردیف‌های تکراری حذف می‌شوند"""
    try:
        base_url = pag_base(url)
        key = (base_url, tidx)
        name = st.ds_map.get(key)
        if name is None:
            p = urlsplit(base_url)
            seg = [s for s in (p.path or "").split("/") if s]
            slug = _clean_ident(seg[-1] if seg else "page")[:28] or "page"
            name = f"ds_{slug}_t{tidx + 1}"
            base, k = name, 2
            while name in st.ds_used:
                name = f"{base}_{k}"
                k += 1
            st.ds_used.add(name)
            st.ds_map[key] = name
            cols = col_names(headers, ncols)
            st.ds_cols[name] = cols
            col_sql = ", ".join(f'"{c}" TEXT' for c in cols)
            db.execute(f'DROP TABLE IF EXISTS "{name}"')
            db.execute(f'CREATE TABLE "{name}" ("_id" INTEGER PRIMARY KEY AUTOINCREMENT, {col_sql})')
            db.execute("INSERT OR IGNORE INTO datasets(sqlite_table, source_url, table_index, headers_json, created_at)"
                       " VALUES (?,?,?,?,?)",
                       (name, base_url, tidx,
                        json.dumps(headers or [f"col_{i+1}" for i in range(ncols)], ensure_ascii=False),
                        datetime.now().isoformat(timespec="seconds")))
        cols = st.ds_cols.get(name) or col_names(headers, ncols)
        st.ds_cols[name] = cols
        ncols = len(cols)
        hset = st.ds_rows.setdefault(name, set())
        col_list = ", ".join(f'"{c}"' for c in cols)
        ph = ", ".join(["?"] * ncols)
        for r in rows:
            r2 = (list(r) + [""] * ncols)[:ncols]
            h = _row_hash(r2)
            if h in hset:
                st.n_ds_dup += 1
                continue
            hset.add(h)
            db.execute(f'INSERT INTO "{name}" ({col_list}) VALUES ({ph})', r2)
        return name
    except Exception as e:
        warn(f"ساخت جدول داده ناموفق بود (ادامه می‌دهیم): {short(e)}")
        return None

def store_page(page, url, page_state, http_status, pag_info, st, variant=0):
    """همه محتوای وضعیت فعلی صفحه را استخراج و در دیتابیس/فایل ذخیره می‌کند.
    خروجی: فهرست لینک‌های خام صفحه (برای صف خزش).
    variant>0 یعنی وضعیت‌های بعدی همان فهرست (صفحه‌ی ۲، ۳، ... با آدرس ثابت):
    HTML/اسکرین‌شات/متن/لینک دوباره ذخیره نمی‌شود — فقط ردیف‌های جدول اضافه می‌شود"""
    db = st.db
    title = ""
    try:
        title = page.title() or ""
    except Exception:
        pass

    html_rel, shot_rel = None, None
    if st.save_html and (variant == 0 or st.save_variant_html):
        try:
            html = page.content()
            base_tag = f'<base href="{page.url}">'
            html = re.sub(r"(<head[^>]*>)", r"\1" + base_tag, html, count=1, flags=re.I)
            fname = fname_for(url if variant == 0 else f"{url}#cwv{variant}", ".html")
            with open(os.path.join(st.html_dir, fname), "w", encoding="utf-8") as f:
                f.write(html)
            html_rel = os.path.relpath(os.path.join(st.html_dir, fname), st.base_dir)
        except Exception as e:
            warn(f"ذخیره HTML ناموفق: {short(e)}")

    if st.save_shots and variant == 0:
        try:
            fname = fname_for(url, ".png")
            page.screenshot(path=os.path.join(st.shot_dir, fname), full_page=True)
            shot_rel = os.path.relpath(os.path.join(st.shot_dir, fname), st.base_dir)
        except Exception as e:
            warn(f"اسکرین‌شات ناموفق: {short(e)}")

    # ذخیره CSS/JS/تصاویر/قالب صفحه در پوشه انتخابی کاربر
    if st.save_assets and variant == 0:
        try:
            n_assets = save_assets(page, url, st)
            if n_assets:
                info(f"{n_assets} فایل CSS/JS/تصویر این صفحه ذخیره شد")
        except Exception as e:
            warn(f"ذخیره فایل‌های ظاهری ناموفق: {short(e)}")

    texts = []
    if st.save_texts and variant == 0:
        try:
            texts = page.evaluate(JS_TEXTS) or []
            dedup = []
            for t in texts:
                if not dedup or dedup[-1]["t"] != t["t"]:
                    dedup.append(t)
            texts = dedup
        except Exception as e:
            warn(f"استخراج متن ناموفق: {short(e)}")

    # جداول — از خود صفحه و همه فریم‌ها (پنل‌های iframe محور مثل CRMها)
    tables = []
    try:
        tables = page.evaluate(JS_TABLES) or []
        for fr in page.frames[1:]:
            try:
                tables.extend(fr.evaluate(JS_TABLES) or [])
            except Exception:
                pass
    except Exception as e:
        warn(f"استخراج جداول ناموفق: {short(e)}")

    page_id = db_insert_page(db, url, page_state, title, http_status, html_rel, shot_rel,
                             pag_info, len(tables), len(texts))
    if page_id is None:
        return []

    if st.save_texts and texts:
        db.executemany("INSERT INTO page_texts(page_id, kind, content) VALUES (?,?,?)",
                       [(page_id, t.get("k"), t.get("t")) for t in texts])

    for ti, tb in enumerate(tables):
        headers = tb.get("headers") or []
        rows = tb.get("rows") or []
        ncols = max([len(headers)] + [len(r) for r in rows]) if (headers or rows) else 0
        if ncols == 0:
            continue
        cur = db.execute(
            "INSERT INTO html_tables(page_id, table_index, caption, headers_json, n_rows, n_cols, dataset_table)"
            " VALUES (?,?,?,?,?,?,?)",
            (page_id, ti, tb.get("caption") or None, json.dumps(headers, ensure_ascii=False),
             len(rows), ncols, None))
        table_id = cur.lastrowid
        clean_rows = []
        for r in rows:
            r2 = list(r) + [""] * (ncols - len(r))
            clean_rows.append(r2[:ncols])
        db.executemany("INSERT INTO table_rows(table_id, row_index, data_json) VALUES (?,?,?)",
                       [(table_id, i, json.dumps(r, ensure_ascii=False)) for i, r in enumerate(clean_rows)])
        if st.datasets_on and clean_rows:
            ds_name = _create_dataset(db, st, url, ti, headers, ncols, clean_rows)
            if ds_name:
                db.execute("UPDATE html_tables SET dataset_table=? WHERE id=?", (ds_name, table_id))

    raw_links = []
    if variant == 0:   # لینک‌های وضعیت‌های بعدی فهرست همان قبلی‌هاست؛ استخراج نمی‌شود
        try:
            raw_links = page.evaluate(JS_LINKS) or []
        except Exception:
            raw_links = []
        # لینک‌های داخل iframeها (پنل‌های فریم‌محور)
        try:
            for fr in page.frames[1:]:
                raw_links.extend(fr.evaluate(JS_LINKS) or [])
        except Exception:
            pass
    seen_l = set()
    link_rows = []
    for L in raw_links[:800]:
        href = L.get("href") or ""
        if not href.startswith("http://") and not href.startswith("https://"):
            continue
        if href in seen_l:
            continue
        seen_l.add(href)
        link_rows.append((page_id, href, L.get("text") or ""))
    if link_rows:
        db.executemany("INSERT INTO links(page_id, url, text) VALUES (?,?,?)", link_rows)

    db.commit()
    st.n_stored += 1
    n_t = f"{len(tables)} جدول" if tables else ""
    extra = f" | {pag_info}" if pag_info and pag_info != "-" else ""
    if variant > 0:
        ok(f"وضعیت {variant + 1} فهرست ({st.n_stored}): {url}" + (f" | {n_t}" if n_t else "") + extra)
    else:
        ok(f"ذخیره شد ({st.n_stored}): {url}" + (f" | {n_t}" if n_t else "") + extra)
    db_log(db, "PAGE", url)
    return [L[1] for L in link_rows] if variant == 0 else []

# ---------------------------------------------------------------- صفحه‌بندی و پردازش یک URL
def process_page(page, ctx, url, st):
    """یک URL را باز، لاگین را چک، صفحه‌بندی را تشخیص و همه وضعیت‌ها را ذخیره می‌کند.
    خروجی: مجموعه URLهایی که در همین پردازش دیدمانده شد"""
    mode = str(st.cfg.get("pagination", {}).get("mode", "auto")).lower()
    urls_seen = set()
    resp = goto(page, url, st.timeout)
    if not is_valid_http(page.url):
        return urls_seen
    if is_block_page(page):
        warn(f"دسترسی توسط فایروال مسدود شد؛ این صفحه ذخیره نشد: {url}")
        db_log(st.db, "BLOCKED", url)
        st.n_blocked += 1
        return urls_seen
    if is_login_page(page):
        info("نشست منقضی شده؛ در حال ورود مجدد...")
        if not do_login_flow(page, ctx, st):
            return urls_seen
        resp = goto(page, url, st.timeout)
        if not is_valid_http(page.url):
            return urls_seen
        if is_login_page(page):
            warn("پس از ورود، باز هم صفحه لاگین نمایش داده شد؛ این صفحه ذخیره نشد.")
            return urls_seen
        if is_block_page(page):
            warn(f"دسترسی توسط فایروال مسدود شد؛ این صفحه ذخیره نشد: {url}")
            db_log(st.db, "BLOCKED", url)
            st.n_blocked += 1
            return urls_seen
    time.sleep(st.delay)

    # --- رد شدن خودکار از صفحات فیلتر/جست‌وجو (کد ملی، کد پرونده، کد رهگیری و ...) ---
    # این صفحات داده‌ی برداشتنی ندارند؛ فقط لینک‌هایشان دنبال می‌شود تا خزش قطع نشود
    if st.skip_filter_pages:
        fp = None
        try:
            fp = page.evaluate(JS_FILTER_PAGE, st.filter_keywords)
        except Exception:
            fp = None
        if fp and fp.get("found"):
            st.n_filter_skip += 1
            info(f"⏭ صفحه فیلتر «{fp.get('kind')}» رد شد — فقط لینک‌ها برداشت می‌شود: {url}")
            db_log(st.db, "FILTER_SKIP", url)
            try:
                raw = page.evaluate(JS_LINKS) or []
                for fr in page.frames[1:]:
                    try:
                        raw.extend(fr.evaluate(JS_LINKS) or [])
                    except Exception:
                        pass
            except Exception:
                raw = []
            seen_l = set()
            for L in raw[:800]:
                h = L.get("href") or ""
                if (h.startswith("http://") or h.startswith("https://")) and h not in seen_l:
                    seen_l.add(h)
                    if st.enqueue:
                        st.enqueue(h)
            return urls_seen

    # --- توقف برای اعمال فیلتر توسط کاربر (صفحات گزارشی/فیلردار) ---
    # پاسخ می‌تواند از دو جا بیاید: دکمه‌های درون مرورگر (نوار شناور) یا رابط گرافیکی
    if st.pause_urls:
        low = unquote(page.url).lower()
        if any(p == "**" or p.lower() in low for p in st.pause_urls):
            info("برای اعمال فیلترها منتظر شما هستیم — دکمه‌های «ادامه» / «رد کردن» در مرورگر و در برنامه فعال است.")
            act = "continue"
            try:
                if HOOKS.filter_pause is not None:
                    act = HOOKS.filter_pause(page.url, page)
                else:
                    act = wait_page_answer(page, 600)
            except Exception as e:
                warn(f"خطا در انتظار فیلتر (ادامه می‌دهیم): {short(e)}")
                act = "continue"
            finally:
                try:
                    page.evaluate(JS_PAUSE_REMOVE)
                except Exception:
                    pass
            if act == "skip":
                info(f"با فرمان شما از این صفحه رد شدیم: {url}")
                db_log(st.db, "SKIPPED", url)
                return urls_seen
            # ممکن است اعمال فیلتر آدرس را عوض کرده باشد
            cur_url = norm(page.url) or url
    cur_url = norm(page.url) or url
    urls_seen.add(cur_url)

    # --- اسکرول بی‌نهایت؟ ---
    infinite = False
    if mode in ("auto", "scroll"):
        m0 = scroll_metrics(page)
        if m0 and m0["h"] > m0["vh"] + 120 and m0["items"] >= 8:
            page.evaluate(JS_SCROLL_BOTTOM)
            time.sleep(st.scroll_wait)
            m1 = scroll_metrics(page)
            page.evaluate(JS_SCROLL_TOP)
            time.sleep(0.2)
            if m1 and (m1["h"] > m0["h"] + 120 or m1["items"] > m0["items"]):
                infinite = True
                info("نوع صفحه‌بندی: اسکرول بی‌نهایت — در حال بارگذاری همه موارد...")
                prev, stable, n = m1, 0, 0
                while n < st.max_scrolls:
                    page.evaluate(JS_SCROLL_BOTTOM)
                    time.sleep(st.scroll_wait)
                    n += 1
                    if is_login_page(page):
                        if not do_login_flow(page, ctx, st):
                            break
                    if is_block_page(page):
                        warn("دسترسی توسط فایروال مسدود شد؛ توقف اسکرول.")
                        break
                    cur_m = scroll_metrics(page)
                    if cur_m and cur_m["h"] <= prev["h"] + 50 and cur_m["items"] <= prev["items"]:
                        stable += 1
                        if stable >= 3:
                            break
                    else:
                        stable = 0
                    prev = cur_m
                page.evaluate(JS_SCROLL_TOP)
    if infinite:
        for u in store_page(page, cur_url, 0, page_status(resp), "اسکرول بی‌نهایت", st):
            st.enqueue(u)
        return urls_seen

    # --- ذخیره وضعیت اول ---
    for u in store_page(page, cur_url, 0, page_status(resp), "-", st):
        st.enqueue(u)
    if mode == "none":
        return urls_seen

    # --- حالت ۱: دکمه «بعدی / بیشتر» ---
    if mode in ("auto", "click"):
        sig = page_sig(page)
        rows_prev = rows_sig(page)
        idx = 0
        got = False
        while idx < st.max_list_pages:
            try:
                page.evaluate(JS_UNMARK)
                found = page.evaluate(JS_FIND_NEXT_MARK)
            except Exception:
                break
            if not found or not found.get("found"):
                break
            # کلیک عادی؛ اگر نشد کلیک جاوااسکریپتی (روی برخی قالب‌ها لازم است)
            clicked = False
            try:
                page.locator('[data-cw-next="1"]').first.click(timeout=6000)
                clicked = True
            except Exception:
                try:
                    page.eval_on_selector('[data-cw-next="1"]', JS_CLICK_NEXT)
                    clicked = True
                except Exception as e:
                    warn(f"کلیک روی «بعدی» ناموفق: {short(e)}")
            if not clicked:
                break
            try:
                page.wait_for_load_state("load", timeout=st.timeout)
            except Exception:
                pass
            time.sleep(st.delay)
            if is_login_page(page):
                if not do_login_flow(page, ctx, st):
                    break
            if is_block_page(page):
                warn("صفحه بعدی فهرست توسط فایروال مسدود شد؛ صفحه‌بندی همین‌جا قطع شد.")
                break
            new_url = norm(page.url)
            new_sig = page_sig(page)
            new_rows = rows_sig(page)
            if new_sig == sig and new_url == cur_url:
                break   # کلیک اثری نداشت = آخرین صفحه
            if rows_prev is not None and new_rows == rows_prev:
                break   # ردیف‌ها همان قبلی‌هاست = داده تازه نیامده؛ پایان فهرست
            idx += 1
            got = True
            info(f"صفحه {idx + 1} همین فهرست (دکمه «بعدی»)")
            if new_url != cur_url:
                if new_url in st.visited or new_url in urls_seen:
                    break
                st.visited.add(new_url)
                urls_seen.add(new_url)
                links = store_page(page, new_url, 0, None, "دکمه بعدی", st)
            else:
                links = store_page(page, cur_url, idx, None, "دکمه بعدی", st, variant=idx)
            for u in links:
                st.enqueue(u)
            cur_url, sig, rows_prev = new_url, new_sig, new_rows
        if got:
            return urls_seen

    # --- حالت ۲: لینک‌های شماره صفحه ---
    if mode in ("auto", "numbered"):
        try:
            nums = page.evaluate(JS_NUMBERED) or []
        except Exception:
            nums = []
        base_d = dirbase(cur_url)
        cand = set()
        for x in nums:
            try:
                n2 = norm(x["href"])
            except Exception:
                continue
            if n2 == cur_url or n2 in st.visited:
                continue
            if dirbase(n2) != base_d:
                continue
            try:
                cand.add((int(x["t"]), n2))
            except ValueError:
                continue
        if cand:
            info(f"نوع صفحه‌بندی: شماره صفحه ({len(cand)} صفحه دیگر)")
            for _, nurl in sorted(cand):
                if nurl in st.visited:
                    continue
                st.visited.add(nurl)
                urls_seen.add(nurl)
                r = goto(page, nurl, st.timeout)
                if not is_valid_http(page.url):
                    continue
                if is_block_page(page):
                    warn(f"دسترسی توسط فایروال مسدود شد؛ رد شد: {nurl}")
                    continue
                if is_login_page(page):
                    if not do_login_flow(page, ctx, st):
                        continue
                    r = goto(page, nurl, st.timeout)
                    if not is_valid_http(page.url):
                        continue
                time.sleep(st.delay)
                for u in store_page(page, nurl, 0, page_status(r), "شماره صفحه", st):
                    st.enqueue(u)
            return urls_seen

    # --- حالت ۳: پارامتر ?page=N در آدرس ---
    if mode in ("auto", "url"):
        pcfg = st.cfg.get("pagination", {})
        param = pcfg.get("url_page_param")
        params = [param] if param else ["page", "p", "pg", "pagenumber", "pageindex"]
        if param or "?" in url:
            sig0 = page_sig(page)
            for prm in params:
                probed = False
                for n in range(2, st.max_list_pages + 2):
                    nurl = with_param(url, prm, str(n))
                    nurl_n = norm(nurl)
                    if nurl_n in st.visited or nurl_n in urls_seen:
                        break
                    r = goto(page, nurl, st.timeout)
                    if not is_valid_http(page.url):
                        break
                    if is_block_page(page):
                        warn("دسترسی توسط فایروال مسدود شد؛ پایان صفحه‌بندی.")
                        break
                    if is_login_page(page):
                        if not do_login_flow(page, ctx, st):
                            break
                        r = goto(page, nurl, st.timeout)
                        if not is_valid_http(page.url):
                            break
                    time.sleep(st.delay)
                    s = page_sig(page)
                    if looks_error(page) or s == sig0 or s is None:
                        break   # پارامتر اشتباه یا پایان فهرست
                    probed = True
                    info(f"صفحه {n} همین فهرست (پارامتر {prm})")
                    st.visited.add(nurl_n)
                    urls_seen.add(nurl_n)
                    for u in store_page(page, nurl_n, 0, page_status(r), f"پارامتر {prm}", st):
                        st.enqueue(u)
                    sig0 = s
                if probed:
                    break
    return urls_seen

# ---------------------------------------------------------------- ضبط پاسخ‌های JSON (API واقعی داده)
def attach_api_capture(page, st):
    """پاسخ JSON درخواست‌های XHR/Fetch همان دامنه را در جدول api_responses ذخیره می‌کند
    — در سایت‌های جاوااسکریپتی این‌ها داده‌ی خام واقعی‌اند"""
    if not st.api_on:
        return
    max_b = st.api_body_max * 1024

    def on_response(resp):
        try:
            req = resp.request
            if (req.resource_type or "") not in ("xhr", "fetch"):
                return
            ctype = (resp.header_value("content-type") or "").lower()
            if "json" not in ctype:
                return
            if urlsplit(resp.url).netloc.lower() != st.host:
                return
            if len(st.api_seen) >= st.api_max:
                return
            key = (req.method or "", norm(resp.url))
            if key in st.api_seen:
                return
            cl = resp.header_value("content-length")
            if cl and cl.isdigit() and int(cl) > max_b:
                return
            try:
                body = resp.text()
            except Exception:
                return
            st.api_seen.add(key)
            st.db.execute("INSERT INTO api_responses(ts, page_url, method, url, status, content_type, body)"
                          " VALUES (?,?,?,?,?,?,?)",
                          (datetime.now().isoformat(timespec="seconds"), (page.url or "")[:500],
                           req.method, resp.url[:1000], resp.status, ctype, body[:max_b]))
            st.db.commit()
            st.n_api += 1
        except Exception:
            pass

    page.on("response", on_response)

# ---------------------------------------------------------------- حلقه اصلی خزش
def run(st, page, ctx):
    crawl = st.cfg.get("crawl", {})
    starts = list(st.cfg.get("site", {}).get("start_urls") or [])
    if st.cli_start_url:
        starts.append(st.cli_start_url)
    starts.extend(st.extra_starts or [])
    if not starts:
        err("هیچ start_urls در config تعریف نشده است.")
        return

    def enqueue(u, force=False):
        nu = norm(u)
        if nu in st.visited or nu in st.enqueued:
            return
        # شروع‌های صریح کاربر از فیلترهای محدودکننده عبور می‌کنند
        if force or st.allowed_target(nu):
            st.enqueued.add(nu)
            st.queue.append(nu)

    st.enqueue = enqueue

    if crawl.get("resume", True):
        for (u,) in st.db.execute("SELECT DISTINCT url FROM pages WHERE page_state=0"):
            st.visited.add(u)
        if st.visited:
            info(f"ادامه‌ی خزش قبلی: {len(st.visited)} صفحه قبلاً گرفته شده (برای شروع از صفر: --fresh)")
        rebuild_datasets(st.db, st)

    for s in starts:
        enqueue(s, force=True)

    head(f"شروع خزش — سقف: {st.max_pages} صفحه")
    count = 0
    blocked_streak = 0
    while st.queue and count < st.max_pages:
        if HOOKS.stopped:
            warn("توقف خزش به درخواست شما از رابط گرافیکی.")
            break
        url = st.queue.popleft()
        if url in st.visited:
            continue
        st.visited.add(url)
        count += 1
        info(f"({count}/{st.max_pages}) {url}")
        if HOOKS.progress:
            try:
                HOOKS.progress(count, st.max_pages, url)
            except Exception:
                pass
        try:
            before = st.n_blocked
            seen = process_page(page, ctx, url, st)
            for u in seen:
                st.visited.add(u)
            if st.n_blocked > before:
                blocked_streak += 1
            else:
                blocked_streak = 0
        except Exception as e:
            err(f"خطا در پردازش صفحه: {short(e)}")
            db_log(st.db, "ERROR", f"{url} :: {short(e)}")
        if blocked_streak >= 1 and count == 1:
            err("اولین صفحه‌ی سایت توسط فایروال مسدود شده است؛ خزش متوقف شد.")
            print(BLOCK_SOLUTIONS)
            st.abort_reason = "blocked"
            break
        if blocked_streak >= 3:
            err("چند صفحه پشت‌سرهم توسط فایروال مسدود شد؛ خزش متوقف شد.")
            print(BLOCK_SOLUTIONS)
            st.abort_reason = "blocked"
            break
        time.sleep(st.delay)
    if st.queue and not HOOKS.stopped and not st.abort_reason:
        warn(f"{len(st.queue)} URL در صف مانده (سقف max_pages پر شد). دوباره اجرا کنید تا از ادامه‌ی صف انجام شود.")

# ---------------------------------------------------------------- خروجی Excel / CSV
def export_data(st):
    """ساخت خروجی Excel (یک شیت به‌ازای هر جدول داده) و CSV از دیتابیس"""
    db = st.db
    try:
        ds = db.execute("SELECT sqlite_table, source_url, created_at FROM datasets ORDER BY id").fetchall()
    except Exception:
        ds = []
    out_msgs = []
    if st.export_csv:
        try:
            import csv as _csv
            csv_dir = os.path.join(st.base_dir, st.cfg.get("output", {}).get("csv_dir", "output/csv"))
            os.makedirs(csv_dir, exist_ok=True)
            n = 0
            for (name,) in [(d[0],) for d in ds]:
                try:
                    cols = [r[1] for r in db.execute(f'PRAGMA table_info("{name}")').fetchall() if r[1] != "_id"]
                    if not cols:
                        continue
                    sel = ", ".join(f'"{c}"' for c in cols)
                    with open(os.path.join(csv_dir, f"{name}.csv"), "w", encoding="utf-8-sig", newline="") as f:
                        w = _csv.writer(f)
                        w.writerow(cols)
                        for r in db.execute(f'SELECT {sel} FROM "{name}"'):
                            w.writerow(r)
                    n += 1
                except Exception:
                    pass
            if n:
                out_msgs.append(f"خروجی CSV: {n} فایل در {csv_dir}")
        except Exception as e:
            warn(f"خروجی CSV ناموفق بود: {short(e)}")
    if st.export_excel:
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font
            from openpyxl.utils import get_column_letter
        except Exception:
            warn("کتابخانه openpyxl نصب نیست؛ خروجی Excel ساخته نشد. نصب:  pip install openpyxl")
            return out_msgs
        try:
            xlsx_path = os.path.join(st.base_dir, st.cfg.get("output", {}).get("excel_path", "output/export.xlsx"))
            os.makedirs(os.path.dirname(xlsx_path), exist_ok=True)
            wb = Workbook()
            bold = Font(bold=True)
            used_titles = {"خلاصه"}
            ws = wb.active
            ws.title = "خلاصه"
            ws.sheet_view.rightToLeft = True
            ws.append(["جدول داده", "ردیف‌ها", "ستون‌ها", "منبع (URL)", "زمان ساخت"])
            for c in ws[1]:
                c.font = bold
            for name, src, cr in ds:
                try:
                    cols = [r[1] for r in db.execute(f'PRAGMA table_info("{name}")').fetchall() if r[1] != "_id"]
                    if not cols:
                        continue
                    sel = ", ".join(f'"{c}"' for c in cols)
                    rows = db.execute(f'SELECT {sel} FROM "{name}"').fetchall()
                    ws.append([name, len(rows), len(cols), src or "", cr or ""])
                    t = re.sub(r"[\[\]:*?/\\]", "_", name)[:31] or f"sheet{len(used_titles) + 1}"
                    t2, k = t, 2
                    while t2 in used_titles:
                        t2 = f"{t[:28]}_{k}"
                        k += 1
                    used_titles.add(t2)
                    sh = wb.create_sheet(t2)
                    sh.sheet_view.rightToLeft = True
                    sh.append(cols)
                    for c in sh[1]:
                        c.font = bold
                    for r in rows:
                        sh.append(["" if v is None else v for v in r])
                    sh.freeze_panes = "A2"
                    for i, cname in enumerate(cols, start=1):
                        wds = [len(str(cname))] + [len(str(r[i - 1])) for r in rows[:200] if i - 1 < len(r)]
                        sh.column_dimensions[get_column_letter(i)].width = min(60, max(10, max(wds) + 4))
                except Exception:
                    continue
            wb.save(xlsx_path)
            out_msgs.append(f"خروجی Excel: {xlsx_path} ({len(ds)} جدول)")
        except Exception as e:
            warn(f"خروجی Excel ناموفق بود: {short(e)}")
        # --- اکسل جداگانه به نام هر صفحه (یک فایل برای هر صفحه‌ی دارای جدول) ---
        if st.per_page_excel and ds:
            try:
                os.makedirs(st.excel_dir, exist_ok=True)
                groups = {}
                for name, src, cr in ds:
                    groups.setdefault(src or "سایت", []).append(name)
                n_files = 0
                for i, (src, names) in enumerate(sorted(groups.items()), start=1):
                    filled = []
                    for name in names:
                        try:
                            if db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]:
                                filled.append(name)
                        except Exception:
                            pass
                    if not filled:
                        continue
                    slug = page_slug(src if src.startswith("http") else f"https://x/{src}")
                    fname = re.sub(r'[<>:"/\\|?*]', "_", slug)[:80] or f"page-{i}"
                    wb2 = Workbook()
                    ws2 = wb2.active
                    ws2.title = "خلاصه"
                    ws2.sheet_view.rightToLeft = True
                    ws2.append(["جدول داده", "ردیف‌ها", "ستون‌ها", "منبع (URL)"])
                    for c in ws2[1]:
                        c.font = bold
                    for name in filled:
                        try:
                            cols = [r[1] for r in db.execute(f'PRAGMA table_info("{name}")').fetchall() if r[1] != "_id"]
                            if not cols:
                                continue
                            sel = ", ".join(f'"{c}"' for c in cols)
                            rows = db.execute(f'SELECT {sel} FROM "{name}"').fetchall()
                            ws2.append([name, len(rows), len(cols), src or ""])
                            t = re.sub(r"[\[\]:*?/\\]", "_", name)[:31] or f"sheet{n_files}"
                            sh = wb2.create_sheet(t)
                            sh.sheet_view.rightToLeft = True
                            sh.append(cols)
                            for c in sh[1]:
                                c.font = bold
                            for r in rows:
                                sh.append(["" if v is None else v for v in r])
                            sh.freeze_panes = "A2"
                        except Exception:
                            continue
                    wb2.save(os.path.join(st.excel_dir, fname + ".xlsx"))
                    n_files += 1
                if n_files:
                    out_msgs.append(f"اکسل جداگانه هر صفحه: {n_files} فایل در {st.excel_dir}")
            except Exception as e:
                warn(f"اکسل جداگانه صفحات ناموفق بود: {short(e)}")
    return out_msgs

def print_summary(st):
    db = st.db
    head("گزارش نهایی خزش")
    n_pages = db.execute("SELECT COUNT(DISTINCT url) FROM pages").fetchone()[0]
    n_states = db.execute("SELECT COUNT(*) FROM pages WHERE page_state > 0").fetchone()[0]
    n_tables = db.execute("SELECT COUNT(*) FROM html_tables").fetchone()[0]
    n_rows = db.execute("SELECT COUNT(*) FROM table_rows").fetchone()[0]
    n_texts = db.execute("SELECT COUNT(*) FROM page_texts").fetchone()[0]
    n_links = db.execute("SELECT COUNT(*) FROM links").fetchone()[0]
    print(f"   صفحات یکتا:          {n_pages}")
    print(f"   وضعیت‌های صفحه‌بندی: {n_states}")
    print(f"   جداول HTML:          {n_tables}")
    print(f"   ردیف‌های جدول:       {n_rows}")
    print(f"   متن/تیتر:            {n_texts}")
    print(f"   لینک‌های ثبت‌شده:    {n_links}")
    if st.api_on:
        try:
            n_api = db.execute("SELECT COUNT(*) FROM api_responses").fetchone()[0]
            print(f"   پاسخ‌های JSON (API): {n_api}")
        except Exception:
            pass
    if st.n_ds_dup:
        print(f"   ردیف‌های تکراری حذف‌شده: {st.n_ds_dup}")
    if st.n_filter_skip:
        print(f"   صفحات فیلتر رد‌شده (کد ملی/پرونده/رهگیری): {st.n_filter_skip}")
    if st.n_action_skip:
        print(f"   لینک‌های عملیاتی/ناآمن رد‌شده: {st.n_action_skip}")
    ds = db.execute("SELECT sqlite_table, source_url FROM datasets ORDER BY id").fetchall()
    if ds:
        print("\n   جداول داده‌ی ساختاریافته:")
        shown = 0
        for name, src in ds:
            shown += 1
            if shown > 40:
                print(f"     ... و {len(ds) - 40} جدول دیگر")
                break
            try:
                cnt = db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            except Exception:
                cnt = "?"
            print(f"     - {name}  ({cnt} ردیف)  ← {src}")
    print(f"\n   دیتابیس:  {st.db_path}")
    if st.save_html:
        print(f"   فایل‌های HTML:  {st.html_dir}")
    if st.save_shots:
        print(f"   اسکرین‌شات‌ها:  {st.shot_dir}")
    if st.save_assets:
        print(f"   فایل‌های CSS/JS/قالب:  {st.assets_dir}")
    if st.per_page_excel and st.export_excel:
        print(f"   اکسل هر صفحه:  {st.excel_dir}")

# ---------------------------------------------------------------- آماده‌سازی و اجرا
def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return {k: v for k, v in cfg.items() if not k.startswith("_")}

class Tee:
    """خروجی ترمینال را هم‌زمان در فایل لاگ هم می‌نویسد"""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for x in self.streams:
            try:
                x.write(s)
                x.flush()
            except Exception:
                pass
        return len(s)

    def flush(self):
        for x in self.streams:
            try:
                x.flush()
            except Exception:
                pass

def main():
    ap = argparse.ArgumentParser(description="سایت‌کاو — خزش هوشمند سایت‌های دارای لاگین")
    ap.add_argument("--config", default="config.json", help="مسیر فایل تنظیمات (پیش‌فرض: config.json)")
    ap.add_argument("--manual", action="store_true", help="لاگین دستی در پنجره مرورگر (برای کپچا/پیامک)")
    ap.add_argument("--headed", action="store_true", help="مرورگر قابل مشاهده اجرا شود")
    ap.add_argument("--login", action="store_true", help="لاگین مجدد اجباری (سشن موجود نادیده گرفته می‌شود)")
    ap.add_argument("--fresh", action="store_true", help="دیتابیس قبلی کنار گذاشته شود و از صفر شروع شود")
    ap.add_argument("--max-pages", type=int, help="سقف تعداد صفحات (بازنویسی config)")
    ap.add_argument("--start-url", help="افزودن URL شروع جدید (علاوه بر config)")
    ap.add_argument("--cdp", nargs="?", const="9222", default=None, metavar="PORT",
                    help="اتصال به کرومِ در حال اجرای خودتان (پورت remote-debugging؛ پیش‌فرض ۹۲۲۲)")
    ap.add_argument("--export-only", action="store_true",
                    help="بدون خزش؛ فقط خروجی Excel/CSV از دیتابیس موجود ساخته می‌شود")
    args = ap.parse_args()

    cfg_path = os.path.abspath(args.config)
    if not os.path.exists(cfg_path):
        err(f"فایل تنظیمات پیدا نشد: {cfg_path}")
        sys.exit(1)
    cfg = load_config(cfg_path)
    res = run_crawl(cfg, base_dir=os.path.dirname(cfg_path),
                    fresh=args.fresh, headed=args.headed, manual=args.manual,
                    login=args.login, max_pages=args.max_pages, start_url=args.start_url,
                    cdp=args.cdp, export_only=args.export_only)
    if not res.get("ok"):
        sys.exit({"login_failed": 2, "blocked": 3, "cdp_failed": 4}.get(res.get("error"), 1))
    head("پایان — خروجی‌سازی انجام شد!" if args.export_only else "پایان — موفق باشید!")

def install_dialog_guard(page):
    """پاسخ خودکار به پنجره‌های جاوااسکریپت سایت (alert/confirm/beforeunload).
    بدون این، اگر سایت پس از ثبت کد یا عملیاتی alert نشان دهد، همه‌ی دستورهای
    بعدی مرورگر قفل می‌شوند و برنامه بی‌پایان منتظر می‌ماند."""
    def _h(d):
        try:
            d.dismiss()
        except Exception:
            pass
    try:
        page.on("dialog", _h)
        return True
    except Exception:
        return False

def run_crawl(cfg, base_dir, fresh=False, headed=False, manual=False, login=False,
              max_pages=None, start_url=None, cdp=None, export_only=False, log_file=None):
    """اجرای کامل خزش از روی تنظیمات — هم از خط فرمان و هم از رابط گرافیکی.
    خروجی: dict شامل ok و آمار و پیام‌ها (هرگز sys.exit نمی‌زند)"""
    base_dir = os.path.abspath(base_dir)
    os.makedirs(base_dir, exist_ok=True)
    if max_pages:
        cfg.setdefault("crawl", {})["max_pages"] = int(max_pages)

    # ثبت هم‌زمان لاگ در فایل (کنار خروجی فعلی — ترمینال یا رابط گرافیکی)
    _log_f = None
    _old_stdout = sys.stdout
    try:
        lp = log_file or os.path.join(base_dir, cfg.get("output", {}).get("log_file", "output/crawl.log"))
        os.makedirs(os.path.dirname(lp), exist_ok=True)
        _log_f = open(lp, "a", encoding="utf-8")
        sys.stdout = Tee(sys.stdout, _log_f)
    except Exception:
        _log_f = None

    db = None
    summary = {"ok": True, "msgs": []}
    try:
        db_path = os.path.join(base_dir, cfg.get("output", {}).get("db_path", "site_data.db"))
        if fresh and os.path.exists(db_path):
            bak = db_path + f".bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            os.rename(db_path, bak)
            info(f"دیتابیس قبلی به {os.path.basename(bak)} منتقل شد.")

        import sqlite3
        db = sqlite3.connect(db_path)
        db.executescript(DB_SCHEMA)
        db.commit()

        st = State(cfg, db, base_dir)
        st.db_path = db_path
        st.cli_start_url = start_url
        st.manual_login = manual
        st.headless = not (headed or manual)

        summary["db_path"] = db_path
        summary["html_dir"] = st.html_dir
        summary["shots_dir"] = st.shot_dir
        summary["assets_dir"] = st.assets_dir
        summary["excel_dir"] = st.excel_dir

        if export_only:
            head("ساخت خروجی‌ها از دیتابیس موجود")
            rebuild_datasets(db, st)
            summary["msgs"] = export_data(st)
            for m in summary["msgs"]:
                ok(m)
            return summary

        sess_file = os.path.join(base_dir, cfg.get("output", {}).get("session_file", "session.json"))
        use_session = os.path.exists(sess_file) and not login
        starts = list(cfg.get("site", {}).get("start_urls") or [])
        if start_url:
            starts.append(start_url)
        if not starts:
            summary.update({"ok": False, "error": "no_start_urls",
                            "hint": "آدرس سامانه (start_urls) وارد نشده است."})
            return summary

        # توقف فیلتر بدون مرورگر مرئی ممکن نیست — خودکار قابل‌مشاهده می‌شود
        if st.pause_urls and HOOKS.filter_pause and st.headless:
            st.headless = False
            warn("برای توقف فیلتر، مرورگر به‌صورت قابل مشاهده باز می‌شود.")

        head("سایت‌کاو — شروع کار")
        with sync_playwright() as p:
            bcfg = cfg.get("browser", {})
            if cdp:
                # حالت اتصال به کروم واقعی کاربر — بهترین راه برای عبور از فایروال سازمانی
                info(f"اتصال به کرومِ شما از طریق درگاه {cdp}...")
                try:
                    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp}")
                except Exception as e:
                    summary.update({"ok": False, "error": "cdp_failed",
                                    "hint": short(e) + BLOCK_SOLUTIONS})
                    return summary
                st.cdp_mode = True
                ok("متصل شد — از همین مرورگر و نشست واقعی شما استفاده می‌کنیم.")
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                install_dialog_guard(page)
            else:
                launch_kwargs = {"headless": st.headless}
                if bcfg.get("channel"):
                    launch_kwargs["channel"] = bcfg["channel"]   # مثلا "chrome" یا "msedge"
                if bcfg.get("proxy"):
                    launch_kwargs["proxy"] = bcfg["proxy"]
                browser = p.chromium.launch(**launch_kwargs)
                ex = cfg.get("extraction", {})
                ctx_kwargs = {
                    "viewport": {"width": int(ex.get("viewport_width", 1366)),
                                 "height": int(ex.get("viewport_height", 900))},
                    "locale": "fa-IR",
                }
                # UA واقعی کروم ویندوزی — مرورگر خودکار را در برابر فیلترهای UA شفاف‌تر می‌کند
                if bcfg.get("user_agent"):
                    ctx_kwargs["user_agent"] = bcfg["user_agent"]
                if use_session:
                    ctx_kwargs["storage_state"] = sess_file
                ctx = browser.new_context(**ctx_kwargs)
                page = ctx.new_page()
                install_dialog_guard(page)
                # صفحات تازه‌ای که بعداً باز می‌شوند (target=_blank) هم محافظت شوند
                try:
                    ctx.on("page", install_dialog_guard)
                except Exception:
                    pass

            st.start_urls = starts
            st.host = urlsplit(norm(starts[0])).netloc.lower()

            # ضبط پاسخ‌های JSON درخواست‌های AJAX سایت (API واقعی داده)
            attach_api_capture(page, st)

            first = starts[0]
            info(f"بررسی نشست: {first}")
            goto(page, first, st.timeout)
            if is_block_page(page):
                err("شروع کار ممکن نشد: این صفحه توسط فایروال/فیلتر سازمانی مسدود شده است.")
                err("نکته: ممکن است فقط مرورگرِ خودکار مسدود شود و کروم معمولی شما رد شود.")
                print(BLOCK_SOLUTIONS)
                summary.update({"ok": False, "error": "blocked", "hint": BLOCK_SOLUTIONS})
                return summary
            if is_login_page(page):
                if use_session:
                    warn("سشن ذخیره‌شده منقضی شده است؛ ورود خودکار...")
                else:
                    info("لاگین لازم است.")
                if not do_login_flow(page, ctx, st):
                    summary.update({"ok": False, "error": "login_failed",
                                    "hint": "ورود انجام نشد؛ یوزر/پسورد را بررسی کنید یا از ورود دستی استفاده کنید."})
                    return summary
                goto(page, first, st.timeout)
                if is_block_page(page):
                    err("شروع کار ممکن نشد: این صفحه توسط فایروال/فیلتر سازمانی مسدود شده است.")
                    print(BLOCK_SOLUTIONS)
                    summary.update({"ok": False, "error": "blocked", "hint": BLOCK_SOLUTIONS})
                    return summary
                # اگر سامانه پس از ورود به صفحه دیگری منتقل شد (مثلا داشبورد)، آن هم خزیده شود
                if is_valid_http(page.url) and norm(page.url) != norm(first):
                    st.extra_starts.append(page.url)
            elif use_session:
                ok("سشن ذخیره‌شده معتبر است — بدون نیاز به لاگین ادامه می‌دهیم.")

            run(st, page, ctx)
            print_summary(st)
            summary["msgs"] = export_data(st)
            for m in summary["msgs"]:
                ok(m)
            summary["pages"] = db.execute("SELECT COUNT(DISTINCT url) FROM pages").fetchone()[0]
            summary["tables"] = db.execute("SELECT COUNT(*) FROM html_tables").fetchone()[0]
            summary["rows"] = db.execute("SELECT COUNT(*) FROM table_rows").fetchone()[0]
            summary["texts"] = db.execute("SELECT COUNT(*) FROM page_texts").fetchone()[0]
            summary["links"] = db.execute("SELECT COUNT(*) FROM links").fetchone()[0]
            if not st.cdp_mode:
                try:
                    ctx.close()
                    browser.close()
                except Exception:
                    pass
            if st.abort_reason:
                summary["ok"] = False
                summary["error"] = st.abort_reason
        return summary
    except Exception as e:
        summary["ok"] = False
        summary["error"] = "exception"
        summary["hint"] = short(e, 300)
        err(f"خطای غیرمنتظره: {short(e, 300)}")
        return summary
    finally:
        sys.stdout = _old_stdout
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
        if _log_f is not None:
            try:
                _log_f.close()
            except Exception:
                pass

if __name__ == "__main__":
    main()
