@echo off
rem Pasang atau update notch: ambil kode terbaru, pasang paket Python, lalu jalankan ulang.
cd /d "%~dp0"

if exist .git (
    echo == Ambil kode terbaru ==
    git pull
    if errorlevel 1 goto gagal
)

echo == Pasang paket Python ==
python -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto gagal

echo == Jalankan ulang notch ==
call "%~dp0jalankan.bat"
echo Selesai. Notch sudah jalan dengan versi terbaru.
timeout /t 3 >nul
exit /b 0

:gagal
echo.
echo Gagal. Baca pesan di atas.
pause
exit /b 1
