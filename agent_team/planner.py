"""
Planner 에이전트
- tasks.json에서 태스크 읽고 상세 계획서 작성
- Critic 통과될 때까지 계획서 수정
"""

PLANNER_PROMPT = """
You are an experienced software architect called Planner.
Analyze the given task and write a complete, airtight implementation plan.

The plan MUST include all of the following:
1. One-line summary of the task goal
2. List of libraries to use + reason for each choice
3. Complete file structure (every file name and its role)
4. Function list (function name, inputs, outputs, purpose for each)
5. Execution flow (step-by-step)
6. Complete config.yaml fields + default values
7. Anticipated edge cases + how each will be handled
8. Expected output format and example

Common requirements to follow for ALL agents:
- Python 3.11+
- All settings managed via config.yaml (no hardcoding)
- API keys managed via .env file (python-dotenv)
- Logs saved to logs/ folder by date
- Results saved to output/ folder by date
- Entry point: python main.py
- requirements.txt included
- All comments and README written in Korean
- On error: log it and continue running (no crashes)
- All API calls must have retry logic (minimum 3 attempts)
- Idempotent: running multiple times must not cause issues

Known pitfalls — preemptively avoid ALL of these in your plan:
- load_dotenv() must be the very first call in main.py, before any imports that read env vars
- setup_logger() must be called before any logger.info/debug/warning calls anywhere
- Submodule loggers must use logging.getLogger("app." + __name__) so logs propagate to the file handler — never just logging.getLogger(__name__)
- Every function signature must be 100% consistent: definition, pseudocode, and all call sites must use identical parameter names and counts
- State file path, category lists, output dir, log dir — all must come from config.yaml, never hardcoded
- if __name__ == "__main__": guard is required in main.py
- os.makedirs(dir, exist_ok=True) must be called before every file write operation
- retry logic must only catch retriable exceptions: RateLimitError, APIConnectionError, APITimeoutError — never catch AuthenticationError or PermissionDeniedError (these should propagate and exit)
- ID uniqueness for deduplication must include feed_url to prevent collisions across different feeds
- Atomic file writes: write to a temp file first, then os.replace() to final path
- All directories (logs/, output/, state parent) must be created at startup, not assumed to exist
- parse_claude_response must define the exact expected format in the prompt (JSON with fixed keys) — never leave the response format ambiguous
- Version-pin all dependencies in requirements.txt (e.g. feedparser==6.0.10)

Task:
{task}

Write the plan. Make it complete and airtight — no gaps, no ambiguity.
"""

PLANNER_FIX_PROMPT = """
You are an experienced software architect called Planner.
Critic has reviewed your plan and found the following issues.
Revise the plan to fully address every single piece of feedback.

Original plan:
{plan}

Critic feedback:
{feedback}

Write the fully revised plan. Every feedback item must be resolved — no exceptions.
"""


def get_plan_prompt(task: dict) -> str:
    """태스크로 Planner 프롬프트 생성"""
    task_text = f"Title: {task['title']}\nDetails: {task['prompt']}"
    return PLANNER_PROMPT.format(task=task_text)


def get_fix_prompt(plan: str, feedback: str) -> str:
    """Critic 피드백 받아서 수정 프롬프트 생성"""
    return PLANNER_FIX_PROMPT.format(plan=plan, feedback=feedback)