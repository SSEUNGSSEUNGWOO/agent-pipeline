#!/bin/bash
cd "$(dirname "$0")"

LOCK_FILE="/tmp/agents_orchestrator.lock"

if [ -f "$LOCK_FILE" ] && kill -0 "$(cat $LOCK_FILE)" 2>/dev/null; then
    exit 0
fi
echo $$ > "$LOCK_FILE"
trap "rm -f $LOCK_FILE" EXIT

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] orchestrator 시작"
    python orchestrator.py

    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 모든 태스크 완료. 종료."
        break
    fi

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 비정상 종료 (exit $EXIT_CODE) → 10초 후 재시작"
    sleep 10
done
