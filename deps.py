"""Keep the installed Python packages in step with requirements.txt.

Called after every update (web UI Update button, the AIO Builder launcher, /update) so new
dependencies arrive with the code, not only on a fresh install. Checks installed versions first
and runs pip only when something is missing or too old, so it's quick when nothing changed.

    python deps.py                      # install anything missing, print what happened
    python deps.py --check              # report only; exit 1 if something is missing
    python deps.py --requirements FILE  # use another requirements file (e.g. the incoming version's)
"""

import importlib.metadata as md
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REQUIREMENTS = os.path.join(ROOT, "requirements.txt")


def _version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4])


def missing(path=REQUIREMENTS):
    """Requirement lines that aren't satisfied by the running interpreter's packages."""
    out = []
    for line in open(path):
        line = line.split("#")[0].strip()
        if not line:
            continue
        m = re.match(r"^([A-Za-z0-9_.\-\[\]]+)\s*(>=|==|~=)?\s*([0-9][0-9A-Za-z.]*)?", line)
        if not m:
            continue
        name, op, want = re.sub(r"\[.*\]", "", m.group(1)), m.group(2), m.group(3)
        try:
            have = md.version(name)
        except md.PackageNotFoundError:
            out.append(line)
            continue
        if want and op in (">=", "~=") and _version_tuple(have) < _version_tuple(want):
            out.append(line)
        elif want and op == "==" and _version_tuple(have) != _version_tuple(want):
            out.append(line)
    return out


def sync(python=None, log=print, path=REQUIREMENTS):
    """Install missing requirements from `path` with the given interpreter (default: this one).
    Returns {"ok", "installed": [...], "output"}; never raises."""
    python = python or sys.executable
    try:
        need = missing(path)
    except OSError as e:
        return {"ok": False, "installed": [], "output": f"Couldn't read requirements.txt: {e}"}
    if not need:
        return {"ok": True, "installed": [], "output": "Dependencies up to date"}
    log(f"Installing new dependencies: {', '.join(need)}")
    try:
        r = subprocess.run([python, "-m", "pip", "install", "-q", "-r", path],
                           cwd=ROOT, capture_output=True, text=True, timeout=900)
    except Exception as e:
        return {"ok": False, "installed": [], "output": f"pip failed to run: {e}"}
    if r.returncode != 0:
        return {"ok": False, "installed": [], "output": (r.stderr or r.stdout).strip()[-1500:]}
    return {"ok": True, "installed": need, "output": f"Installed: {', '.join(need)}"}


if __name__ == "__main__":
    req = sys.argv[sys.argv.index("--requirements") + 1] if "--requirements" in sys.argv else REQUIREMENTS
    if "--check" in sys.argv:
        need = missing(req)
        print("Missing: " + ", ".join(need) if need else "Dependencies up to date")
        sys.exit(1 if need else 0)
    res = sync(path=req)
    print(res["output"])
    sys.exit(0 if res["ok"] else 1)
