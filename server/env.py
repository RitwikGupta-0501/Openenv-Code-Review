"""
SupportTriageEnv — core environment implementing step() / reset() / state().
"""

from __future__ import annotations
import copy
from typing import Any, Optional

from .models import (
    TaskName, Action, ActionType, Observation, Reward, StepResult,
    PullRequest,
)
from .corpus import TASK_PR_MAP, AnnotatedPR
from .tasks import TASKS, grade_episode


class CodeReviewEnv:
    """
    OpenEnv-compliant code review environment.

    Episode flow:
      1. reset(task)     → returns initial Observation with first PR/file
      2. step(action)*   → agent flags bugs/vulns, adds comments, assigns reviewer
      3. When agent issues REQUEST_CHANGES or APPROVE, moves to next PR
      4. Episode ends when all PRs are reviewed or max_steps reached
    """

    def __init__(self) -> None:
        self.current_task:       Optional[TaskName]         = None
        self._prs:               list[AnnotatedPR]          = []
        self._pr_index:          int                        = 0
        self._file_index:        int                        = 0
        self._step:              int                        = 0
        self._cumulative_reward: float                      = 0.0
        self._flags:             list[dict[str, Any]]       = []   # all flags this episode
        self._actions:           list[dict[str, Any]]       = []   # all actions this episode
        self._pr_flags:          list[dict[str, Any]]       = []   # flags for current PR
        self._done:              bool                       = False

    # ─── reset ───────────────────────────────────────────────────────────────

    def reset(self, task: TaskName) -> Observation:
        self.current_task       = task
        self._prs               = copy.deepcopy(TASK_PR_MAP[task.value])
        self._pr_index          = 0
        self._file_index        = 0
        self._step              = 0
        self._cumulative_reward = 0.0
        self._flags             = []
        self._actions           = []
        self._pr_flags          = []
        self._done              = False

        task_def = TASKS[task]
        return Observation(
            task=task.value,
            step_number=0,
            current_pr=self._current_pr().pr if self._prs else None,
            current_file_index=0,
            prs_remaining=len(self._prs),
            flags_raised=[],
            cumulative_reward=0.0,
            elapsed_steps=0,
            message=(
                f"Episode started. Task: {task_def.name} ({task_def.difficulty}). "
                f"Objective: {task_def.objective} "
                f"You have {len(self._prs)} PR(s) to review and {task_def.max_steps} steps."
            ),
            done=False,
        )

    # ─── step ────────────────────────────────────────────────────────────────

    def step(self, action: Action) -> StepResult:
        if self._done:
            return self._terminal_result("Episode already done. Call /reset to start a new episode.")

        task_def = TASKS[self.current_task]
        self._step += 1

        action_dict = action.model_dump()
        self._actions.append(action_dict)

        reward_value, reward_components, reward_explanation = self._compute_reward(action)
        self._cumulative_reward += reward_value

        # Check max steps
        if self._step >= task_def.max_steps:
            self._done = True
            obs = self._make_obs("Max steps reached. Episode ending.", done=True)
            return StepResult(
                observation=obs,
                reward=Reward(value=reward_value, components=reward_components, explanation=reward_explanation),
                done=True,
                info={"reason": "max_steps"},
            )

        # Process the action
        message = self._process_action(action, action_dict)

        done = self._done
        obs = self._make_obs(message, done=done)

        return StepResult(
            observation=obs,
            reward=Reward(value=reward_value, components=reward_components, explanation=reward_explanation),
            done=done,
            info={"step": self._step, "pr_index": self._pr_index},
        )

    # ─── state ───────────────────────────────────────────────────────────────

    def state(self) -> dict[str, Any]:
        return {
            "task": self.current_task.value if self.current_task else None,
            "step": self._step,
            "pr_index": self._pr_index,
            "file_index": self._file_index,
            "prs_total": len(self._prs),
            "prs_remaining": max(0, len(self._prs) - self._pr_index),
            "flags_raised": self._flags,
            "actions_taken": self._actions,
            "cumulative_reward": round(self._cumulative_reward, 4),
            "done": self._done,
        }

    # ─── grade ───────────────────────────────────────────────────────────────

    def grade(self) -> tuple[float, dict[str, Any]]:
        task_def = TASKS[self.current_task]
        return grade_episode(
            task_name=self.current_task,
            annotated_prs=self._prs,
            agent_flags=self._flags,
            agent_actions=self._actions,
            steps_used=self._step,
            max_steps=task_def.max_steps,
        )

    # ─── internal helpers ────────────────────────────────────────────────────

    def _current_pr(self) -> Optional[AnnotatedPR]:
        if self._pr_index < len(self._prs):
            return self._prs[self._pr_index]
        return None

    def _make_obs(self, message: str, done: bool = False) -> Observation:
        apr = self._current_pr()
        return Observation(
            task=self.current_task.value,
            step_number=self._step,
            current_pr=apr.pr if apr else None,
            current_file_index=self._file_index,
            prs_remaining=max(0, len(self._prs) - self._pr_index),
            flags_raised=self._pr_flags,
            cumulative_reward=round(self._cumulative_reward, 4),
            elapsed_steps=self._step,
            message=message,
            done=done,
        )

    def _process_action(self, action: Action, action_dict: dict) -> str:
        atype = action.action_type
        apr = self._current_pr()

        if atype == ActionType.FLAG_BUG:
            if action.bug_category and action.line_number and action.severity:
                flag = {
                    "flag_type": "bug",
                    "bug_category": action.bug_category.value,
                    "line_number": action.line_number,
                    "severity": action.severity.value,
                    "pr_id": apr.pr.pr_id if apr else "?",
                }
                self._flags.append(flag)
                self._pr_flags.append(flag)
                return f"Bug flagged: {action.bug_category.value} at line {action.line_number} (severity: {action.severity.value})."
            return "FLAG_BUG requires bug_category, line_number, and severity."

        elif atype == ActionType.FLAG_SECURITY:
            if action.security_category and action.line_number and action.severity:
                flag = {
                    "flag_type": "security",
                    "security_category": action.security_category.value,
                    "line_number": action.line_number,
                    "severity": action.severity.value,
                    "pr_id": apr.pr.pr_id if apr else "?",
                }
                self._flags.append(flag)
                self._pr_flags.append(flag)
                return f"Security issue flagged: {action.security_category.value} at line {action.line_number} (severity: {action.severity.value})."
            return "FLAG_SECURITY requires security_category, line_number, and severity."

        elif atype == ActionType.ADD_COMMENT:
            if action.comment:
                return f"Comment added: {action.comment[:80]}..."
            return "ADD_COMMENT requires comment text."

        elif atype == ActionType.ASSIGN_REVIEWER:
            if action.reviewer_role:
                return f"PR assigned to reviewer: {action.reviewer_role.value}."
            return "ASSIGN_REVIEWER requires reviewer_role."

        elif atype in (ActionType.REQUEST_CHANGES, ActionType.APPROVE):
            # Advance to next PR
            self._pr_index += 1
            self._pr_flags = []
            if self._pr_index >= len(self._prs):
                self._done = True
                verb = "approved" if atype == ActionType.APPROVE else "review requested"
                return f"PR {verb}. All PRs reviewed — episode complete."
            self._file_index = 0
            verb = "Approved" if atype == ActionType.APPROVE else "Changes requested on"
            return f"{verb} PR. Moving to next PR ({self._pr_index + 1}/{len(self._prs)})."

        elif atype == ActionType.SKIP:
            # Move to next file within PR, or next PR if last file
            if apr and self._file_index < len(apr.pr.files) - 1:
                self._file_index += 1
                return f"Skipped to file {self._file_index + 1}/{len(apr.pr.files)}."
            else:
                self._pr_index += 1
                self._pr_flags = []
                self._file_index = 0
                if self._pr_index >= len(self._prs):
                    self._done = True
                    return "Skipped last PR. Episode complete."
                return f"Skipped PR. Moving to next PR ({self._pr_index + 1}/{len(self._prs)})."

        return f"Action {atype.value} processed."

    def _compute_reward(self, action: Action) -> tuple[float, dict[str, float], str]:
        """
        Shaped reward function providing signal throughout the trajectory.

        Components:
          +0.3 to +0.5  correct bug/vuln flagged (severity-weighted)
          -0.2          false positive (flag on clean line)
          +0.1          correct reviewer assigned
          -0.1          wrong final action (approve vs request_changes)
          +0.05         meaningful comment (length > 30 chars)
          -0.05         skip penalty
          -0.02/step    step cost to discourage padding
        """
        components: dict[str, float] = {}
        apr = self._current_pr()

        # Step cost
        components["step_cost"] = -0.02

        if action.action_type == ActionType.FLAG_BUG and apr:
            gt_bugs = apr.ground_truth.bugs
            hit = any(
                abs(b["line"] - (action.line_number or -999)) <= 3
                for b in gt_bugs
            )
            if hit:
                sev = action.severity.value if action.severity else "medium"
                bonus = {"critical": 0.5, "high": 0.4, "medium": 0.3, "low": 0.15, "info": 0.05}.get(sev, 0.2)
                components["correct_bug_flag"] = bonus
            else:
                components["false_positive"] = -0.2

        elif action.action_type == ActionType.FLAG_SECURITY and apr:
            gt_vulns = apr.ground_truth.security_issues
            hit = any(
                abs(v["line"] - (action.line_number or -999)) <= 3
                for v in gt_vulns
            )
            if hit:
                sev = action.severity.value if action.severity else "medium"
                bonus = {"critical": 0.5, "high": 0.4, "medium": 0.3, "low": 0.15, "info": 0.05}.get(sev, 0.2)
                components["correct_vuln_flag"] = bonus
            else:
                components["false_positive"] = -0.2

        elif action.action_type == ActionType.ASSIGN_REVIEWER and apr:
            if action.reviewer_role and action.reviewer_role.value in {apr.ground_truth.correct_reviewer.value}:
                components["correct_reviewer"] = 0.1
            else:
                components["wrong_reviewer"] = -0.05

        elif action.action_type == ActionType.REQUEST_CHANGES and apr:
            if not apr.ground_truth.should_approve:
                components["correct_final_action"] = 0.15
            else:
                components["wrong_final_action"] = -0.1

        elif action.action_type == ActionType.APPROVE and apr:
            if apr.ground_truth.should_approve:
                components["correct_final_action"] = 0.15
            else:
                components["wrong_final_action"] = -0.15   # worse — approved a bad PR

        elif action.action_type == ActionType.ADD_COMMENT:
            if action.comment and len(action.comment) > 30:
                components["quality_comment"] = 0.05
            else:
                components["empty_comment"] = -0.01

        elif action.action_type == ActionType.SKIP:
            components["skip_penalty"] = -0.05

        total = sum(components.values())
        explanation = "; ".join(f"{k}={v:+.2f}" for k, v in components.items())
        return round(total, 4), components, explanation

    def _terminal_result(self, message: str) -> StepResult:
        obs = Observation(
            task=self.current_task.value if self.current_task else "none",
            step_number=self._step,
            current_pr=None,
            current_file_index=0,
            prs_remaining=0,
            flags_raised=[],
            cumulative_reward=self._cumulative_reward,
            elapsed_steps=self._step,
            message=message,
            done=True,
        )
        return StepResult(
            observation=obs,
            reward=Reward(value=0.0, components={}, explanation="Episode already done."),
            done=True,
            info={},
        )
