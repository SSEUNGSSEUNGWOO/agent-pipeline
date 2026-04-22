#!/bin/bash
set -e

pip install lxml==5.2.2 --no-binary lxml || {
    echo "[install.sh] lxml 바이너리 빌드 실패. html.parser 대체 사용 권고."
    echo "[install.sh] config.yaml의 http.bs_parser를 'html.parser'로 변경하고 계속하거나 Ctrl+C로 중단하세요."

    TMPFILE=$(mktemp /tmp/requirements_nolxml.XXXXXX.txt)
    grep -v '^lxml' requirements.txt > "$TMPFILE"
    pip install -r "$TMPFILE"
    rm -f "$TMPFILE"
    exit 0
}

pip install -r requirements.txt
