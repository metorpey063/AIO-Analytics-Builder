"""Data apps for Tableau Next and Tableau Cloud — one CLI for the /data-app skill and the Web UI.

    python3 -m dataapps next sources --profile <sf connection>
    python3 -m dataapps next build --profile <key> --source <SDM apiName> --dest <workspace name or id>
                                   [--slug S] [--ask "what to answer"] [--feedback "what to change"]
    python3 -m dataapps next repackage --slug S     # republish the recorded app as is (newer AIO components)
    python3 -m dataapps next remove --slug S
    python3 -m dataapps next shot --slug S          # picture of the deployed app (signs in through the sf CLI)

    python3 -m dataapps cloud sources --profile <tableau connection>
    python3 -m dataapps cloud build --profile <key> --source <datasource LUID> --dest <project LUID>
                                    [--slug S] [--ask "..."] [--feedback "..."]
    python3 -m dataapps cloud repackage --slug S    # republish the recorded app as is (newer AIO runtime)
    python3 -m dataapps cloud remove --slug S

    python3 -m dataapps <next|cloud> describe --profile <key> --company "Coeur Mining" --description "..."
                                    [--slug S] [--plan]     # no data yet: design it, mock it, load it, build the app
                                                            # (--plan: design + generate + check only, no org writes)

    python3 -m dataapps <next|cloud> undo --slug S   # put the previous version back and republish it

    python3 -m dataapps status --slug S        # both checkpoints for a demo folder

Claude writes the app (the page and its queries); AIO runs every query against the data before it
publishes, then publishes, deploys and verifies it. --feedback revises the existing app in place.
The app lands in demos/{slug}/ (the source's AIO demo folder when there is one).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataapps import common as C  # noqa: E402


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        sys.exit(__doc__)
    if argv[0] == "status":
        p = argparse.ArgumentParser(prog="dataapps status")
        p.add_argument("--slug", required=True)
        a = p.parse_args(argv[1:])
        print(json.dumps({pl: C.load_cp(a.slug, pl) for pl in C.PLATFORMS}, indent=2))
        return
    if argv[0] not in C.PLATFORMS or len(argv) < 2:
        sys.exit(__doc__)
    platform, cmd = argv[0], argv[1]
    p = argparse.ArgumentParser(prog=f"dataapps {platform} {cmd}")
    p.add_argument("--profile")
    p.add_argument("--source")
    p.add_argument("--dest")
    p.add_argument("--slug")
    p.add_argument("--ask", default="")
    p.add_argument("--feedback", default="")
    p.add_argument("--company", default="")
    p.add_argument("--description", default="")
    p.add_argument("--plan", action="store_true")
    a = p.parse_args(argv[2:])
    engine = __import__(f"dataapps.{platform}", fromlist=["build"])
    if cmd == "sources":
        if not a.profile:
            sys.exit("--profile is required")
        print(json.dumps(engine.sources(a.profile), indent=2))
    elif cmd == "build":
        if not (a.profile and a.source and a.dest):
            sys.exit("--profile, --source and --dest are required")
        engine.build(a.profile, a.source, a.dest, slug=a.slug, ask=a.ask, feedback=a.feedback)
    elif cmd == "describe":
        if not (a.company and a.description) or (not a.plan and not a.profile):
            sys.exit("--company and --description are required (and --profile unless --plan)")
        from dataapps import scenario
        scenario.describe(platform, a.profile, a.company, a.description, slug=a.slug, plan_only=a.plan, ask=a.ask)
    elif cmd in ("repackage", "undo"):
        cp = C.load_cp(a.slug or "", platform)
        if cmd == "undo":
            if not cp.get("history"):
                sys.exit("There is no earlier version of this app to go back to.")
            prev = cp["history"].pop()
            cp["app"] = prev["app"]
            C.save_cp(a.slug, platform, cp)
            print(f"Going back to the version published {prev.get('at') or 'earlier'}", flush=True)
        if not cp.get("app"):
            sys.exit(f"No data app recorded in demos/{a.slug}.")
        if platform == "cloud":
            engine.build(cp["profile"], cp["datasource_id"], cp["project_id"], slug=a.slug, repackage=True)
        else:
            engine.build(cp["profile"], cp["sdm"], cp["workspace"], slug=a.slug, repackage=True)
    elif cmd == "shot":
        if platform != "next" or not a.slug:
            sys.exit("shot is for Tableau Next apps: dataapps next shot --slug S")
        from dataapps.snapshot import next_snapshot
        next_snapshot(a.slug)
    elif cmd == "remove":
        if not a.slug:
            sys.exit("--slug is required")
        engine.remove(a.slug)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
