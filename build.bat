@echo off
chcp 65001 >nul
echo ================================
echo Building YouTube Claim Checker
echo (with embedded Tesseract OCR)
echo ================================
echo.

REM Check if Tesseract is installed
echo [0/6] Checking Tesseract installation...
set "TESSERACT_PATH=C:\Program Files\Tesseract-OCR"
if not exist "%TESSERACT_PATH%\tesseract.exe" (
    echo ❌ Tesseract not found at: %TESSERACT_PATH%
    echo.
    echo Please install Tesseract first:
    echo https://github.com/UB-Mannheim/tesseract/wiki
    echo.
    echo Or update TESSERACT_PATH in this script if installed elsewhere.
    pause
    exit /b 1
)
echo ✓ Found Tesseract at: %TESSERACT_PATH%
echo.

REM Clean previous build
echo [1/6] Cleaning old builds...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "*.spec" del /q "*.spec"
if exist "YouTube Claim Checker V3.8.9.exe" del /q "YouTube Claim Checker V3.8.9.exe"
echo Done!
echo.

REM Install required packages
echo [2/6] Checking dependencies...
pip install --quiet pyinstaller mutagen pillow pytesseract
echo Done!
echo.

REM Build executable with Tesseract embedded
echo [3/6] Building executable with embedded Tesseract...
echo This will take several minutes, please wait...
echo.
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "YouTube Claim Checker V3.8.9" ^
    --add-binary "%TESSERACT_PATH%\tesseract.exe;tesseract" ^
    --add-data "%TESSERACT_PATH%\tessdata;tessdata" ^
    --hidden-import=PIL ^
    --hidden-import=PIL._imagingtk ^
    --hidden-import=PIL._tkinter_finder ^
    --hidden-import=pytesseract ^
    --exclude-module torch ^
    --exclude-module tensorflow ^
    --exclude-module pandas ^
    --exclude-module numpy ^
    --exclude-module scipy ^
    --exclude-module matplotlib ^
    --exclude-module cv2 ^
    --exclude-module sklearn ^
    --exclude-module pytest ^
    --noupx ^
    --clean ^
    claim_checker_v3.8.9.py

if %errorlevel% neq 0 (
    echo.
    echo ❌ Build FAILED!
    echo Check the error messages above.
    pause
    exit /b 1
)
echo Done!
echo.

REM Move exe to current directory
echo [4/6] Moving executable...
if exist "dist\YouTube Claim Checker V3.8.9.exe" (
    move "dist\YouTube Claim Checker V3.8.9.exe" "YouTube Claim Checker V3.8.9.exe" >nul
    echo Done!
) else (
    echo ❌ Executable not found!
    pause
    exit /b 1
)
echo.

REM Clean up
echo [5/6] Cleaning temporary files...
rmdir /s /q "build" 2>nul
rmdir /s /q "dist" 2>nul
del /q "*.spec" 2>nul
echo Done!
echo.

REM Get file size
echo [6/6] Build information...
for %%A in ("YouTube Claim Checker V3.8.9.exe") do (
    set size=%%~zA
    set /a sizeMB=!size! / 1048576
)
echo File: YouTube Claim Checker V3.8.9.exe
echo Size: ~%sizeMB% MB
echo.

echo ================================
echo ✅ BUILD SUCCESSFUL!
echo ================================
echo.
echo ✓ Tesseract OCR is embedded in the EXE
echo ✓ No need to install Tesseract on target PC
echo ✓ EXE is portable and ready to distribute
echo.

pause