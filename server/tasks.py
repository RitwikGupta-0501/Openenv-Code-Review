"""
Task definitions and deterministic graders for all 3 tasks.
Each grader returns (score: float, breakdown: dict) where score ∈ [0.0, 1.0].
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from .models import TaskName, ActionType, BugCategory, SecurityCategory, Severity


@dataclass
class TaskDefinition:
    task_id: str
    name: str
    description: str
    difficulty: str
    max_steps: int
    objective: str


TASKS: dict[str, TaskDefinition] = {
    TaskName.BUG_DETECTION: TaskDefinition(
        task_id="bug_detection",
        name="Bug Detection",
        description=(
            "Review 2 pull requests and identify all bugs. "
            "For each bug found, FLAG_BUG with the correct category, line number, and severity. "
            "When done with each PR, either APPROVE (if clean) or REQUEST_CHANGES (if issues found). "
            "Assign the PR to the appropriate reviewer role."
        ),
        difficulty="easy",
        max_steps=30,
        objective="Find all seeded bugs; minimize false positives; assign correct reviewer.",
    ),
    TaskName.SECURITY_AUDIT: TaskDefinition(
        task_id="security_audit",
        name="Security Audit",
        description=(
            "Perform a security-focused review of 2 pull requests. "
            "Identify all security vulnerabilities using FLAG_SECURITY with correct category and severity. "
            "Escalate critical findings with detailed explanations. "
            "Draft a REQUEST_CHANGES with a clear, actionable security summary."
        ),
        difficulty="medium",
        max_steps=40,
        objective="Find all security vulnerabilities; correct categories; actionable summaries.",
    ),
    TaskName.FULL_REVIEW: TaskDefinition(
        task_id="full_review",
        name="Full Code Review",
        description=(
            "Conduct a thorough code review of 2 complex pull requests covering bugs, security, "
            "race conditions, design issues, and correctness. Use FLAG_BUG, FLAG_SECURITY, and "
            "ADD_COMMENT for inline notes. Provide a final REQUEST_CHANGES with a comprehensive "
            "structured summary. Assign the correct senior reviewer."
        ),
        difficulty="hard",
        max_steps=60,
        objective="Find all bugs + security issues; meaningful inline comments; comprehensive summary.",
    ),
}


# ─── Grader ──────────────────────────────────────────────────────────────────

def _severity_weight(sev: str) -> float:
    return {"critical": 1.0, "high": 0.75, "medium": 0.5, "low": 0.25, "info": 0.1}.get(sev, 0.5)


def grade_episode(
    task_name: str,
    annotated_prs: list,          # list[AnnotatedPR] from corpus
    agent_flags: list[dict],      # accumulated flags from the episode
    agent_actions: list[dict],    # all actions taken
    steps_used: int,
    max_steps: int,
) -> tuple[float, dict[str, Any]]:
    """
    Deterministic grader. Returns (score ∈ [0.0, 1.0], breakdown dict).

    Scoring dimensions:
      1. Bug recall        — what fraction of seeded bugs were found (weighted by severity)
      2. Vuln recall       — what fraction of security issues were found (weighted by severity)
      3. Precision         — penalty for false positives
      4. Category accuracy — correct category labels (partial credit)
      5. Reviewer correct  — assigned the right reviewer role
      6. Final action      — issued REQUEST_CHANGES (not APPROVE) when issues exist
      7. Comment quality   — touched key topics in comments/summaries
      8. Efficiency        — mild bonus for not burning all steps
    """

    breakdown: dict[str, float] = {}

    all_gt_bugs  = []
    all_gt_vulns = []
    expected_reviewer_set = set()
    should_approve = all(apr.ground_truth.should_approve for apr in annotated_prs)
    all_quality_topics: list[str] = []

    for apr in annotated_prs:
        all_gt_bugs.extend(apr.ground_truth.bugs)
        all_gt_vulns.extend(apr.ground_truth.security_issues)
        expected_reviewer_set.add(apr.ground_truth.correct_reviewer.value)
        all_quality_topics.extend(apr.ground_truth.quality_comments)

    # Separate agent flags
    agent_bug_flags  = [f for f in agent_flags if f.get("flag_type") == "bug"]
    agent_vuln_flags = [f for f in agent_flags if f.get("flag_type") == "security"]

    # ── 1. Bug recall ──────────────────────────────────────────────────
    total_bug_weight = sum(_severity_weight(b["severity"].value if hasattr(b["severity"], "value") else b["severity"]) for b in all_gt_bugs) or 1.0
    matched_bug_weight = 0.0
    for gt_bug in all_gt_bugs:
        gt_line = gt_bug["line"]
        gt_cat  = gt_bug["category"].value if hasattr(gt_bug["category"], "value") else gt_bug["category"]
        gt_sev  = gt_bug["severity"].value if hasattr(gt_bug["severity"], "value") else gt_bug["severity"]
        for af in agent_bug_flags:
            line_match = abs(af.get("line_number", -999) - gt_line) <= 3   # ±3 line tolerance
            cat_match  = af.get("bug_category") == gt_cat
            if line_match:
                credit = _severity_weight(gt_sev)
                if cat_match:
                    credit *= 1.0    # full credit
                else:
                    credit *= 0.5    # half credit for wrong category
                matched_bug_weight += credit
                break
    bug_recall = min(matched_bug_weight / total_bug_weight, 1.0) if all_gt_bugs else 1.0
    breakdown["bug_recall"] = round(bug_recall, 3)

    # ── 2. Vuln recall ─────────────────────────────────────────────────
    total_vuln_weight = sum(_severity_weight(v["severity"].value if hasattr(v["severity"], "value") else v["severity"]) for v in all_gt_vulns) or 1.0
    matched_vuln_weight = 0.0
    for gt_vuln in all_gt_vulns:
        gt_line = gt_vuln["line"]
        gt_cat  = gt_vuln["category"].value if hasattr(gt_vuln["category"], "value") else gt_vuln["category"]
        gt_sev  = gt_vuln["severity"].value if hasattr(gt_vuln["severity"], "value") else gt_vuln["severity"]
        for af in agent_vuln_flags:
            line_match = abs(af.get("line_number", -999) - gt_line) <= 3
            cat_match  = af.get("security_category") == gt_cat
            if line_match:
                credit = _severity_weight(gt_sev)
                if cat_match:
                    credit *= 1.0
                else:
                    credit *= 0.5
                matched_vuln_weight += credit
                break
    vuln_recall = min(matched_vuln_weight / total_vuln_weight, 1.0) if all_gt_vulns else 1.0
    breakdown["vuln_recall"] = round(vuln_recall, 3)

    # ── 3. Precision (false positive penalty) ──────────────────────────
    total_flags  = len(agent_bug_flags) + len(agent_vuln_flags)
    total_gt     = len(all_gt_bugs) + len(all_gt_vulns)
    false_pos    = max(0, total_flags - total_gt)
    precision    = max(0.0, 1.0 - (false_pos * 0.1))   # -10% per false positive, capped at 0
    breakdown["precision"] = round(precision, 3)

    # ── 4. Reviewer correctness ────────────────────────────────────────
    assigned_reviewers = set(
        a.get("reviewer_role") for a in agent_actions
        if a.get("action_type") == ActionType.ASSIGN_REVIEWER.value
    )
    reviewer_score = 1.0 if expected_reviewer_set & assigned_reviewers else 0.0
    breakdown["reviewer_correct"] = reviewer_score

    # ── 5. Final action correctness ────────────────────────────────────
    final_actions = [a for a in agent_actions if a.get("action_type") in
                     (ActionType.REQUEST_CHANGES.value, ActionType.APPROVE.value)]
    if not final_actions:
        final_action_score = 0.0
    else:
        last = final_actions[-1]["action_type"]
        if should_approve:
            final_action_score = 1.0 if last == ActionType.APPROVE.value else 0.0
        else:
            final_action_score = 1.0 if last == ActionType.REQUEST_CHANGES.value else 0.0
    breakdown["final_action"] = final_action_score

    # ── 6. Comment quality ─────────────────────────────────────────────
    all_text = " ".join(
        (a.get("comment") or "") + " " + (a.get("escalation_reason") or "")
        for a in agent_actions
    ).lower()
    if all_quality_topics:
        hits = sum(1 for topic in all_quality_topics if topic.lower() in all_text)
        comment_quality = hits / len(all_quality_topics)
    else:
        comment_quality = 1.0
    breakdown["comment_quality"] = round(comment_quality, 3)

    # ── 7. Efficiency bonus ────────────────────────────────────────────
    efficiency = max(0.0, 1.0 - (steps_used / max_steps))
    breakdown["efficiency_bonus"] = round(efficiency * 0.1, 3)  # max 0.1 bonus

    # ── Weighted final score ───────────────────────────────────────────
    # Weights tuned per task difficulty
    if task_name == TaskName.BUG_DETECTION:
        weights = dict(bug_recall=0.40, vuln_recall=0.15, precision=0.15,
                       reviewer_correct=0.10, final_action=0.10, comment_quality=0.10)
    elif task_name == TaskName.SECURITY_AUDIT:
        weights = dict(bug_recall=0.10, vuln_recall=0.45, precision=0.15,
                       reviewer_correct=0.10, final_action=0.10, comment_quality=0.10)
    else:  # full_review
        weights = dict(bug_recall=0.25, vuln_recall=0.25, precision=0.10,
                       reviewer_correct=0.10, final_action=0.10, comment_quality=0.20)

    base_score = sum(breakdown[k] * w for k, w in weights.items())
    final_score = min(1.0, base_score + breakdown["efficiency_bonus"])
    breakdown["weighted_total"] = round(final_score, 4)

    return round(final_score, 4), breakdown
