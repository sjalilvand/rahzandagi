/* سایت‌کاو نمایشگر — جاوااسکریپت کمکی (بدون وابستگی) */
(function () {
  'use strict';

  /* ---------- پوسته‌ی روشن/تاریک ---------- */
  var btn = document.getElementById('themeBtn');
  var saved = null;
  try { saved = localStorage.getItem('cw-theme'); } catch (e) {}
  if (saved === 'light') document.documentElement.setAttribute('data-theme', 'light');
  function syncIcon() {
    if (!btn) return;
    var light = document.documentElement.getAttribute('data-theme') === 'light';
    btn.innerHTML = svg(light ? 'moon' : 'sun');
  }
  function svg(name) {
    var d = name === 'moon'
      ? '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>'
      : '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>';
    return '<svg class="ic sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + d + '</svg>';
  }
  if (btn) {
    syncIcon();
    btn.addEventListener('click', function () {
      var el = document.documentElement;
      var light = el.getAttribute('data-theme') === 'light';
      if (light) { el.removeAttribute('data-theme'); } else { el.setAttribute('data-theme', 'light'); }
      try { localStorage.setItem('cw-theme', light ? 'dark' : 'light'); } catch (e) {}
      syncIcon();
    });
  }

  /* ---------- دکمه‌های کپی ---------- */
  function copyText(t, done) {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(t).then(done, function () { fallback(); });
    } else { fallback(); }
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = t; ta.style.cssText = 'position:fixed;opacity:0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch (e) {}
      ta.remove(); if (done) done();
    }
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-copy]');
    if (!b) return;
    e.preventDefault();
    copyText(b.getAttribute('data-copy'), function () {
      var old = b.getAttribute('title') || '';
      b.style.color = '#10b981';
      setTimeout(function () { b.style.color = ''; }, 900);
    });
  });

  /* ---------- لایت‌باکس تصاویر ---------- */
  var lb = document.getElementById('lightbox');
  var lbImg = document.getElementById('lbImg');
  window.lbOpen = function (src) {
    if (!lb || !lbImg) return;
    lbImg.src = src;
    lb.classList.add('on');
  };
  window.lbFrom = function (ev, src) {
    ev.preventDefault();
    window.lbOpen(src);
  };
  window.lbClose = function () {
    if (lb) { lb.classList.remove('on'); lbImg.src = ''; }
  };
  if (lb) {
    lb.addEventListener('click', function (e) {
      if (e.target === lb) window.lbClose();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') window.lbClose();
    });
  }

  /* ---------- فیلتر سطح لاگ ---------- */
  var logFilter = document.getElementById('logFilter');
  if (logFilter) {
    var lines = document.querySelectorAll('#loglist .logline');
    logFilter.addEventListener('click', function (e) {
      var b = e.target.closest('.chipbtn');
      if (!b) return;
      logFilter.querySelectorAll('.chipbtn').forEach(function (x) { x.classList.remove('on'); });
      b.classList.add('on');
      var lv = b.getAttribute('data-lv');
      lines.forEach(function (l) {
        l.hidden = !!lv && l.getAttribute('data-lv') !== lv;
      });
    });
  }
})();
