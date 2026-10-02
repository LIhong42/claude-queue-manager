#!/usr/bin/env bash
# ============================================================================
# Claude Queue Manager - CLI 任务提交工具 (Linux / macOS / Git Bash for Windows)
# ============================================================================
# 用法:
#   ./cli/add.sh "prompt text"                         # 立即加入队列
#   ./cli/add.sh "prompt text" "2026-10-02 15:30:00"   # 指定时间执行
#   ./cli/add.sh -f prompt.txt                         # 从文件读取 prompt
#   ./cli/add.sh -f prompt.txt "2026-10-02 15:30:00"   # 从文件 + 定时
#
# 环境变量 (覆盖默认值):
#   HOST             后端服务 host       默认 127.0.0.1
#   PORT             后端服务 port       默认 8000
#   BASE_URL         直接指定完整 base   默认 http://$HOST:$PORT
#   HEALTH_TIMEOUT   健康检查超时(秒)     默认 2
#   POST_TIMEOUT     提交超时(秒)         默认 15
#
# 时间格式: 本脚本接受 "YYYY-MM-DD HH:MM[:SS]" 或 "YYYY-MM-DDTHH:MM[:SS]"，
#           视为 *本地时区* 提交；后端会原样存入 DB。如果你需要 UTC，请使用
#           ISO 8601 带时区后缀 (例如 "2026-10-02T15:30:00+08:00")。
#
# 示例:
#   ./cli/add.sh "review this code"
#   ./cli/add.sh "nightly build"  "2026-10-02 23:00"
#   ./cli/add.sh -f task.txt
#   BASE_URL=http://192.168.1.10:8000 ./cli/add.sh "remote" "2026-10-02 18:30"
# ============================================================================

set -euo pipefail

usage() {
    sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

PROMPT=""
SCHEDULED_AT=""
USE_FILE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage 0 ;;
        -f|--file)
            [[ $# -ge 2 ]] || { usage 1; }
            USE_FILE=1
            PROMPT="$2"
            shift 2 ;;
        --)
            shift
            break ;;
        -*)
            echo "未知参数: $1" >&2
            usage 1 ;;
        *)
            if [[ -z "$PROMPT" ]]; then
                PROMPT="$1"
                shift
            elif [[ -z "$SCHEDULED_AT" ]]; then
                SCHEDULED_AT="$1"
                shift
            else
                echo "参数过多: $1" >&2
                usage 1
            fi
            ;;
    esac
done

if [[ -z "$PROMPT" ]]; then
    echo "错误: 未提供任务内容" >&2
    usage 1
fi

if [[ "$USE_FILE" == "1" ]]; then
    if [[ ! -f "$PROMPT" ]]; then
        echo "错误: 文件不存在 - $PROMPT" >&2
        exit 1
    fi
    PROMPT="$(cat "$PROMPT")"
fi

if [[ -z "$PROMPT" ]]; then
    echo "错误: prompt 为空" >&2
    exit 1
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
BASE_URL="${BASE_URL:-http://$HOST:$PORT}"

# 校验后端连接是否可达
if ! command -v curl >/dev/null 2>&1; then
    echo "错误: 缺少 curl，请先安装 curl" >&2
    exit 1
fi
# Prefer `python` over `python3` to avoid the broken WindowsApps stub on some Windows setups.
if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    echo "错误: 缺少 python 或 python3" >&2
    exit 1
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
BASE_URL="${BASE_URL:-http://$HOST:$PORT}"

# 快速健康检查：连接失败立即报错（避免后端未启动时挂起）
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-2}"
HEALTH_URL="$BASE_URL/api/tasks"
HEALTH_RESP="$(curl -fsS --max-time "$HEALTH_TIMEOUT" "$HEALTH_URL" 2>/dev/null)" || {
    HEALTH_RC=$?
    if [ "$HEALTH_RC" -eq 7 ] || [ "$HEALTH_RC" -eq 28 ] || [ "$HEALTH_RC" -eq 52 ]; then
        echo "错误: 后端服务不可达: $BASE_URL" >&2
        echo "      请确认后端已经启动 (cd backend && python -m app)" >&2
        echo "      或通过环境变量 HOST/PORT/BASE_URL 指定正确的后端地址。" >&2
    else
        echo "错误: 后端健康检查失败 (curl rc=$HEALTH_RC)" >&2
    fi
    exit 1
}

# 使用 python 构造 JSON 负载，避免对 jq 的依赖
# 如果提供了 SCHEDULED_AT，使用 python 将 "YYYY-MM-DD HH:MM[:SS]" (无 TZ) 转成 ISO (按本地时区)
# 如果 SCHEDULED_AT 已经带时区后缀 (如 +08:00 / Z), 原样传给 python 解析。
PAYLOAD="$(
PROMPT="$PROMPT" \
SCHEDULED_AT="$SCHEDULED_AT" \
"$PYTHON_BIN" - <<'PY'
import json, os, sys
from datetime import datetime, timezone

prompt = os.environ["PROMPT"]
scheduled_raw = os.environ.get("SCHEDULED_AT", "") or ""

scheduled_iso = None
if scheduled_raw.strip():
    s = scheduled_raw.strip().replace("/", "-")
    # Already has tz suffix?
    has_tz = (
        s.endswith("Z")
        or "+" in s[10:]
        or (s.count("-") >= 3)  # crude check: includes a tz offset like +08:00 minus parsing
    )
    # Robust detection: any +HH:MM / -HH:MM in the last 6 chars
    tail = s[-6:]
    has_tz = s.endswith("Z") or (
        len(tail) == 6 and tail[0] in "+-" and tail[3] == ":"
    )
    try:
        if has_tz:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            # No timezone — treat as local time.
            dt = datetime.fromisoformat(s)
            dt = dt.astimezone()
    except ValueError as e:
        print(f"无法解析时间: {scheduled_raw!r}: {e}", file=sys.stderr)
        sys.exit(1)
    scheduled_iso = dt.astimezone(timezone.utc).isoformat()

print(json.dumps({"prompt": prompt, "scheduled_at": scheduled_iso}, ensure_ascii=False))
PY
)"

# 提交（带超时，避免后端挂起时无限等待）
POST_TIMEOUT="${POST_TIMEOUT:-15}"
RESP="$(curl -fsS --max-time "$POST_TIMEOUT" -X POST -H 'Content-Type: application/json' \
    -d "$PAYLOAD" "$BASE_URL/api/tasks" 2>&1)" || {
    POST_RC=$?
    if [ "$POST_RC" -eq 28 ]; then
        echo "提交失败: 后端 $POST_TIMEOUT 秒内未响应" >&2
    elif [ "$POST_RC" -eq 7 ] || [ "$POST_RC" -eq 52 ]; then
        echo "提交失败: 后端连接断开 $BASE_URL" >&2
    else
        echo "提交失败 (curl rc=$POST_RC): $RESP" >&2
    fi
    exit 1
}

# 解析响应
TASK_ID="$(printf '%s' "$RESP" | "$PYTHON_BIN" -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id",""))')"
TASK_STATUS="$(printf '%s' "$RESP" | "$PYTHON_BIN" -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status",""))')"

echo "✅ 已添加: $TASK_ID  (status=$TASK_STATUS)"
if [[ -n "$SCHEDULED_AT" ]]; then
    echo "   本地时间: $SCHEDULED_AT"
    echo "   UTC ISO : $(printf '%s' "$RESP" | "$PYTHON_BIN" -c 'import json,sys; d=json.load(sys.stdin); print(d.get("scheduled_at",""))')"
    echo "   备注: 仅在系统空闲 (无 RUNNING 任务) 时才会被 worker 领取。"
fi