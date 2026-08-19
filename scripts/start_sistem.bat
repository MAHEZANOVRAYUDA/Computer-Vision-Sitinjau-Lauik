@echo off
REM =====================================================================
REM start_sistem.bat
REM Script untuk menjalankan seluruh stack Sitinjau Lauik CV di Windows.
REM
REM Cara pakai (dari root folder proyek, dengan venv aktif):
REM     scripts\start_sistem.bat
REM
REM Urutan startup:
REM   1. Cek MQTT broker (Mosquitto) sudah berjalan
REM   2. Jalankan API Server (background window)
REM   3. Jalankan MQTT Consumer (background window)
REM   4. Jalankan Edge Detector / main.py (foreground di window ini)
REM =====================================================================

setlocal

echo.
echo ======================================================================
echo  SITINJAU LAUIK CV SYSTEM - Startup Script (Windows)
echo ======================================================================
echo.

REM --- Cek Python tersedia ---
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python tidak ditemukan di PATH.
    echo         Aktifkan virtual environment terlebih dahulu:
    echo         venv\Scripts\activate
    pause
    exit /b 1
)

REM --- Cek file config ada ---
if not exist "config\config.yaml" (
    echo [ERROR] File config\config.yaml tidak ditemukan.
    echo         Pastikan Anda menjalankan script ini dari ROOT folder proyek
    echo         (folder yang berisi folder 'config\', 'src\', dll.)
    pause
    exit /b 1
)

REM --- Cek MQTT Broker (Mosquitto) ---
echo [1/4] Memeriksa MQTT Broker (Mosquitto)...
netstat -an 2>nul | find "1883" | find "LISTENING" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARN] Port 1883 tidak terdeteksi LISTEN. Mosquitto mungkin belum berjalan.
    echo        Mencoba memulai Mosquitto...
    where mosquitto >nul 2>&1
    if %ERRORLEVEL% eq 0 (
        start /B "Mosquitto" mosquitto
        timeout /t 2 /nobreak >nul
        echo [OK]  Mosquitto dijalankan.
    ) else (
        echo [WARN] Mosquitto tidak ditemukan di PATH. Sistem tetap dijalankan,
        echo        tapi data MQTT tidak akan terkirim sampai broker aktif.
        echo        Install Mosquitto: https://mosquitto.org/download/
    )
) else (
    echo [OK]  MQTT Broker sudah berjalan di port 1883.
)

REM --- Buat folder logs jika belum ada ---
if not exist "data\logs" mkdir "data\logs"

REM --- Jalankan API Server di window baru ---
echo.
echo [2/4] Menjalankan API Server (http://localhost:8000)...
start "Sitinjau-API-Server" cmd /k "python src\api_server.py"
timeout /t 3 /nobreak >nul
echo [OK]  API Server berjalan.

REM --- Jalankan MQTT Consumer di window baru ---
echo [3/4] Menjalankan MQTT Consumer...
start "Sitinjau-MQTT-Consumer" cmd /k "python src\mqtt_consumer.py"
timeout /t 2 /nobreak >nul
echo [OK]  MQTT Consumer berjalan.

REM --- Buka dashboard di browser ---
echo [4/4] Membuka dashboard di browser...
timeout /t 1 /nobreak >nul
start "" "http://localhost:8000"

echo.
echo ======================================================================
echo  Semua proses berjalan. Menjalankan Edge Detector di window ini.
echo  Tekan Ctrl+C atau 'q' pada jendela video untuk menghentikan.
echo ======================================================================
echo.

REM --- Jalankan Edge Detector di window ini (foreground) ---
python src\main.py %*

echo.
echo [INFO] Edge Detector dihentikan.
echo [INFO] Tutup window API Server dan MQTT Consumer secara manual jika perlu.
pause
