"""
Test suite for the OpenEnv Code Review environment.
Tests: reset, step, state, grader, all action types, reward shaping, episode termination.
"""

import pytest
from server.models import Action, ActionType, TaskName, BugCategory, SecurityCategory, Severity, ReviewerRole
from server.env import CodeReviewEnv
from server.tasks import grade_episode, TASKS
from server.corpus import TASK_PR_MAP


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def env():
    return CodeReviewEnv()


# ─── reset() ─────────────────────────────────────────────────────────────────

def test_reset_returns_observation(env):
    obs = env.reset(TaskName.BUG_DETECTION)
    assert obs.task == "bug_detection"
    assert obs.step_number == 0
    assert obs.done is False
    assert obs.current_pr is not None
    assert obs.cumulative_reward == 0.0


def test_reset_clears_state(env):
    env.reset(TaskName.BUG_DETECTION)
    env.step(Action(action_type=ActionType.SKIP))
    obs = env.reset(TaskName.BUG_DETECTION)
    assert obs.step_number == 0
    assert obs.cumulative_reward == 0.0
    assert obs.flags_raised == []


def test_reset_all_tasks(env):
    for task in TaskName:
        obs = env.reset(task)
        assert obs.task == task.value
        assert obs.current_pr is not None


# ─── step() ──────────────────────────────────────────────────────────────────

def test_step_requires_reset(env):
    # Stepping without reset should raise
    with pytest.raises(Exception):
        env.step(Action(action_type=ActionType.SKIP))


def test_step_flag_bug_increments_flags(env):
    env.reset(TaskName.BUG_DETECTION)
    action = Action(
        action_type=ActionType.FLAG_BUG,
        bug_category=BugCategory.OFF_BY_ONE,
        line_number=9,
        severity=Severity.HIGH,
    )
    result = env.step(action)
    assert result.observation.step_number == 1
    assert len(result.observation.flags_raised) == 1
    assert result.observation.flags_raised[0]["flag_type"] == "bug"


def test_step_flag_security_increments_flags(env):
    env.reset(TaskName.SECURITY_AUDIT)
    action = Action(
        action_type=ActionType.FLAG_SECURITY,
        security_category=SecurityCategory.SQL_INJECTION,
        line_number=19,
        severity=Severity.CRITICAL,
    )
    result = env.step(action)
    assert len(result.observation.flags_raised) == 1
    assert result.observation.flags_raised[0]["security_category"] == "sql_injection"


def test_step_correct_bug_gives_positive_reward(env):
    env.reset(TaskName.BUG_DETECTION)
    # PR-101 (first PR): off-by-one at line 22 in api/utils.py (retry logic)
    action = Action(
        action_type=ActionType.FLAG_BUG,
        bug_category=BugCategory.OFF_BY_ONE,
        line_number=22,
        severity=Severity.MEDIUM,
    )
    result = env.step(action)
    assert result.reward.value > 0, "Correct bug flag should give positive reward"


def test_step_false_positive_gives_negative_reward(env):
    env.reset(TaskName.BUG_DETECTION)
    action = Action(
        action_type=ActionType.FLAG_BUG,
        bug_category=BugCategory.LOGIC_ERROR,
        line_number=999,  # no bug here
        severity=Severity.MEDIUM,
    )
    result = env.step(action)
    assert result.reward.value < 0, "False positive should give negative reward"


def test_step_skip_gives_negative_reward(env):
    env.reset(TaskName.BUG_DETECTION)
    result = env.step(Action(action_type=ActionType.SKIP))
    assert result.reward.value < 0


def test_step_request_changes_advances_pr(env):
    env.reset(TaskName.BUG_DETECTION)
    pr_count_before = env._pr_index
    env.step(Action(
        action_type=ActionType.REQUEST_CHANGES,
        comment="Issues found: off-by-one and SQL injection."
    ))
    assert env._pr_index == pr_count_before + 1


def test_step_approve_bad_pr_penalises(env):
    env.reset(TaskName.BUG_DETECTION)
    result = env.step(Action(action_type=ActionType.APPROVE, comment="LGTM"))
    # All bug_detection PRs should_approve=False, so approving is wrong
    assert result.reward.value < 0


def test_episode_ends_after_all_prs(env):
    env.reset(TaskName.BUG_DETECTION)
    # 2 PRs in bug_detection; request changes on each
    for _ in range(2):
        result = env.step(Action(
            action_type=ActionType.REQUEST_CHANGES,
            comment="Found issues."
        ))
    assert result.done is True


# ─── state() ─────────────────────────────────────────────────────────────────

def test_state_reflects_actions(env):
    env.reset(TaskName.SECURITY_AUDIT)
    env.step(Action(
        action_type=ActionType.FLAG_SECURITY,
        security_category=SecurityCategory.PATH_TRAVERSAL,
        line_number=19,
        severity=Severity.CRITICAL,
    ))
    s = env.state()
    assert s["step"] == 1
    assert len(s["flags_raised"]) == 1
    assert s["done"] is False


def test_state_task_matches_reset(env):
    env.reset(TaskName.FULL_REVIEW)
    s = env.state()
    assert s["task"] == "full_review"


# ─── grader ──────────────────────────────────────────────────────────────────

def test_grader_score_range(env):
    env.reset(TaskName.BUG_DETECTION)
    env.step(Action(action_type=ActionType.REQUEST_CHANGES, comment="done"))
    env.step(Action(action_type=ActionType.REQUEST_CHANGES, comment="done"))
    score, breakdown = env.grade()
    assert 0.0 <= score <= 1.0


def test_grader_no_flags_low_score(env):
    env.reset(TaskName.SECURITY_AUDIT)
    # Immediately request changes without flagging anything
    env.step(Action(action_type=ActionType.REQUEST_CHANGES, comment="done"))
    env.step(Action(action_type=ActionType.REQUEST_CHANGES, comment="done"))
    score, _ = env.grade()
    assert score < 0.5, "Missing all issues should score below 0.5"


def test_grader_perfect_bug_detection(env):
    """Simulate finding all bugs in bug_detection task."""
    env.reset(TaskName.BUG_DETECTION)
    # PR-101: off-by-one at line 22 (utils.py) + SQL injection at line 17 (users.py)
    env.step(Action(action_type=ActionType.FLAG_BUG,
                    bug_category=BugCategory.OFF_BY_ONE, line_number=22, severity=Severity.MEDIUM))
    env.step(Action(action_type=ActionType.FLAG_SECURITY,
                    security_category=SecurityCategory.SQL_INJECTION, line_number=17, severity=Severity.HIGH))
    env.step(Action(action_type=ActionType.ASSIGN_REVIEWER, reviewer_role=ReviewerRole.BACKEND))
    env.step(Action(action_type=ActionType.REQUEST_CHANGES, comment="Off-by-one in retry logic and SQL injection in get_user endpoint."))
    # PR-102: off-by-one at line 9 + sensitive data exposure at line 43
    env.step(Action(action_type=ActionType.FLAG_BUG,
                    bug_category=BugCategory.OFF_BY_ONE, line_number=9, severity=Severity.HIGH))
    env.step(Action(action_type=ActionType.FLAG_SECURITY,
                    security_category=SecurityCategory.SENSITIVE_DATA_EXPOSURE, line_number=43, severity=Severity.CRITICAL))
    env.step(Action(action_type=ActionType.ASSIGN_REVIEWER, reviewer_role=ReviewerRole.SECURITY))
    env.step(Action(action_type=ActionType.REQUEST_CHANGES,
                    comment="Off-by-one loop bug and CVV/card number sent insecurely. PCI DSS violation."))

    score, breakdown = env.grade()
    assert score > 0.7, f"Perfect review should score > 0.7, got {score}: {breakdown}"


def test_grader_breakdown_has_required_keys(env):
    env.reset(TaskName.BUG_DETECTION)
    env.step(Action(action_type=ActionType.REQUEST_CHANGES, comment="done"))
    _, breakdown = env.grade()
    required = {"bug_recall", "vuln_recall", "precision", "reviewer_correct",
                "final_action", "comment_quality", "efficiency_bonus", "weighted_total"}
    assert required.issubset(set(breakdown.keys()))


def test_grader_deterministic(env):
    """Same actions should always produce same score."""
    def run_fixed_episode():
        e = CodeReviewEnv()
        e.reset(TaskName.BUG_DETECTION)
        e.step(Action(action_type=ActionType.FLAG_BUG,
                      bug_category=BugCategory.OFF_BY_ONE, line_number=9, severity=Severity.HIGH))
        e.step(Action(action_type=ActionType.REQUEST_CHANGES, comment="found issue"))
        e.step(Action(action_type=ActionType.REQUEST_CHANGES, comment="done"))
        return e.grade()[0]

    assert run_fixed_episode() == run_fixed_episode()


# ─── reward shaping ──────────────────────────────────────────────────────────

def test_reward_components_present(env):
    env.reset(TaskName.BUG_DETECTION)
    result = env.step(Action(
        action_type=ActionType.FLAG_BUG,
        bug_category=BugCategory.OFF_BY_ONE,
        line_number=9,
        severity=Severity.HIGH,
    ))
    assert isinstance(result.reward.components, dict)
    assert len(result.reward.components) > 0
    assert result.reward.explanation != ""


def test_step_cost_always_present(env):
    env.reset(TaskName.BUG_DETECTION)
    result = env.step(Action(action_type=ActionType.ADD_COMMENT, comment="This is a comment about the code."))
    assert "step_cost" in result.reward.components
    assert result.reward.components["step_cost"] == -0.02


# ─── max steps ───────────────────────────────────────────────────────────────

def test_max_steps_terminates_episode(env):
    env.reset(TaskName.BUG_DETECTION)
    task_def = TASKS[TaskName.BUG_DETECTION]
    done_result = None
    for _ in range(task_def.max_steps + 5):
        r = env.step(Action(action_type=ActionType.ADD_COMMENT, comment="comment " * 5))
        if r.done:
            done_result = r
            break
    assert done_result is not None, "Episode should terminate at max_steps"
    assert done_result.done is True


# ─── corpus sanity ────────────────────────────────────────────────────────────

def test_all_tasks_have_prs():
    for task in TaskName:
        prs = TASK_PR_MAP[task.value]
        assert len(prs) >= 1, f"Task {task.value} has no PRs"


def test_all_prs_have_ground_truth():
    for task, prs in TASK_PR_MAP.items():
        for apr in prs:
            gt = apr.ground_truth
            total_issues = len(gt.bugs) + len(gt.security_issues)
            assert total_issues > 0, f"{apr.pr.pr_id} has no ground truth issues"
            assert gt.correct_reviewer is not None


def test_all_prs_have_files():
    for task, prs in TASK_PR_MAP.items():
        for apr in prs:
            assert len(apr.pr.files) > 0, f"{apr.pr.pr_id} has no files"
