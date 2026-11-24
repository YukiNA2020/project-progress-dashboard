@echo off
rem Business Dashboard launcher.
rem Kept ASCII-only on purpose: a .bat with Chinese text breaks on codepage 936.
pushd "%~dp0.."
if not exist "data" mkdir "data"

set "PY="

py -3 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3"

if not defined PY (
  python --version >nul 2>nul
  if not errorlevel 1 set "PY=python"
)

if not defined PY (
  for /d %%D in ("C:\Python3*") do (
    if exist "%%D\python.exe" set "PY=%%D\python.exe"
  )
)

if not defined PY (
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
)

if not defined PY (
  if exist "%USERPROFILE%\anaconda3\python.exe" set "PY=%USERPROFILE%\anaconda3\python.exe"
  if exist "%USERPROFILE%\miniconda3\python.exe" set "PY=%USERPROFILE%\miniconda3\python.exe"
  if exist "C:\ProgramData\anaconda3\python.exe" set "PY=C:\ProgramData\anaconda3\python.exe"
)

if not defined PY goto NOPY

%PY% -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
  echo Python found. Installing three packages, one moment...
  %PY% -m pip install --quiet fastapi uvicorn pydantic >> "data\start.log" 2>&1
  %PY% -c "import fastapi, uvicorn" >nul 2>nul
  if errorlevel 1 goto NODEPS
)

echo.
echo   Business Dashboard
echo   Closing this window stops the service. Your data is already saved.
echo.
%PY% run.py
goto END

:NOPY
echo.
echo   Python was not found on this machine.
echo.
echo   No problem - opening the offline version.
echo   Everything works, data stays in this browser.
echo   Use the Export button to keep a backup copy.
echo.
start "" "index.html"
pause
goto END

:NODEPS
echo.
echo   Python is here, but fastapi / uvicorn could not be installed
echo   (often a company proxy or permission issue).
echo.
echo   Opening the offline version instead.
echo.
start "" "index.html"
pause
goto END

:END
popd
