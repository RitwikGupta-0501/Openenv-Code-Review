"""
Baseline inference script.
Runs an LLM agent (gpt-4o-mini by default) against all 3 tasks and reports scores.

Usage:
    OPENAI_API_KEY=sk-... python -m app.baseline
    OPENAI_API_KEY=sk-... BASELINE_MODEL=gpt-4o python -m app.baseline

The agent uses a simple ReAct-style loop:
  1. Receives the current observation
  2. Calls the LLM with a structured prompt
  3. Parses the JSON action from the response
  4. Steps the environment
  5. Repeats until done
"""

from __future__ import annotations
import json
import os
import sys
import time
import traceback
from openai import RateLimitError

from .models import Action, TaskName
from .env import CodeReviewEnv
from .tasks import TASKS

SYSTEM_PROMPT = """\
You are an expert software engineer performing a code review. You will be shown a pull request diff and must identify bugs, security vulnerabilities, and other issues.

You interact with the environment by responding with a single JSON object matching this schema:
{
  "action_type": one of ["flag_bug", "flag_security", "add_comment", "assign_reviewer", "request_changes", "approve", "skip"],
  "bug_category": one of ["logic_error", "null_pointer", "off_by_one", "race_condition", "memory_leak", "infinite_loop", "type_error", "unhandled_exception"] (required for flag_bug),
  "security_category": one of ["sql_injection", "xss", "hardcoded_secret", "path_traversal", "insecure_deserialization", "broken_auth", "sensitive_data_exposure", "command_injection"] (required for flag_security),
  "line_number": integer line number in the patch (required for flag_bug and flag_security),
  "severity": one of ["critical", "high", "medium", "low", "info"] (required for flag_bug and flag_security),
  "reviewer_role": one of ["backend", "frontend", "security", "devops", "senior"] (required for assign_reviewer),
  "comment": string (required for add_comment, request_changes, approve),
  "escalation_reason": string (optional)
}

Strategy:
1. Read the PR diff carefully
2. FLAG every bug you find with flag_bug (correct category + line + severity)
3. FLAG every security issue with flag_security
4. ADD_COMMENT for design/quality issues that aren't bugs
5. ASSIGN_REVIEWER to the appropriate role
6. Finally, REQUEST_CHANGES (if issues found) or APPROVE (if clean)

Respond ONLY with the JSON object. No explanation, no markdown.
"""


def build_user_message(obs_dict: dict) -> str:
    pr = obs_dict.get("current_pr")
    if not pr:
        return f"Status: {obs_dict.get('message', '')}\nNo PR available."

    files_text = ""
    for f in pr.get("files", []):
        files_text += (
            f"\n\n--- File: {f['filename']} ({f['language']}) ---\n{f['patch']}"
        )

    return f"""\
Task: {obs_dict['task']}
Step: {obs_dict['step_number']}
PRs remaining: {obs_dict['prs_remaining']}
Status: {obs_dict['message']}

Current PR: {pr['pr_id']} — {pr['title']}
Author: {pr['author']}
Description: {pr['description']}
+{pr['total_additions']} / -{pr['total_deletions']}

Flags raised so far in this PR:
{json.dumps(obs_dict.get('flags_raised', []), indent=2) or 'None yet'}

Diff:
{files_text}

Respond with your next action as a JSON object.
"""


def call_llm(client, model: str, history: list[dict]) -> str:
    max_retries = 5
    wait_seconds = 60  # Increased to 60s to handle the 51s penalty from Google

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=history,
                temperature=0.1,
                max_tokens=4096,  # Increased from 512 so the JSON doesn't get cut off!
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content.strip()

        except RateLimitError as e:
            if attempt == max_retries - 1:
                print("  [FATAL] Max retries reached. Crashing.")
                raise e
            print(
                f"  [Rate Limit Hit] Pausing for {wait_seconds}s to respect free tier... (Retry {attempt + 1}/{max_retries})"
            )
            time.sleep(wait_seconds)


def parse_action(raw: str) -> Action | None:
    # Strip markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
    if raw.endswith("```"):
        raw = "\n".join(raw.split("\n")[:-1])
    try:
        data = json.loads(raw.strip())
        return Action(**data)
    except Exception as e:
        print(f"  [parse error] {e} — raw: {raw[:120]}")
        return None


def run_task(task_name: str, model: str, client) -> float:
    env = CodeReviewEnv()
    task = TaskName(task_name)
    obs_dict = env.reset(task).model_dump()

    history = [{"role": "system", "content": SYSTEM_PROMPT}]
    task_def = TASKS[task]
    print(
        f"\n  Task: {task_def.name} ({task_def.difficulty}) — {task_def.max_steps} steps max"
    )

    for step_i in range(task_def.max_steps):
        user_msg = build_user_message(obs_dict)
        history.append({"role": "user", "content": user_msg})

        raw = call_llm(client, model, history)
        history.append({"role": "assistant", "content": raw})

        action = parse_action(raw)
        if action is None:
            # Fallback: skip
            action = Action(action_type="skip")

        result = env.step(action)
        obs_dict = result.observation.model_dump()

        print(
            f"  Step {step_i+1:02d}: {action.action_type.value:20s} reward={result.reward.value:+.3f}  cumulative={obs_dict['cumulative_reward']:+.3f}"
        )

        if result.done:
            break

    score, breakdown = env.grade()
    print(f"  ── Final score: {score:.4f} | breakdown: {json.dumps(breakdown)}")
    return score


def run_baseline() -> dict[str, float]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set.")

    model = os.environ.get("BASELINE_MODEL", "gemini-2.5-flash")

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    except ImportError:
        raise ImportError("openai package not installed. Run: pip install openai")

    print(f"\n{'='*60}")
    print(f"OpenEnv Code Review — Baseline Inference")
    print(f"Model: {model}")
    print(f"{'='*60}")

    scores: dict[str, float] = {}
    for task_name in ["bug_detection", "security_audit", "full_review"]:
        print(f"\n[Task: {task_name}]")
        try:
            scores[task_name] = run_task(task_name, model, client)
        except Exception as e:
            print(f"  ERROR: {e}")
            traceback.print_exc()
            scores[task_name] = 0.0

    print(f"\n{'='*60}")
    print("BASELINE SCORES:")
    for task, score in scores.items():
        print(f"  {task:<25} {score:.4f}")
    print(f"  {'AVERAGE':<25} {sum(scores.values()) / len(scores):.4f}")
    print(f"{'='*60}\n")

    return scores


if __name__ == "__main__":
    scores = run_baseline()
    sys.exit(0 if all(s > 0 for s in scores.values()) else 1)
