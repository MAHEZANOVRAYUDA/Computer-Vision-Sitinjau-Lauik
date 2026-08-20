@echo off
echo ======================================================================
echo  SITINJAU LAUIK CV SYSTEM - Demo Mode (2 Kamera via Video File)
echo ======================================================================
echo.

REM --- Cek MQTT Broker (Mosquitto) ---
echo [1/5] Memeriksa MQTT Broker (Mosquitto)...
netstat -an 2>nul | find "1883" | find "LISTENING" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [WARN] Port 1883 tidak terdeteksi LISTEN. Mosquitto mungkin belum berjalan.
    echo        Mencoba memulai Mosquitto...
    where mosquitto >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Mosquitto tidak ditemukan di PATH.
    ) else (
        start "Mosquitto" mosquitto
        timeout /t 2 /nobreak >nul
        echo [OK]  Mosquitto dijalankan.
    )
) else (
    echo [OK]  MQTT Broker sudah berjalan di port 1883.
)

REM --- Buat folder logs jika belum ada ---
if not exist "data\logs" mkdir "data\logs"

REM --- Jalankan API Server di window baru ---
echo [2/5] Menjalankan API Server (http://localhost:8000)...
start "Sitinjau-API-Server" cmd /k "C:\Users\aseps\AppData\Local\Programs\Python\Python313\python.exe src\api_server.py"
timeout /t 3 /nobreak >nul

REM --- Jalankan MQTT Consumer di window baru ---
echo [3/5] Menjalankan MQTT Consumer...
start "Sitinjau-MQTT-Consumer" cmd /k "C:\Users\aseps\AppData\Local\Programs\Python\Python313\python.exe src\mqtt_consumer.py"
timeout /t 2 /nobreak >nul

REM --- Jalankan Edge Detector Gerbang A di window baru ---
echo [4/5] Menjalankan Edge Detector - Gerbang A...
start "Sitinjau-Edge-Gerbang-A" cmd /k "C:\Users\aseps\AppData\Local\Programs\Python\Python313\python.exe src\main.py --config config\config_gerbang_a.yaml"
timeout /t 3 /nobreak >nul

REM --- Jalankan Edge Detector Gerbang B di window baru ---
echo [5/5] Menjalankan Edge Detector - Gerbang B...
start "Sitinjau-Edge-Gerbang-B" cmd /k "C:\Users\aseps\AppData\Local\Programs\Python\Python313\python.exe src\main.py --config config\config_gerbang_b.yaml"

REM --- Buka dashboard di browser ---
echo [OK] Membuka dashboard di browser...
timeout /t 2 /nobreak >nul
start "" "http://localhost:8000"

echo.
echo ======================================================================
echo  Semua proses berjalan. 
echo  Periksa jendela cmd yang baru terbuka untuk melihat log.
echo  Window video (cv2) akan muncul dari masing-masing Edge Detector.
echo ======================================================================
pause
