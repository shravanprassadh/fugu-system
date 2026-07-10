#!/usr/bin/env python3
"""Verify the public Fugu deployment without reading or printing secrets."""

from __future__ import annotations

import argparse
import json
import sys

from fugu.production_baseline import ProductionBaselineError, verify_production_deployment


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-url", required=True, help="Public Vercel frontend origin.")
    parser.add_argument("--backend-url", required=True, help="Public Render backend origin.")
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    try:
        report = verify_production_deployment(
            frontend_url=arguments.frontend_url,
            backend_url=arguments.backend_url,
        )
    except ProductionBaselineError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("Fugu production baseline verified.")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
