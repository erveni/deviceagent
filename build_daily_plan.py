#!/usr/bin/env python3
"""Canonical daily entry point: eight prompt types per campaign/location.

DATE selects the logical run date. DRY_RUN=1 performs catalog planning only.
PLAN_PATH must be new for a real build; historical plans are never overwritten.
The previous five/12-session planner remains recoverable in Git history.
"""
from build_daily_eight import main

if __name__ == '__main__':
    main()
