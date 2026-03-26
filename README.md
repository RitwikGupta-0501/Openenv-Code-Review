---
title: OpenEnv Code Review
emoji: 🔍
colorFrom: blue
colorTo: purple
sdk: docker
pinned: true
tags:
  - openenv
  - code-review
  - reinforcement-learning
  - security
  - software-engineering
short_description: OpenEnv environment for training AI agents on code review
---

# 🔍 OpenEnv: Code Review

> A real-world reinforcement learning environment where AI agents review pull requests, identify bugs, audit security vulnerabilities, and produce actionable code review output.

[![openenv](https://img.shields.io/badge/openenv-v1.0-blue)](https://huggingface.co)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-green)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)
[![Tests: 25 passing](https://img.shields.io/badge/tests-25%20passing-brightgreen)]()

---

## What Is This?

**OpenEnv: Code Review** simulates a real-world software engineering task: reviewing pull requests.

An AI agent is presented with realistic pull request diffs across Python, JavaScript, Go, and TypeScript. The agent must:

- **Identify bugs** — off-by-one errors, race conditions, memory leaks, logic errors
- **Audit security** — SQL injection, command injection, hardcoded secrets, broken auth, insecure deserialization
- **Route correctly** — assign the PR to the right reviewer role (backend, security, senior)
- **Summarise findings** — write actionable `REQUEST_CHANGES` or `APPROVE` decisions

This is a task that software engineers do every day. Training agents to do it well has immediate real-world value.

---

## Quick Start

### Option A: Docker (recommended)

```bash
git clone https://github.com/your-repo/openenv-code-review
cd openenv-code-review

docker build -t openenv-code-review .
docker run -p 7860:7860 openenv-code-review

# Server is live at http://localhost:7860
```

### Option B: Local Python

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 7860
```

### Option C: HuggingFace Space

Visit the live deployment at: `https://huggingface.co/spaces/YOUR_USERNAME/openenv-code-review`

---

## Running an Agent

```python
import requests

BASE = "http://localhost:7860"

# 1. Start a bug detection episode
obs = requests.post(f"{BASE}/reset?task=bug_detection").json()
print(obs["message"])
print(obs["current_pr"]["title"])

# 2. Flag a bug
result = requests.post(f"{BASE}/step", json={
    "action_type": "flag_bug",
    "bug_category": "off_by_one",
    "line_number": 22,
    "severity": "medium"
}).json()

print(f"Reward: {result['reward']['value']}")        # +0.28
print(f"Explanation: {result['reward']['explanation']}")

# 3. Flag a security issue
result = requests.post(f"{BASE}/step", json={
    "action_type": "flag_security",
    "security_category": "sql_injection",
    "line_number": 17,
    "severity": "high"
}).json()

# 4. Assign reviewer and close out the PR
requests.post(f"{BASE}/step", json={
    "action_type": "assign_reviewer",
    "reviewer_role": "backend"
})

requests.post(f"{BASE}/step", json={
    "action_type": "request_changes",
    "comment": "Found an off-by-one in retry logic and SQL injection in get_user. Both need fixing before merge."
})

# 5. Get your final score
score = requests.get(f"{BASE}/grader").json()
print(f"Score: {score['score']}")           # 0.0 – 1.0
print(f"Breakdown: {score['breakdown']}")
```

---

## API Reference

| Method | Endpoint                | Description                                        |
| ------ | ----------------------- | -------------------------------------------------- |
| `POST` | `/reset?task=<task_id>` | Start a new episode                                |
| `POST` | `/step`                 | Submit an action, receive observation + reward     |
| `GET`  | `/state`                | Current full environment state                     |
| `GET`  | `/tasks`                | List all tasks + full action JSON schema           |
| `GET`  | `/grader`               | Score the current episode (0.0–1.0)                |
| `GET`  | `/baseline`             | Run baseline inference (requires `OPENAI_API_KEY`) |
| `GET`  | `/docs`                 | Interactive Swagger UI                             |

---

## Observation Space

Every call to `/reset` and `/step` returns an **Observation**:

```json
{
  "task": "bug_detection",
  "step_number": 3,
  "current_pr": {
    "pr_id": "PR-101",
    "title": "Add user pagination to /api/users endpoint",
    "description": "...",
    "author": "junior_dev_1",
    "files": [
      {
        "filename": "api/users.py",
        "language": "python",
        "patch": "--- a/api/users.py\n+++ b/api/users.py\n..."
      }
    ],
    "total_additions": 45,
    "total_deletions": 4
  },
  "current_file_index": 0,
  "prs_remaining": 2,
  "flags_raised": [...],
  "cumulative_reward": 0.56,
  "elapsed_steps": 3,
  "message": "Bug flagged: off_by_one at line 22",
  "done": false
}
```

---

## Action Space

Every call to `/step` takes an **Action**:

```json
{
  "action_type": "flag_bug | flag_security | add_comment | assign_reviewer | request_changes | approve | skip",

  "bug_category": "logic_error | null_pointer | off_by_one | race_condition | memory_leak | infinite_loop | type_error | unhandled_exception",
  "security_category": "sql_injection | xss | hardcoded_secret | path_traversal | insecure_deserialization | broken_auth | sensitive_data_exposure | command_injection",
  "line_number": 22,
  "severity": "critical | high | medium | low | info",
  "reviewer_role": "backend | frontend | security | devops | senior",
  "comment": "Found SQL injection at line 17 — use parameterized queries.",
  "escalation_reason": "optional string"
}
```

**Required fields per action type:**

| action_type       | Required fields                                |
| ----------------- | ---------------------------------------------- |
| `flag_bug`        | `bug_category`, `line_number`, `severity`      |
| `flag_security`   | `security_category`, `line_number`, `severity` |
| `add_comment`     | `comment`                                      |
| `assign_reviewer` | `reviewer_role`                                |
| `request_changes` | `comment`                                      |
| `approve`         | _(none required, comment optional)_            |
| `skip`            | _(none required)_                              |

---

## Tasks

### Task 1 — Bug Detection `bug_detection` 🟢 Easy

**Objective:** Review 2 PRs (Python + JavaScript) and identify all bugs.

**PRs in this task:**

- `PR-101` — Python pagination endpoint with an off-by-one in retry logic and SQL injection in a route handler
- `PR-102` — JavaScript shopping cart with an off-by-one loop bug and raw payment card data exposure

**What a good agent does:** FLAG_BUG for the off-by-one errors, FLAG_SECURITY for the injection/data issues, ASSIGN_REVIEWER correctly, REQUEST_CHANGES with a clear summary.

**Max steps:** 30 | **Expected baseline score:** ~0.71

---

### Task 2 — Security Audit `security_audit` 🟡 Medium

**Objective:** Security-focused review of 2 PRs (Python + Go). Find all vulnerabilities.

**PRs in this task:**

- `PR-201` — Python file export feature with path traversal, SQL injection, command injection, SSTI, and **two separate sets of hardcoded credentials**
- `PR-202` — Go JWT authentication with MD5-signed tokens, unverified token signature, SQL injection in login, MD5 password hashing, and no token expiry check

**What a good agent does:** Must recognise multiple vulnerability classes in the same file, correctly classify each (not just "this looks bad"), and produce a security-focused REQUEST_CHANGES summary.

**Max steps:** 40 | **Expected baseline score:** ~0.58

---

### Task 3 — Full Review `full_review` 🔴 Hard

**Objective:** Comprehensive review of 2 complex PRs (Python + TypeScript). Bugs, security issues, race conditions, and design flaws are interleaved.

**PRs in this task:**

- `PR-301` — Python async job queue with insecure pickle deserialization (RCE risk), race conditions on the result cache, a thread leak in `schedule_recurring`, worker list never cleared on `stop()`, and a cache stampede vulnerability
- `PR-302` — TypeScript multi-tenant SaaS middleware where a module-level mutable variable causes cross-tenant data leakage in async Node.js, missing tenant filter on UPDATE/DELETE queries, SQL injection via filter key interpolation, and secrets returned in full config responses

**What a good agent does:** Distinguish between bug and security categories for subtle issues (e.g. the race condition is a bug AND a security issue), flag all 9+ issues, assign SENIOR reviewer, write a structured multi-section summary.

**Max steps:** 60 | **Expected baseline score:** ~0.39

---

## Reward Function

Reward is shaped across the **full trajectory** — agents get signal on every step, not just at the end.

| Event                                       | Reward                        |
| ------------------------------------------- | ----------------------------- |
| Correctly flag a `critical` issue           | +0.50                         |
| Correctly flag a `high` severity issue      | +0.40                         |
| Correctly flag a `medium` severity issue    | +0.30                         |
| Correctly flag a `low` severity issue       | +0.15                         |
| Correct category label (vs just right line) | Full credit                   |
| Wrong category but right line               | 50% credit                    |
| False positive (flagging clean code)        | −0.20                         |
| Correct reviewer assigned                   | +0.10                         |
| Wrong reviewer assigned                     | −0.05                         |
| REQUEST_CHANGES when PR has issues          | +0.15                         |
| APPROVE when PR has issues                  | −0.15                         |
| Meaningful ADD_COMMENT (>30 chars)          | +0.05                         |
| SKIP action                                 | −0.05                         |
| Each step taken                             | −0.02 _(efficiency pressure)_ |

### Line Number Tolerance

Agents are given **±3 line tolerance** when matching flags to ground truth. A bug at line 22 is credited if the agent flags lines 19–25. This accounts for agents reasoning about a code block rather than the exact line.

---

## Grader

The grader runs deterministically at episode end and returns a score in `[0.0, 1.0]` with a full breakdown:

```json
{
  "score": 0.74,
  "breakdown": {
    "bug_recall": 0.875,
    "vuln_recall": 0.72,
    "precision": 0.9,
    "reviewer_correct": 1.0,
    "final_action": 1.0,
    "comment_quality": 0.6,
    "efficiency_bonus": 0.047,
    "weighted_total": 0.7401
  },
  "task": "bug_detection"
}
```

**Score interpretation:**

| Range     | Meaning                                              |
| --------- | ---------------------------------------------------- |
| 0.0 – 0.3 | Poor — missed most issues                            |
| 0.3 – 0.6 | Partial — found some, missed key ones                |
| 0.6 – 0.8 | Good — found most issues with reasonable precision   |
| 0.8 – 1.0 | Excellent — comprehensive review with correct labels |

---

## Baseline Scores

Run against `gpt-4o-mini` with the included `baseline.py`:

| Task             | Score    | Difficulty |
| ---------------- | -------- | ---------- |
| `bug_detection`  | 0.71     | Easy       |
| `security_audit` | 0.58     | Medium     |
| `full_review`    | 0.39     | Hard       |
| **Average**      | **0.56** | —          |

### Running the Baseline Yourself

```bash
export OPENAI_API_KEY=sk-...
python -m app.baseline

# Or via the API:
curl http://localhost:7860/baseline
```

---

## Project Structure

```
openenv-code-review/
│
├── app/
│   ├── __init__.py     — package marker
│   ├── main.py         — FastAPI app, all HTTP endpoints
│   ├── env.py          — Core env: reset() / step() / state() / grade()
│   ├── models.py       — Pydantic v2 typed models (Observation, Action, Reward)
│   ├── corpus.py       — 6 annotated PRs with hidden ground truth
│   ├── tasks.py        — Task definitions + deterministic grader
│   └── baseline.py     — GPT-4o-mini baseline inference script
│
├── tests/
│   ├── conftest.py     — pytest configuration
│   └── test_env.py     — 25 unit tests (reset, step, state, grader, rewards)
│
├── openenv.yaml        — OpenEnv spec metadata
├── Dockerfile          — Container for HuggingFace Spaces
├── requirements.txt    — Python dependencies
└── README.md           — This file
```

---

## Deploying to HuggingFace Spaces

1. Create a new Space at [huggingface.co/new-space](https://huggingface.co/new-space)
   - SDK: **Docker**
   - Visibility: Public

2. Push this repo to the Space:

```bash
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/openenv-code-review
git push hf main
```

3. (Optional) Add your `OPENAI_API_KEY` as a Space secret for live baseline:
   - Space Settings → Variables and Secrets → New Secret

4. Verify deployment:

```bash
curl https://YOUR_USERNAME-openenv-code-review.hf.space/tasks
```

---

## Running Tests

```bash
pip install -r requirements.txt pytest
python -m pytest tests/ -v
```

Expected output: **25 passed**

---

## OpenEnv Spec Compliance

| Requirement                    | Status                                     |
| ------------------------------ | ------------------------------------------ |
| Typed `Observation` model      | ✅ Pydantic v2                             |
| Typed `Action` model           | ✅ Pydantic v2                             |
| Typed `Reward` model           | ✅ with component breakdown                |
| `POST /reset`                  | ✅                                         |
| `POST /step`                   | ✅ returns observation, reward, done, info |
| `GET /state`                   | ✅                                         |
| `GET /tasks`                   | ✅ with action schema                      |
| `GET /grader`                  | ✅ deterministic 0.0–1.0                   |
| `GET /baseline`                | ✅                                         |
| `openenv.yaml`                 | ✅                                         |
| 3+ tasks with difficulty range | ✅ easy → medium → hard                    |
| Shaped reward function         | ✅ per-step signal                         |
| Dockerfile                     | ✅ builds and runs                         |
| HuggingFace Space              | ✅ Docker SDK                              |

---

## License

MIT — see [LICENSE](LICENSE)
