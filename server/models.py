"""
OpenEnv typed models: Observation, Action, Reward, StepResult.
Full Pydantic v2 annotations per OpenEnv spec.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# ─── Enums ───────────────────────────────────────────────────────────────────

class TaskName(str, Enum):
    BUG_DETECTION    = "bug_detection"       # Easy:   spot logical / runtime bugs
    SECURITY_AUDIT   = "security_audit"      # Medium: find security vulnerabilities
    FULL_REVIEW      = "full_review"         # Hard:   comprehensive multi-dimension review


class BugCategory(str, Enum):
    LOGIC_ERROR       = "logic_error"
    NULL_POINTER      = "null_pointer"
    OFF_BY_ONE        = "off_by_one"
    RACE_CONDITION    = "race_condition"
    MEMORY_LEAK       = "memory_leak"
    INFINITE_LOOP     = "infinite_loop"
    TYPE_ERROR        = "type_error"
    UNHANDLED_EXCEPTION = "unhandled_exception"


class SecurityCategory(str, Enum):
    SQL_INJECTION      = "sql_injection"
    XSS                = "xss"
    HARDCODED_SECRET   = "hardcoded_secret"
    PATH_TRAVERSAL     = "path_traversal"
    INSECURE_DESERIALIZATION = "insecure_deserialization"
    BROKEN_AUTH        = "broken_auth"
    SENSITIVE_DATA_EXPOSURE = "sensitive_data_exposure"
    COMMAND_INJECTION  = "command_injection"


class Severity(str, Enum):
    CRITICAL  = "critical"
    HIGH      = "high"
    MEDIUM    = "medium"
    LOW       = "low"
    INFO      = "info"


class ReviewerRole(str, Enum):
    BACKEND    = "backend"
    FRONTEND   = "frontend"
    SECURITY   = "security"
    DEVOPS     = "devops"
    SENIOR     = "senior"      # for complex / architecture issues


class ActionType(str, Enum):
    FLAG_BUG        = "flag_bug"        # Report a bug at a specific line
    FLAG_SECURITY   = "flag_security"   # Report a security vulnerability
    ADD_COMMENT     = "add_comment"     # Leave an inline review comment
    ASSIGN_REVIEWER = "assign_reviewer" # Route PR to a specific reviewer role
    REQUEST_CHANGES = "request_changes" # Block merge; summarise all issues found
    APPROVE         = "approve"         # Approve the PR (with optional notes)
    SKIP            = "skip"            # Move on without reviewing current file


# ─── Code Diff ───────────────────────────────────────────────────────────────

class FileDiff(BaseModel):
    filename: str
    language: str          # python | javascript | typescript | go
    patch: str             # unified diff format
    additions: int
    deletions: int


class PullRequest(BaseModel):
    pr_id: str
    title: str
    description: str
    author: str
    base_branch: str = "main"
    files: list[FileDiff]
    language: str          # primary language of the PR
    total_additions: int
    total_deletions: int


# ─── Observation ─────────────────────────────────────────────────────────────

class Observation(BaseModel):
    """Returned by reset() and step(). Full view the agent gets each turn."""
    task: str
    step_number: int
    current_pr: Optional[PullRequest]
    current_file_index: int = Field(description="Which file in the PR is being reviewed (0-indexed)")
    prs_remaining: int      = Field(description="PRs left in the review queue")
    flags_raised: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Issues flagged so far in the current PR"
    )
    cumulative_reward: float
    elapsed_steps: int
    message: str
    done: bool = False


# ─── Action ──────────────────────────────────────────────────────────────────

class Action(BaseModel):
    """
    Agent action. Required fields vary by action_type — see field descriptions.
    """
    action_type: ActionType

    # FLAG_BUG
    bug_category: Optional[BugCategory] = Field(
        default=None,
        description="Required for FLAG_BUG: category of the bug found"
    )
    line_number: Optional[int] = Field(
        default=None,
        description="Required for FLAG_BUG / FLAG_SECURITY / ADD_COMMENT: line in the patch"
    )
    severity: Optional[Severity] = Field(
        default=None,
        description="Required for FLAG_BUG and FLAG_SECURITY: how severe is this issue"
    )

    # FLAG_SECURITY
    security_category: Optional[SecurityCategory] = Field(
        default=None,
        description="Required for FLAG_SECURITY: type of security vulnerability"
    )

    # ADD_COMMENT / REQUEST_CHANGES / APPROVE
    comment: Optional[str] = Field(
        default=None,
        description="Required for ADD_COMMENT, REQUEST_CHANGES, APPROVE: the review text"
    )

    # ASSIGN_REVIEWER
    reviewer_role: Optional[ReviewerRole] = Field(
        default=None,
        description="Required for ASSIGN_REVIEWER: which team/role to route to"
    )


# ─── Reward ──────────────────────────────────────────────────────────────────

class Reward(BaseModel):
    value: float = Field(description="Step reward in range [-1.0, 1.0]")
    components: dict[str, float] = Field(
        description="Named sub-rewards for interpretability"
    )
    explanation: str


# ─── Step Result ─────────────────────────────────────────────────────────────

class StepResult(BaseModel):
    observation: Observation
    reward:      Reward
    done:        bool
    info:        dict[str, Any] = Field(default_factory=dict)
