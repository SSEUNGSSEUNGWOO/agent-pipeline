#!/bin/bash
set -e

pip install lxml==5.2.2 --no-binary lxml || {
    echo "[install.sh] lxml 바이너리 빌드 실패. html.parser 대체 사용 권고."
    echo "[install.sh] config.yaml의 http.bs_parser를 'html.parser'로 변경하고 계속하거나 Ctrl+C로 중단하세요."

    # macOS BSD mktemp 호환: suffix 없이 X-블록으로만 끝나는 템플릿 사용
    TMPFILE=$(mktemp /tmp/requirements_nolxml.XXXXXX)
    grep -v '^lxml' requirements.txt > "$TMPFILE"
    pip install -r "$TMPFILE"
    rm -f "$TMPFILE"
    exit 0
}

pip install -r requirements.txt
