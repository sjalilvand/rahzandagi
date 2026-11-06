# ==================================================================
# سایت‌کاو نسخه ۴ — اجرای وب‌اپ یکپارچه (نمایش داده‌ها + شروع خزش)
# آدرس پس از اجرا:  http://127.0.0.1:5002
#
# روش اجرا:
#   1) در PowerShell:   powershell -ExecutionPolicy Bypass -File start-web.ps1
#   2) یا راست‌کلیک روی همین فایل → «Run with PowerShell»
#
# پارامترها همین‌طور پاس داده می‌شوند، مثلاً:
#   start-web.ps1 --host 0.0.0.0 --port 5002     (دسترسی از گوشی/رایانه دیگر شبکه)
#   start-web.ps1 --no-browser                   (باز شدن خودکار مرورگر خاموش)
#   start-web.ps1 --db "D:\مسیر\site_data.db"    (انتخاب دستی دیتابیس)
# ==================================================================

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# --- پایتون نصب است؟
try { $null = python --version } catch {
    Write-Host ""
    Write-Host "[خطا] پایتون پیدا نشد — ابتدا پایتون را از python.org نصب کنید." -ForegroundColor Red
    Read-Host "برای بستن Enter بزنید"
    exit 1
}

# --- پیش‌نیازها (فقط بار اول نصب می‌شود)
python -c "import flask, playwright, openpyxl" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[نصب] پیش‌نیازها برای بار اول در حال نصب است..." -ForegroundColor Cyan
    pip install -r requirements.txt
    python -m playwright install chromium
}

Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host "  سایت‌کاو — وب‌اپ یکپارچه (نسخه ۴)" -ForegroundColor Green
Write-Host "  آدرس:  http://127.0.0.1:5002" -ForegroundColor Green
Write-Host "  برای بستن برنامه: Ctrl+C" -ForegroundColor Yellow
Write-Host "==================================================" -ForegroundColor Green
Write-Host ""

python viewer.py @args

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[خطا] برنامه با مشکل متوقف شد — متن بالا را ببینید." -ForegroundColor Red
}
Read-Host "برای بستن پنجره Enter بزنید"
