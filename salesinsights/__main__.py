"""Sales Insights deploy engine — one CLI for the /deploy-sales-insights skill.

    python3 -m salesinsights capture --from <dir>     # maintainer: Package & Deploy exports -> package/
    python3 -m salesinsights generate [--out <dir>]   # seeded synthetic data -> CSVs (no org writes)
    python3 -m salesinsights check --profile <key>    # read-only preflight (auth, connector, source-org guard)
    python3 -m salesinsights deploy --profile <key>   # checkpointed deploy to a target org
    python3 -m salesinsights status --profile <key>   # what the checkpoint says is deployed
    python3 -m salesinsights reset --profile <key>    # delete only what the deploy created

Commands never prompt; they exit non-zero with a clear message on failure.
"""

import os
import sys


def _arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        sys.exit(__doc__)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cmd = argv[0]
    if cmd == "capture":
        from salesinsights import capture
        src = _arg(argv, "--from") or sys.exit("capture needs --from <dir with the 6 dashboard package exports>")
        capture.capture(src)
    elif cmd == "generate":
        from salesinsights import generate
        generate.write_csvs(_arg(argv, "--out", os.path.join("demos", "sales_insights", "data")))
    elif cmd in ("check", "deploy", "status", "reset"):
        from salesinsights import deploy
        profile = _arg(argv, "--profile") or sys.exit(f"{cmd} needs --profile <config.json profile key>")
        getattr(deploy, cmd)(profile)
    else:
        sys.exit(f"Unknown command {cmd!r}.\n{__doc__}")


if __name__ == "__main__":
    main(sys.argv[1:])
