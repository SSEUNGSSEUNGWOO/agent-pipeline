"""
Logger 에이전트
- 완성된 에이전트를 completed/ 폴더에 저장
- tasks.json 상태 업데이트
- 전체 진행 기록 관리
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

LOGGER_PROMPT = """
You are a meticulous Logger.
Archive the completed agent into the completed/ folder.

Steps to follow in order:
1. Move in_progress/{agent_name}/ to completed/{agent_name}/
2. Review completed/{agent_name}/README.md for completeness (installation, execution, config docs)
3. Run python main.py from completed/{agent_name}/ to confirm it still works
4. If everything is clean, report completion

Agent name: {agent_name}
Base directory: {base_dir}

Execute each step in order. Report any issues found.
"""

LOGGER_FIX_PROMPT = """
You are a meticulous Logger.
Critic found issues with the saved agent. Fix them now.

Agent path: completed/{agent_name}/

Issues to fix:
{feedback}

Fix every issue listed above. Then confirm all files are present and python main.py runs correctly.
"""


def get_log_prompt(agent_name: str, base_dir: str) -> str:
    """Logger 프롬프트 생성"""
    return LOGGER_PROMPT.format(agent_name=agent_name, base_dir=base_dir)


def get_log_fix_prompt(agent_name: str, feedback: str) -> str:
    """Logger 수정 프롬프트 생성"""
    return LOGGER_FIX_PROMPT.format(agent_name=agent_name, feedback=feedback)


def update_task_status(tasks_path: str, task_id: int, status: str):
    """tasks.json에서 태스크 상태 업데이트"""
    with open(tasks_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for task in data['tasks']:
        if task['id'] == task_id:
            task['status'] = status
            task['updated_at'] = datetime.now().isoformat()
            break

    with open(tasks_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_next_task(tasks_path: str) -> dict | None:
    """다음 todo 태스크 반환"""
    with open(tasks_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for task in data['tasks']:
        if task['status'] == 'todo':
            return task
    return None


def log_progress(log_path: str, message: str):
    """진행 상황 로그 기록"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] {message}\n"

    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(log_entry)

    print(log_entry.strip())