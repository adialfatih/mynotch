@echo off
rem Jalankan notch. Notch yang masih jalan ditutup dulu, jadi file ini sekalian buat restart.
cd /d "%~dp0"
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*notch.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Wait-Process -Id $_.ProcessId -Timeout 3 -ErrorAction SilentlyContinue }"
start "" pythonw "%~dp0notch.py"
