@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Personal-Agent launcher (stable, debug-friendly)
REM Usage:
REM   run.bat           -> start Streamlit
REM   run.bat --check   -> env/cert/deps checks only, then exit

cd /d "%~dp0"

set "MODE=%~1"
if /i "%MODE%"=="--help" goto :help
if /i "%MODE%"=="-h" goto :help

REM 1) venv must exist first (so we can use python-dotenv)
if not exist "venv\Scripts\python.exe" (
  echo [ERROR] Missing venv\Scripts\python.exe
  echo        Create venv then install deps:
  echo        py -3.11 -m venv venv
  echo        venv\Scripts\pip install -r requirements.txt
  exit /b 1
)

REM 2) .env must exist
if not exist ".env" (
  echo [ERROR] Missing .env
  echo        copy .env.example .env
  exit /b 1
)

REM 3) Load .env into current CMD process via generated SET script
set "_ENV_CMD=%TEMP%\personal_agent_env_%RANDOM%%RANDOM%.cmd"
venv\Scripts\python scripts\env_to_cmd.py ".env" "%_ENV_CMD%"
if errorlevel 1 (
  echo [ERROR] Failed to parse .env
  exit /b 1
)
call "%_ENV_CMD%"
del /q "%_ENV_CMD%" >nul 2>&1

REM 4) Map DEEPSEEK_* -> OPENAI_* (override)
if not "%DEEPSEEK_API_KEY%"=="" set "OPENAI_API_KEY=%DEEPSEEK_API_KEY%"
if not "%DEEPSEEK_BASE_URL%"=="" set "OPENAI_BASE_URL=%DEEPSEEK_BASE_URL%"

REM 5) Sanitize bogus CA env (like $ca)
if not "%SSL_CERT_FILE%"=="" if "%SSL_CERT_FILE:~0,1%"=="$" set "SSL_CERT_FILE="
if not "%SSL_CERT_DIR%"=="" if "%SSL_CERT_DIR:~0,1%"=="$" set "SSL_CERT_DIR="
if not "%REQUESTS_CA_BUNDLE%"=="" if "%REQUESTS_CA_BUNDLE:~0,1%"=="$" set "REQUESTS_CA_BUNDLE="
if not "%CURL_CA_BUNDLE%"=="" if "%CURL_CA_BUNDLE:~0,1%"=="$" set "CURL_CA_BUNDLE="

REM 6) Default SSL verify
if "%OPENAI_SSL_VERIFY%"=="" set "OPENAI_SSL_VERIFY=1"

REM 7) Optional Watt CA
if not "%WATT_CA_CERT%"=="" (
  set "WATT_CA_CERT_PATH=%WATT_CA_CERT:"=%"
  if exist "!WATT_CA_CERT_PATH!" (
    if not exist "data\certs" mkdir "data\certs" >nul 2>&1
    set "WATT_CA_PEM=%cd%\data\certs\watt-ca.pem"
    venv\Scripts\python scripts\prepare_ca_bundle.py "!WATT_CA_CERT_PATH!" "!WATT_CA_PEM!" >nul 2>&1
    if not exist "!WATT_CA_PEM!" (
      certutil -encode "!WATT_CA_CERT_PATH!" "!WATT_CA_PEM!" >nul 2>&1
    )
    if exist "!WATT_CA_PEM!" (
      set "SSL_CERT_FILE=!WATT_CA_PEM!"
      set "REQUESTS_CA_BUNDLE=!WATT_CA_PEM!"
      set "CURL_CA_BUNDLE=!WATT_CA_PEM!"
    )
  )
)

REM 8) Dependency sanity check (and optional install)
venv\Scripts\python -c "import streamlit, chromadb, langchain" >nul 2>&1
if errorlevel 1 (
  echo [INFO] Installing requirements...
  venv\Scripts\pip install -r requirements.txt --retries 10 --timeout 120
  if errorlevel 1 (
    echo [ERROR] pip install failed
    exit /b 1
  )
)

REM 9) Check-only mode
if /i "%MODE%"=="--check" (
  echo [OK] check passed
  exit /b 0
)

REM 10) Start Streamlit
echo [OK] Starting Streamlit...
venv\Scripts\python -m streamlit run app\streamlit_app.py
exit /b %errorlevel%

:help
echo Usage:
echo   run.bat           ^(start Streamlit^)
echo   run.bat --check   ^(env/cert/deps checks only^)
exit /b 0

