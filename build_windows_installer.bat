@echo off
setlocal EnableExtensions

set "ROOT_DIR=%~dp0"
pushd "%ROOT_DIR%" >nul || (
    echo [ERROR] Could not enter script directory: %ROOT_DIR%
    exit /b 1
)

call :resolve_python
if not defined PYTHON_EXE (
    echo [INFO] Python not found. Installing Python 3.12 with winget...
    call :install_python
    if errorlevel 1 exit /b %errorlevel%
    call :resolve_python
)

if not defined PYTHON_EXE (
    echo [ERROR] Python could not be resolved after install.
    echo [ERROR] Install Python 3.10+ manually and re-run this script.
    exit /b 1
)

if defined PYTHON_ARGS (
    echo [INFO] Using Python: "%PYTHON_EXE%" %PYTHON_ARGS%
) else (
    echo [INFO] Using Python: "%PYTHON_EXE%"
)

set "VENV_DIR=%ROOT_DIR%.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [INFO] Creating virtual environment in: %VENV_DIR%
    call :run_python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Virtual environment creation failed.
        exit /b %errorlevel%
    )
)

echo [INFO] Upgrading pip and installing required packages...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 exit /b %errorlevel%

"%VENV_PY%" -m pip install -e ".[build-exe,runtime-v2]"
if errorlevel 1 exit /b %errorlevel%

echo [INFO] Cleaning previous build outputs...
if exist "%ROOT_DIR%build" rd /s /q "%ROOT_DIR%build"
if exist "%ROOT_DIR%dist" rd /s /q "%ROOT_DIR%dist"

echo [INFO] Building BranchNexus.exe with PyInstaller...
"%VENV_PY%" -m PyInstaller --clean --noconfirm packaging\branchnexus-gui.spec
if errorlevel 1 exit /b %errorlevel%

if not exist "%ROOT_DIR%dist\BranchNexus.exe" (
    echo [ERROR] Build output not found: dist\BranchNexus.exe
    exit /b 1
)

if exist "%ROOT_DIR%build" rd /s /q "%ROOT_DIR%build"

echo.
echo Build completed successfully.
echo Output: dist\BranchNexus.exe
exit /b 0

:resolve_python
set "PYTHON_EXE="
set "PYTHON_ARGS="

where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        set "PYTHON_ARGS=-3"
        goto :eof
    )
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
        set "PYTHON_ARGS="
        goto :eof
    )
)

for %%P in (
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%LocalAppData%\Programs\Python\Python311\python.exe"
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python311\python.exe"
) do (
    if exist "%%~P" (
        set "PYTHON_EXE=%%~P"
        set "PYTHON_ARGS="
        goto :eof
    )
)

goto :eof

:run_python
if defined PYTHON_ARGS (
    "%PYTHON_EXE%" %PYTHON_ARGS% %*
) else (
    "%PYTHON_EXE%" %*
)
exit /b %errorlevel%

:install_python
where winget >nul 2>&1
if errorlevel 1 (
    echo [ERROR] winget was not found.
    echo [ERROR] Install Python manually, then run this script again.
    exit /b 1
)

winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent
if errorlevel 1 (
    echo [ERROR] Python installation failed via winget.
    exit /b %errorlevel%
)

exit /b 0
