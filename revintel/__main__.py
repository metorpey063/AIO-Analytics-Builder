"""Revenue Intelligence demo data engine — one CLI for the /update-rev-intel skill and the web UI.

    python3 -m revintel <demo_folder> inspect            # read-only org survey (JSON report in out/)
    python3 -m revintel <demo_folder> draft [--feedback "…"]   # Claude drafts config.json from the answers + inspect
    python3 -m revintel <demo_folder> plan [--json]      # generate + story stats + CSVs, no org writes
    python3 -m revintel <demo_folder> apply              # write CRM data (checkpointed, insert-only, backups)
    python3 -m revintel <demo_folder> team <phase>       # people (users + lead roles) | quotas | reassign
    python3 -m revintel <demo_folder> roll [--apply] [--close today=3,2026-11-04=1] [--close-only] [--keep "name,name"] [--refresh]   # play the days since the last roll forward, optionally closing deals on given dates (dry run unless --apply)
    python3 -m revintel <demo_folder> add [--apply] [--count N]    # add new expansion deals (dry run unless --apply)
    python3 -m revintel <demo_folder> refresh [--plan] [--skip-sync]   # Data Sync + CRMA recipes in order
    python3 -m revintel <demo_folder> reset              # delete pool opps/contacts/activities (date refresh)

The demo folder holds the customer config (config.py / *_config.py / config.json), pool seed
files and out/. Add --today to re-anchor dates to today (a date refresh: reset, then apply --today).
Commands never prompt; they exit non-zero with a clear message on failure.
"""

import os
import sys


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        sys.exit(__doc__)
    demo, cmd = os.path.abspath(argv[0]), argv[1]
    if not os.path.isdir(demo):
        sys.exit(f"Demo folder not found: {demo}")
    os.environ["REVINTEL_DEMO"] = demo
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    if cmd == "plan":
        from revintel import build
        build.plan(json_out="--json" in argv)
    elif cmd == "apply":
        from revintel import apply as A, build
        A.apply(build.plan())
    elif cmd == "reset":
        from revintel import apply as A
        A.reset()
    elif cmd == "team":
        from revintel import team
        team.run(argv[2] if len(argv) > 2 else None)
    elif cmd == "roll":
        from revintel import roll
        roll.run(apply="--apply" in argv, refresh="--refresh" in argv, force="--force" in argv,
                 on=argv[argv.index("--date") + 1] if "--date" in argv else None,
                 close=argv[argv.index("--close") + 1] if "--close" in argv else None,
                 close_only="--close-only" in argv,
                 keep=argv[argv.index("--keep") + 1] if "--keep" in argv else None,
                 max_deal=int(argv[argv.index("--max-deal") + 1]) if "--max-deal" in argv else None)
    elif cmd == "add":
        from revintel import adddeals
        adddeals.run(apply="--apply" in argv, force="--force" in argv,
                    count=int(argv[argv.index("--count") + 1]) if "--count" in argv else None,
                    on=argv[argv.index("--date") + 1] if "--date" in argv else None)
    elif cmd == "refresh":
        import crma_refresh
        from revintel.config import C
        crma_refresh.refresh(C.ORG_ALIAS, C.REFRESH_APPS, plan_only="--plan" in argv, skip_sync="--skip-sync" in argv)
    elif cmd == "draft":
        from revintel import draft
        fb = argv[argv.index("--feedback") + 1] if "--feedback" in argv else None
        draft.run(fb)
    elif cmd == "inspect":
        from revintel import inspect_org
        inspect_org.run()
    else:
        sys.exit(f"Unknown command {cmd!r}.\n{__doc__}")


if __name__ == "__main__":
    main(sys.argv[1:])
