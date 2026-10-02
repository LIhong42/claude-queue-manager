@echo off
REM ============================================================================
REM Claude Queue Manager - CLI 任务提交工具 (Windows 原生批处理)
REM ============================================================================
REM 用法:
REM   cli\add.bat "prompt text"
REM   cli\add.bat "prompt text" "2026-10-02 15:30:00"
REM   cli\add.bat -f prompt.txt
REM   cli\add.bat -f prompt.txt "2026-10-02 15:30:00"
REM
REM 环境变量 (覆盖默认值):
REM   HOST         后端服务 host       默认 127.0.0.1
REM   PORT         后端服务 port       默认 8000
REM   BASE_URL     直接指定完整 base   默认 http://%HOST%:%PORT%
REM
REM 时间格式: 接受 "YYYY-MM-DD HH:MM[:SS]" 或 "YYYY-MM-DDTHH:MM[:SS]"，
REM           视为 *本地时区* 提交；后端会原样存入 DB。
REM           如果需要 UTC, 请使用 ISO 8601 带时区后缀,
REM           例如 "2026-10-02T15:30:00+08:00"。
REM
REM 示例:
REM   cli\add.bat "review this code"
REM   cli\add.bat "nightly build"  "2026-10-02 23:00"
REM   cli\add.bat -f task.txt
REM   set BASE_URL=http://192.168.1.10:8000 ^&^& cli\add.bat "remote" "2026-10-02 18:30"
REM ============================================================================

setlocal EnableDelayedExpansion

REM ---------- argument parsing ----------
set "PROMPT="
set "SCHEDULED_AT="
set "USE_FILE=0"

:parse_args
if "%~1"=="" goto :after_parse

if /i "%~1"=="-f" goto :set_file
if /i "%~1"=="--file" goto :set_file

if /i "%~1"=="-h" goto :help
if /i "%~1"=="--help" goto :help
if "%~1"=="/?" goto :help

if "%PROMPT%"=="" (
    set "PROMPT=%~1"
    shift
    goto :parse_args
)
if "%SCHEDULED_AT%"=="" (
    set "SCHEDULED_AT=%~1"
    shift
    goto :parse_args
)

echo 错误: 参数过多: %~1 1>&2
goto :help_err

:set_file
if "%~2"=="" (
    echo 错误: -f 后面需要文件路径 1>&2
    goto :help_err
)
set "USE_FILE=1"
set "PROMPT=%~2"
shift
shift
goto :parse_args

:after_parse

if "%PROMPT%"=="" (
    echo 错误: 未提供任务内容 1>&2
    goto :help_err
)

if "%USE_FILE%"=="1" (
    if not exist "%PROMPT%" (
        echo 错误: 文件不存在 - %PROMPT% 1>&2
        exit /b 1
    )
    set "PROMPT="
    for /f "usebackq delims=" %%i in ("%PROMPT%") do (
        set "PROMPT=!PROMPT!%%i"
    )
)

if "%PROMPT%"=="" (
    echo 错误: prompt 为空 1>&2
    exit /b 1
)

REM ---------- environment ----------
if "%HOST%"=="" set "HOST=127.0.0.1"
if "%PORT%"=="" set "PORT=8000"
if "%BASE_URL%"=="" set "BASE_URL=http://%HOST%:%PORT%"

where curl >nul 2>&1
if errorlevel 1 (
    echo 错误: 缺少 curl,请先安装 curl 1>&2
    exit /b 1
)
where python >nul 2>&1
if errorlevel 1 (
    echo 错误: 缺少 python,请先安装 Python 3 1>&2
    exit /b 1
)

REM ---------- build JSON payload via python ----------
set "PYTMP=%TEMP%\claude_queue_cli_%RANDOM%%RANDOM%.py"
(
    echo import json, os, sys
    echo from datetime import datetime, timezone
    echo.
    echo prompt = os.environ["PROMPT_RAW"]
    echo scheduled_raw = os.environ.get("SCHEDULED_AT_RAW", "") or ""
    echo.
    echo scheduled_iso = None
    echo if scheduled_raw.strip():
    echo     s = scheduled_raw.strip().replace("/", "-")
    echo     tail = s[-6:]
    echo     has_tz = s.endswith("Z") or (len(tail) == 6 and tail[0] in "+-" and tail[3] == ":")
    echo     try:
    echo         if has_tz:
    echo             dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    echo         else:
    echo             dt = datetime.fromisoformat(s)
    echo             dt = dt.astimezone()
    echo     except ValueError as e:
    echo         print("无法解析时间: " + repr(scheduled_raw) + ": " + str(e), file=sys.stderr)
    echo         sys.exit(1)
    echo     scheduled_iso = dt.astimezone(timezone.utc).isoformat()
    echo.
    echo print(json.dumps({"prompt": prompt, "scheduled_at": scheduled_iso}, ensure_ascii=False))
) > "%PYTMP%"

set "PROMPT_RAW=%PROMPT%"
set "SCHEDULED_AT_RAW=%SCHEDULED_AT%"
for /f "delims=" %%j in ('python "%PYTMP%"') do set "PAYLOAD=%%j"
del "%PYTMP%" >nul 2>&1

if "%PAYLOAD%"=="" (
    echo 错误: 无法构造 JSON payload 1>&2
    exit /b 1
)

REM ---------- health check (short timeout; bail out fast if backend is down) ----------
if "%HEALTH_TIMEOUT%"=="" set "HEALTH_TIMEOUT=2"
curl -fsS --max-time %HEALTH_TIMEOUT% "%BASE_URL%/api/tasks" >nul 2>&1
if errorlevel 1 (
    echo 错误: 后端服务不可达: %BASE_URL% 1>&2
    echo       请确认后端已经启动 (cd backend ^&^& python -m app^) 1>&2
    echo       或通过环境变量 HOST/PORT/BASE_URL 指定正确的后端地址。 1>&2
    exit /b 1
)

REM ---------- submit via curl ----------
if "%POST_TIMEOUT%"=="" set "POST_TIMEOUT=15"
set "RESPFILE=%TEMP%\claude_queue_resp_%RANDOM%%RANDOM%.txt"
curl -fsS --max-time %POST_TIMEOUT% -X POST -H "Content-Type: application/json" -d "%PAYLOAD%" "%BASE_URL%/api/tasks" > "%RESPFILE%" 2>&1
if errorlevel 1 (
    echo 提交失败: 1>&2
    type "%RESPFILE%" 1>&2
    del "%RESPFILE%" >nul 2>&1
    exit /b 1
)

echo --- 服务器响应:
type "%RESPFILE%"
echo.
del "%RESPFILE%" >nul 2>&1

if not "%SCHEDULED_AT%"=="" (
    echo.
    echo   本地时间: %SCHEDULED_AT%
    echo   备注: 仅在系统空闲 (无 RUNNING 任务) 时才会被 worker 领取。
)

exit /b 0

:help
echo.
echo 用法:
echo   %~nx0 "prompt text"
echo   %~nx0 "prompt text" "2026-10-02 15:30:00"
echo   %~nx0 -f prompt.txt
echo   %~nx0 -f prompt.txt "2026-10-02 15:30:00"
echo.
echo 环境变量:
echo   HOST             后端 host              默认 127.0.0.1
echo   PORT             后端 port              默认 8000
echo   BASE_URL         完整 base URL          默认 http://%HOST%:%PORT%
echo   HEALTH_TIMEOUT   健康检查超时(秒)         默认 2
echo   POST_TIMEOUT     提交超时(秒)             默认 15
exit /b 0

:help_err
echo. 1>&2
echo 用法: %~nx0 "prompt text" ["YYYY-MM-DD HH:MM:SS"] [-f prompt.txt] 1>&2
exit /b 1