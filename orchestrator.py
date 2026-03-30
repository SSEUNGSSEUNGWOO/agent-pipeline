"""
Orchestrator - 전체 에이전트 팀 관리
Claude Code에 각 에이전트 역할을 지시하고 루프를 관리한다.

실행: python orchestrator.py
"""

import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime

from agent_team.planner import get_plan_prompt, get_fix_prompt as get_plan_fix_prompt
from agent_team.critic import (
    get_plan_critic_prompt,
    get_code_critic_prompt,
    get_fix_critic_prompt,
    get_log_critic_prompt,
    parse_critic_result,
)
from agent_team.builder import get_build_prompt
from agent_team.fixer import get_fix_prompt as get_code_fix_prompt
from agent_team.logger import (
    get_log_prompt,
    get_log_fix_prompt,
    get_next_task,
    update_task_status,
    log_progress,
)

# 경로 설정
BASE_DIR = Path(__file__).parent
TASKS_PATH = BASE_DIR / "tasks.json"
IN_PROGRESS_DIR = BASE_DIR / "in_progress"
COMPLETED_DIR = BASE_DIR / "completed"
LOG_PATH = BASE_DIR / "logs" / f"orchestrator_{datetime.now().strftime('%Y%m%d')}.log"

IN_PROGRESS_DIR.mkdir(exist_ok=True)
COMPLETED_DIR.mkdir(exist_ok=True)


def run_claude(prompt: str) -> str:
    """
    Claude Code에 프롬프트 전달하고 응답 반환
    Claude Code CLI: claude -p "prompt"
    """
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        cwd=str(BASE_DIR)
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI 실패: {result.stderr}")
    return result.stdout


def phase_plan(task: dict) -> str:
    """
    Phase 1: Planner가 계획서 작성 → Critic 통과될 때까지 반복
    """
    log_progress(LOG_PATH, f"[PLANNER] 태스크 {task['id']}: {task['title']} 계획 시작")

    # 초기 계획서 작성
    prompt = get_plan_prompt(task)
    plan = run_claude(prompt)
    log_progress(LOG_PATH, "[PLANNER] 초기 계획서 작성 완료")

    iteration = 0
    while True:
        iteration += 1
        log_progress(LOG_PATH, f"[CRITIC] 계획서 검토 #{iteration}")

        # Critic이 계획서 검토
        critic_prompt = get_plan_critic_prompt(plan)
        critic_response = run_claude(critic_prompt)
        passed, feedback = parse_critic_result(critic_response)

        if passed:
            log_progress(LOG_PATH, f"[CRITIC] 계획서 통과 (#{iteration}회)")
            return plan

        log_progress(LOG_PATH, f"[CRITIC] 계획서 FAIL → Planner 수정 요청\n{feedback}")

        # Planner가 피드백 반영해서 수정
        fix_prompt = get_plan_fix_prompt(plan, feedback)
        plan = run_claude(fix_prompt)
        log_progress(LOG_PATH, f"[PLANNER] 계획서 수정 완료 (#{iteration}회)\n{plan[:200]}")


def phase_build(task: dict, plan: str) -> Path:
    """
    Phase 2: Builder가 코드 작성 → Critic 통과될 때까지 반복
    """
    agent_name = f"{task['id']:02d}_{task['title'].replace(' ', '_')}"
    work_dir = IN_PROGRESS_DIR / agent_name
    work_dir.mkdir(exist_ok=True)

    log_progress(LOG_PATH, f"[BUILDER] 코드 작성 시작 → {work_dir}")

    # 초기 코드 작성
    build_prompt = get_build_prompt(plan, str(work_dir))
    build_output = run_claude(build_prompt)
    log_progress(LOG_PATH, f"[BUILDER] 초기 코드 작성 완료\n{build_output[:200]}")

    iteration = 0
    feedback = ""

    while True:
        iteration += 1
        log_progress(LOG_PATH, f"[CRITIC] 코드 검토 #{iteration}")

        # Critic이 코드 검토 (실제 실행 포함)
        if iteration == 1:
            critic_prompt = get_code_critic_prompt(str(work_dir))
        else:
            critic_prompt = get_fix_critic_prompt(feedback, str(work_dir))

        critic_response = run_claude(critic_prompt)
        passed, feedback = parse_critic_result(critic_response)

        if passed:
            log_progress(LOG_PATH, f"[CRITIC] 코드 통과 (#{iteration}회)")
            return work_dir

        log_progress(LOG_PATH, f"[CRITIC] 코드 FAIL → Fixer 수정 요청\n{feedback}")

        # Fixer가 피드백 반영해서 수정
        fix_prompt = get_code_fix_prompt(str(work_dir), feedback)
        fix_output = run_claude(fix_prompt)
        log_progress(LOG_PATH, f"[FIXER] 코드 수정 완료 (#{iteration}회)\n{fix_output[:200]}")


def phase_log(task: dict, work_dir: Path):
    """
    Phase 3: Logger가 completed/에 저장 → Critic 통과될 때까지 반복
    """
    agent_name = work_dir.name
    log_progress(LOG_PATH, f"[LOGGER] 저장 시작 → completed/{agent_name}")

    # Logger가 저장
    log_prompt = get_log_prompt(agent_name, str(BASE_DIR))
    run_claude(log_prompt)
    log_progress(LOG_PATH, "[LOGGER] 저장 완료")

    iteration = 0
    while True:
        iteration += 1
        log_progress(LOG_PATH, f"[CRITIC] 저장 검토 #{iteration}")

        # Critic이 저장 결과 검토
        critic_prompt = get_log_critic_prompt(agent_name)
        critic_response = run_claude(critic_prompt)
        passed, feedback = parse_critic_result(critic_response)

        if passed:
            log_progress(LOG_PATH, f"[CRITIC] 저장 통과 (#{iteration}회)")
            break

        log_progress(LOG_PATH, f"[CRITIC] 저장 FAIL → Logger 재작업\n{feedback}")

        # Logger가 다시 수정
        fix_log_prompt = get_log_fix_prompt(agent_name, feedback)
        fix_log_output = run_claude(fix_log_prompt)
        log_progress(LOG_PATH, f"[LOGGER] 재저장 완료 (#{iteration}회)\n{fix_log_output[:200]}")

    # tasks.json 상태 업데이트
    update_task_status(str(TASKS_PATH), task['id'], 'done')
    log_progress(LOG_PATH, f"✅ 태스크 {task['id']} 완료: {task['title']}")


NEW_TASKS_PER_BATCH = 5


def generate_new_tasks():
    """기존 태스크와 겹치지 않는 새 에이전트 아이디어를 생성하고 tasks.json에 추가"""
    with open(TASKS_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    existing_titles = [t['title'] for t in data['tasks']]
    last_id = max(t['id'] for t in data['tasks'])

    existing_list = "\n".join(f"- {title}" for title in existing_titles)

    prompt = f"""You are a creative AI product designer.
The following Python agent projects have already been built:
{existing_list}

Generate {NEW_TASKS_PER_BATCH} NEW agent ideas that do NOT overlap with any of the above.
Each agent should be a standalone Python automation tool that is practical and portfolio-worthy.

For each idea, output EXACTLY this format (no extra text):
TITLE: <agent title in Korean>
PROMPT: <detailed description in Korean, including data sources, features, output format>
---

Output all {NEW_TASKS_PER_BATCH} ideas back to back."""

    log_progress(LOG_PATH, f"[IDEATOR] 새 태스크 {NEW_TASKS_PER_BATCH}개 생성 중...")
    response = run_claude(prompt)

    new_tasks = []
    current_id = last_id + 1
    for block in response.split("---"):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        title = ""
        prompt_lines = []
        in_prompt = False
        for line in lines:
            if line.startswith("TITLE:"):
                title = line.replace("TITLE:", "").strip()
            elif line.startswith("PROMPT:"):
                in_prompt = True
                prompt_lines.append(line.replace("PROMPT:", "").strip())
            elif in_prompt:
                prompt_lines.append(line.strip())
        if title and prompt_lines:
            new_tasks.append({
                "id": current_id,
                "title": title,
                "status": "todo",
                "prompt": " ".join(prompt_lines)
            })
            current_id += 1

    if not new_tasks:
        log_progress(LOG_PATH, "[IDEATOR] 새 태스크 파싱 실패")
        return

    data['tasks'].extend(new_tasks)
    with open(TASKS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    titles = "\n".join(f"  - {t['title']}" for t in new_tasks)
    log_progress(LOG_PATH, f"[IDEATOR] {len(new_tasks)}개 추가됨:\n{titles}")


def run():
    """
    메인 루프 — todo 태스크가 없으면 새 아이디어 생성 후 계속 실행
    """
    log_progress(LOG_PATH, "=" * 50)
    log_progress(LOG_PATH, "🚀 Orchestrator 시작")
    log_progress(LOG_PATH, "=" * 50)

    completed_count = 0

    while True:
        # 다음 태스크 가져오기
        task = get_next_task(str(TASKS_PATH))

        if task is None:
            log_progress(LOG_PATH, "🎉 현재 태스크 모두 완료 → 새 아이디어 생성")
            generate_new_tasks()
            continue

        log_progress(LOG_PATH, f"\n{'='*50}")
        log_progress(LOG_PATH, f"📋 태스크 {task['id']}: {task['title']}")
        log_progress(LOG_PATH, f"{'='*50}")

        # 진행 중으로 상태 변경
        update_task_status(str(TASKS_PATH), task['id'], 'in_progress')

        try:
            # Phase 1: 계획
            plan = phase_plan(task)

            # Phase 2: 빌드
            work_dir = phase_build(task, plan)

            # Phase 3: 저장
            phase_log(task, work_dir)

            completed_count += 1
            log_progress(LOG_PATH, f"✅ 완료 누적: {completed_count}개")

        except Exception as e:
            log_progress(LOG_PATH, f"❌ 태스크 {task['id']} 실패: {e}")
            update_task_status(str(TASKS_PATH), task['id'], 'error')
            continue

    log_progress(LOG_PATH, f"\n총 완료: {completed_count}개")


if __name__ == "__main__":
    run()