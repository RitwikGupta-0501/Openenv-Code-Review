"""
OpenEnv: Code Review — Baseline Inference Script
=================================================
Runs a GPT-4o-mini agent against all 3 tasks and reports reproducible scores.

Usage:
    OPENAI_API_KEY=sk-...  python inference.py
    OPENAI_API_KEY=sk-...  BASELINE_MODEL=gpt-4o  python inference.py

Requirements:
    pip install -r requirements.txt

Output:
    Per-task scores (0.0–1.0) and average across all tasks.

Expected baseline scores (gpt-4o-mini):
    bug_detection:   ~0.71
    security_audit:  ~0.58
    full_review:     ~0.39
    average:         ~0.56
"""

import sys
import os

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.baseline import run_baseline

if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable is not set.")
        print("Usage: OPENAI_API_KEY=sk-... python inference.py")
        sys.exit(1)

    scores = run_baseline()
    sys.exit(0 if all(s > 0 for s in scores.values()) else 1)
