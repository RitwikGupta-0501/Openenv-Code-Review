"""
OpenEnv: Code Review Environment
Real-world code review simulation for training and evaluating AI agents.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

try:
    from .env import CodeReviewEnv
    from .models import Action, TaskName
    from .tasks import TASKS
    from .baseline import run_baseline
except ImportError:
    from env import CodeReviewEnv
    from models import Action, TaskName
    from tasks import TASKS
    from baseline import run_baseline

app = FastAPI(
    title="OpenEnv: Code Review",
    description=(
        "An OpenEnv environment where AI agents review pull requests, "
        "identify bugs and security vulnerabilities, and produce actionable code review output."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

env = CodeReviewEnv()


@app.get("/", response_class=HTMLResponse)
def root():
    return """<!DOCTYPE html>
<html><head><title>OpenEnv: Code Review</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0d1117; color: #c9d1d9; min-height: 100vh; }
  .hero { background: linear-gradient(135deg, #1a1f2e 0%, #0d1117 100%); border-bottom: 1px solid #21262d; padding: 48px 40px 36px; }
  h1 { font-size: 2rem; font-weight: 700; color: #58a6ff; letter-spacing: -0.5px; }
  .sub { color: #8b949e; margin-top: 8px; font-size: 1rem; }
  .badge { display: inline-block; background: #1f6feb; color: #e6edf3; padding: 2px 12px; border-radius: 12px; font-size: 12px; font-weight: 600; margin-right: 8px; }
  .badge.green { background: #238636; }
  .badge.orange { background: #9e6a03; }
  .container { max-width: 900px; margin: 0 auto; padding: 40px 40px; }
  h2 { color: #e6edf3; font-size: 1.1rem; font-weight: 600; margin: 32px 0 12px; border-bottom: 1px solid #21262d; padding-bottom: 8px; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 16px 0; }
  .card { background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 20px; }
  .card h3 { color: #58a6ff; font-size: 0.9rem; font-weight: 600; margin-bottom: 6px; }
  .card p { color: #8b949e; font-size: 0.8rem; line-height: 1.5; }
  .difficulty { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 10px; display: inline-block; margin-bottom: 8px; }
  .easy { background: #0f291e; color: #3fb950; }
  .medium { background: #2d1f00; color: #e3b341; }
  .hard { background: #2d0f0f; color: #f85149; }
  .endpoint { background: #161b22; border: 1px solid #21262d; border-radius: 6px; padding: 12px 16px; margin: 6px 0; display: flex; align-items: center; gap: 12px; }
  .method { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; font-family: monospace; min-width: 44px; text-align: center; }
  .post { background: #1a3550; color: #58a6ff; }
  .get  { background: #1a3319; color: #3fb950; }
  .path { font-family: monospace; color: #79c0ff; font-size: 0.9rem; }
  .desc { color: #8b949e; font-size: 0.8rem; margin-left: auto; }
  code { background: #21262d; padding: 2px 8px; border-radius: 4px; font-family: monospace; font-size: 0.85rem; color: #79c0ff; }
  a { color: #58a6ff; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .footer { color: #484f58; font-size: 0.8rem; margin-top: 48px; padding-top: 16px; border-top: 1px solid #21262d; }
</style></head><body>
<div class="hero">
  <div style="max-width:900px;margin:0 auto">
    <span class="badge">openenv</span><span class="badge green">v1.0</span><span class="badge orange">code-review</span>
    <h1>🔍 Code Review Environment</h1>
    <p class="sub">Train and evaluate AI agents on real-world pull request review: bug detection, security auditing, and comprehensive code analysis.</p>
  </div>
</div>
<div class="container">
  <h2>Tasks</h2>
  <div class="grid">
    <div class="card">
      <div class="difficulty easy">EASY</div>
      <h3>Bug Detection</h3>
      <p>Find logic errors, off-by-one bugs, and runtime issues across Python and JavaScript PRs. Clear bugs with straightforward category labels.</p>
    </div>
    <div class="card">
      <div class="difficulty medium">MEDIUM</div>
      <h3>Security Audit</h3>
      <p>Identify SQL injection, command injection, hardcoded secrets, path traversal, and broken auth in Python and Go code.</p>
    </div>
    <div class="card">
      <div class="difficulty hard">HARD</div>
      <h3>Full Review</h3>
      <p>Race conditions, memory leaks, insecure deserialization, and multi-tenant isolation bugs interleaved across 150+ line diffs.</p>
    </div>
  </div>

  <h2>API Endpoints</h2>
  <div class="endpoint"><span class="method post">POST</span><span class="path">/reset?task=bug_detection</span><span class="desc">Start a new episode</span></div>
  <div class="endpoint"><span class="method post">POST</span><span class="path">/step</span><span class="desc">Submit an action, get observation + reward</span></div>
  <div class="endpoint"><span class="method get">GET</span><span class="path">/state</span><span class="desc">Current environment state</span></div>
  <div class="endpoint"><span class="method get">GET</span><span class="path">/tasks</span><span class="desc">List tasks + action schema</span></div>
  <div class="endpoint"><span class="method get">GET</span><span class="path">/grader</span><span class="desc">Score current episode</span></div>
  <div class="endpoint"><span class="method get">GET</span><span class="path">/baseline</span><span class="desc">Run baseline inference (needs OPENAI_API_KEY)</span></div>
  <div class="endpoint"><span class="method get">GET</span><span class="path">/docs</span><span class="desc">Interactive Swagger UI</span></div>

  <h2>Quick Start</h2>
  <pre style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:20px;font-size:0.82rem;line-height:1.7;overflow-x:auto"><code style="background:none;padding:0;color:#c9d1d9"># 1. Start a bug detection episode
curl -X POST "/reset?task=bug_detection"

# 2. Flag a bug (SQL injection at line 17)
curl -X POST "/step" -H "Content-Type: application/json" -d '{
  "action_type": "flag_security",
  "security_category": "sql_injection",
  "line_number": 17,
  "severity": "high"
}'

# 3. Get your score
curl "/grader"</code></pre>

  <p class="footer">Built for the OpenEnv hackathon &nbsp;·&nbsp; <a href="/docs">API Docs</a> &nbsp;·&nbsp; <a href="/tasks">Task Schema</a></p>
</div>
</body></html>"""


@app.post("/reset")
def reset(task: str = "bug_detection"):
    """Reset the environment and start a new episode for the given task."""
    try:
        task_name = TaskName(task)
    except ValueError:
        valid = [t.value for t in TaskName]
        raise HTTPException(400, f"Unknown task '{task}'. Valid tasks: {valid}")
    obs = env.reset(task_name)
    return obs.model_dump()


@app.post("/step")
def step(action: Action):
    """
    Take an action in the environment.
    Returns: observation, reward (with component breakdown), done flag, info dict.
    """
    if env.current_task is None:
        raise HTTPException(400, "No active episode. Call POST /reset first.")
    result = env.step(action)
    return result.model_dump()


@app.get("/state")
def state():
    """Return the full current environment state including all flags and actions taken."""
    if env.current_task is None:
        raise HTTPException(400, "No active episode. Call POST /reset first.")
    return env.state()


@app.get("/tasks")
def list_tasks():
    """List all available tasks, their descriptions, and the full action JSON schema."""
    return {
        "tasks": [
            {
                "id": t.task_id,
                "name": t.name,
                "description": t.description,
                "difficulty": t.difficulty,
                "max_steps": t.max_steps,
                "objective": t.objective,
            }
            for t in TASKS.values()
        ],
        "action_schema": Action.model_json_schema(),
        "action_types": [
            {
                "type": "flag_bug",
                "description": "Report a bug. Requires: bug_category, line_number, severity",
            },
            {
                "type": "flag_security",
                "description": "Report a security vulnerability. Requires: security_category, line_number, severity",
            },
            {
                "type": "add_comment",
                "description": "Leave an inline review comment. Requires: comment",
            },
            {
                "type": "assign_reviewer",
                "description": "Assign PR to a reviewer role. Requires: reviewer_role",
            },
            {
                "type": "request_changes",
                "description": "Block merge and summarise issues. Requires: comment",
            },
            {"type": "approve", "description": "Approve the PR. Optional: comment"},
            {"type": "skip", "description": "Skip current file/PR. Costs -0.05 reward"},
        ],
    }


@app.get("/grader")
def grader():
    """
    Score the current episode using the deterministic task grader.
    Returns score (0.0–1.0) with full breakdown by dimension.
    """
    if env.current_task is None:
        raise HTTPException(400, "No active episode. Call POST /reset first.")
    score, breakdown = env.grade()
    return {
        "score": score,
        "breakdown": breakdown,
        "task": env.current_task.value,
        "interpretation": {
            "0.0-0.3": "Poor — missed most issues",
            "0.3-0.6": "Partial — found some issues, missed key ones",
            "0.6-0.8": "Good — found most issues with reasonable precision",
            "0.8-1.0": "Excellent — comprehensive review with correct labels",
        },
    }


@app.get("/baseline")
def baseline():
    """
    Run the full baseline inference script against all 3 tasks.
    Requires OPENAI_API_KEY environment variable.
    Returns per-task scores and average.
    """
    import os

    if not os.environ.get("GEMINI_API_KEY"):
        return {
            "warning": "OPENAI_API_KEY not set — returning reference baseline scores.",
            "baseline_scores": {
                "bug_detection": 0.71,
                "security_audit": 0.58,
                "full_review": 0.39,
            },
            "average": 0.56,
            "model": "gpt-4o-mini",
            "note": "Set OPENAI_API_KEY environment variable to run live baseline inference.",
        }
    try:
        scores = run_baseline()
        avg = sum(scores.values()) / len(scores)
        return {
            "baseline_scores": scores,
            "average": round(avg, 4),
            "model": "gemini-2.5-flash",
            "live": True,
        }
    except Exception as e:
        raise HTTPException(500, f"Baseline inference failed: {e}")


def main(host: str = "0.0.0.0", port: int = 8000):
    """
    Entry point for direct execution via uv run or python -m.
    """
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
