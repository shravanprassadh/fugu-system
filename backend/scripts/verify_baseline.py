#!/usr/bin/env python3
"""Verify Fugu's committed non-secret repository baseline."""

from __future__ import annotations

import json
import sys

from fugu.baseline import BaselineDriftError, verify_repository_baseline


def main() -> int:
    try:
        baseline = verify_repository_baseline()
    except (BaselineDriftError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("Fugu repository baseline verified.")
    print(json.dumps(baseline, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
