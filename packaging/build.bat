@echo off
rem ThermoDrop build for Windows 7/10/11. Keep this file ASCII-only (cmd.exe limitation).
rem Requires Python 3.8: the build bitness (x64/x86) equals the Python bitness.
rem Usage:  packaging\build.bat [path\to\python.exe] [path\to\ISCC.exe]
rem Result: dist\<arch>\ThermoDrop\ (portable) and packaging\Output\ThermoDrop-<ver>-<arch>-setup.exe
setlocal
cd /d "%~dp0.."

set "PY=%~1"
if "%PY%"=="" set "PY=py -3.8"
set "ISCC=%~2"
if "%ISCC%"=="" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"

set "ARCH="
for /f %%a in ('%PY% -c "import struct; print('x64' if struct.calcsize('P') == 8 else 'x86')"') do set "ARCH=%%a"
if "%ARCH%"=="" goto :error
set "VENV=.venv38-%ARCH%"
echo === Architecture: %ARCH%, environment: %VENV%

if not exist "%VENV%\Scripts\python.exe" (
    %PY% -m venv "%VENV%" || goto :error
)
set "VPY=%VENV%\Scripts\python.exe"
"%VPY%" -m pip install --upgrade "pip<25" || goto :error
"%VPY%" -m pip install -r requirements-dev.txt || goto :error

echo === Tests
"%VPY%" -m pytest -q -p no:cacheprovider || goto :error

echo === User guide PDF
"%VPY%" packaging\make_guide.py || goto :error

echo === PyInstaller
"%VPY%" -m PyInstaller --noconfirm --clean --distpath "dist\%ARCH%" --workpath "build\%ARCH%" packaging\thermodrop.spec || goto :error

echo === Installer
if exist "%ISCC%" (
    rem Antivirus may briefly lock freshly built files: retry once after a pause.
    "%ISCC%" /Q /DArch=%ARCH% packaging\installer.iss || (
        echo Retrying in 15 s...
        ping -n 16 127.0.0.1 >nul
        "%ISCC%" /Q /DArch=%ARCH% packaging\installer.iss
    ) || goto :error
    echo Installer: packaging\Output\
) else (
    echo Inno Setup not found - installer skipped. Portable build: dist\%ARCH%\ThermoDrop\
)
echo === Done
exit /b 0

:error
echo *** BUILD FAILED
exit /b 1
