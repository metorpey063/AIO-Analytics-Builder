#!/usr/bin/env python3
"""
AIO Analytics Builder — One-click installer
Detects existing installations, preserves demos/connections,
creates a virtual environment, installs dependencies, and launches the web UI.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def log(msg, color=GREEN):
    print(f"{color}{BOLD}  → {RESET}{msg}")


def warn(msg):
    print(f"{YELLOW}{BOLD}  ⚠ {RESET}{msg}")


def error(msg):
    print(f"{RED}{BOLD}  ✗ {RESET}{msg}")


def banner():
    print(f"""
{BOLD}  ┌─────────────────────────────────────────┐
  │       AIO Analytics Builder Setup        │
  │                                          │
  │  Tableau Pulse · Tableau Next · Data Cloud│
  └─────────────────────────────────────────┘{RESET}
""")


def prompt_choice(question, options):
    """Display a numbered choice prompt. Returns the 1-based index selected."""
    print(f"  {question}\n")
    for i, opt in enumerate(options, 1):
        print(f"    {BOLD}{i}{RESET}  {opt}")
    print()
    while True:
        try:
            raw = input(f"  Enter choice (1-{len(options)}): ").strip()
            choice = int(raw)
            if 1 <= choice <= len(options):
                print()
                return choice
        except (ValueError, EOFError):
            pass
        print(f"  Please enter a number between 1 and {len(options)}")


def prompt_path(message, default=None):
    """Prompt for a directory path with optional default."""
    suffix = f" [{default}]" if default else ""
    while True:
        raw = input(f"  {message}{suffix}: ").strip()
        path = Path(raw) if raw else (Path(default) if default else None)
        if path and path.exists() and path.is_dir():
            return path.resolve()
        if path:
            print(f"  Directory not found: {path}")
        else:
            print(f"  Please enter a path")


def detect_existing(path):
    """Check what AIO assets exist in a directory."""
    found = {}
    config = path / "config.json"
    if config.exists():
        try:
            cfg = json.loads(config.read_text())
            profiles = cfg.get("profiles", {})
            found["config"] = True
            found["profiles"] = len(profiles)
            found["profile_names"] = [p.get("label", k) for k, p in profiles.items()]
        except (json.JSONDecodeError, KeyError):
            found["config"] = True
            found["profiles"] = 0

    demos_dir = path / "demos"
    if demos_dir.exists():
        demos = [d.name for d in demos_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
        found["demos"] = demos

    found["has_webui"] = (path / "web-ui" / "app.py").exists()
    found["has_venv"] = (path / ".venv").exists()
    found["has_connections"] = (path / "connections.py").exists()

    return found


def show_existing_summary(found):
    """Print what was found in an existing installation."""
    print(f"  {BOLD}Found existing AIO installation:{RESET}\n")
    if found.get("profiles"):
        names = ", ".join(found["profile_names"])
        print(f"    Connection profiles: {BOLD}{found['profiles']}{RESET} ({names})")
    if found.get("demos"):
        print(f"    Demos built:         {BOLD}{len(found['demos'])}{RESET} ({', '.join(found['demos'][:5])}{'...' if len(found['demos']) > 5 else ''})")
    if found.get("has_venv"):
        print(f"    Virtual environment:  exists")
    print()


def choose_install_path():
    """Interactive prompt to determine where to install."""
    choice = prompt_choice(
        "Have you used AIO Analytics Builder before?",
        [
            "Fresh install — this is my first time",
            "Yes — I have an existing AIO installation",
        ]
    )

    if choice == 1:
        log("Fresh install — using current directory")
        return SCRIPT_DIR

    # Existing installation
    print(f"  Point me to your existing AIO directory.")
    print(f"  {DIM}(This is the folder containing connections.py, demos/, etc.){RESET}\n")

    existing_path = prompt_path("AIO directory path", default=str(SCRIPT_DIR))

    found = detect_existing(existing_path)

    if not found.get("has_connections"):
        warn(f"No connections.py found in {existing_path}")
        proceed = prompt_choice(
            "This doesn't look like an AIO installation. Continue anyway?",
            ["Yes — install here anyway", "No — let me pick a different directory"]
        )
        if proceed == 2:
            return choose_install_path()

    show_existing_summary(found)

    if existing_path != SCRIPT_DIR:
        action = prompt_choice(
            "How should I handle the installation?",
            [
                f"Upgrade in place — install web UI into {existing_path.name}/",
                f"Keep both — install fresh here and copy my connections + demos over",
            ]
        )

        if action == 1:
            copy_new_files_to(existing_path)
            return existing_path
        else:
            copy_existing_data_from(existing_path)
            return SCRIPT_DIR
    else:
        log("Installing in current directory — your existing data is preserved")
        return SCRIPT_DIR


def copy_new_files_to(target):
    """Copy new web-ui and installer files into an existing AIO installation."""
    log(f"Copying web UI files to {target.name}/...")

    src_webui = SCRIPT_DIR / "web-ui"
    dst_webui = target / "web-ui"

    if src_webui.exists() and SCRIPT_DIR != target:
        if dst_webui.exists():
            shutil.rmtree(str(dst_webui))
        shutil.copytree(str(src_webui), str(dst_webui))
        log("Copied web-ui/")

    for f in ["install.py", "requirements.txt"]:
        src = SCRIPT_DIR / f
        dst = target / f
        if src.exists() and SCRIPT_DIR != target:
            shutil.copy2(str(src), str(dst))

    # Merge requirements.txt — add any new deps without removing existing ones
    req_target = target / "requirements.txt"
    req_source = SCRIPT_DIR / "requirements.txt"
    if req_source.exists():
        existing_pkgs = set()
        if req_target.exists():
            for line in req_target.read_text().splitlines():
                pkg = line.split(">=")[0].split("==")[0].strip().lower()
                if pkg:
                    existing_pkgs.add(pkg)

        new_lines = []
        for line in req_source.read_text().splitlines():
            pkg = line.split(">=")[0].split("==")[0].strip().lower()
            if pkg and pkg not in existing_pkgs:
                new_lines.append(line)

        if new_lines:
            with open(str(req_target), "a") as f:
                f.write("\n" + "\n".join(new_lines) + "\n")
            log(f"Added {len(new_lines)} new dependencies to requirements.txt")


def copy_existing_data_from(source):
    """Copy config.json and demos/ from an existing installation into the new one."""
    log(f"Copying your data from {source.name}/...")

    config_src = source / "config.json"
    config_dst = SCRIPT_DIR / "config.json"
    if config_src.exists() and not config_dst.exists():
        shutil.copy2(str(config_src), str(config_dst))
        log("Copied config.json (connection profiles preserved)")
    elif config_src.exists() and config_dst.exists():
        warn("config.json already exists here — merging profiles")
        merge_configs(config_src, config_dst)

    demos_src = source / "demos"
    demos_dst = SCRIPT_DIR / "demos"
    if demos_src.exists():
        if not demos_dst.exists():
            demos_dst.mkdir()
        for demo_dir in demos_src.iterdir():
            if demo_dir.is_dir() and not demo_dir.name.startswith("."):
                dst = demos_dst / demo_dir.name
                if not dst.exists():
                    shutil.copytree(str(demo_dir), str(dst))
                    log(f"Copied demo: {demo_dir.name}")
                else:
                    log(f"Demo already exists, skipping: {demo_dir.name}")


def merge_configs(src_path, dst_path):
    """Merge profiles from source config into destination config."""
    try:
        src = json.loads(src_path.read_text())
        dst = json.loads(dst_path.read_text())

        src_profiles = src.get("profiles", {})
        dst_profiles = dst.get("profiles", {})

        added = 0
        for key, profile in src_profiles.items():
            if key not in dst_profiles:
                dst_profiles[key] = profile
                added += 1
                log(f"  Merged profile: {profile.get('label', key)}")

        if added:
            dst["profiles"] = dst_profiles
            dst_path.write_text(json.dumps(dst, indent=2))
            log(f"Merged {added} profile(s) into config.json")
        else:
            log("No new profiles to merge")
    except (json.JSONDecodeError, KeyError) as e:
        warn(f"Could not merge configs: {e}")


# ── Standard install steps ────────────────────────────────────────────────


def check_python():
    v = sys.version_info
    log(f"Python {v.major}.{v.minor}.{v.micro}")
    if v < (3, 10):
        error("Python 3.10+ is required. Please upgrade.")
        error("Download from https://www.python.org/downloads/")
        sys.exit(1)


def create_venv(project_root):
    venv_dir = project_root / ".venv"
    if venv_dir.exists():
        log(f"Virtual environment already exists")
        return venv_dir

    log("Creating virtual environment...")
    venv.create(str(venv_dir), with_pip=True)
    log(f"Created .venv/")
    return venv_dir


def get_pip(venv_dir):
    if platform.system() == "Windows":
        return str(venv_dir / "Scripts" / "pip")
    return str(venv_dir / "bin" / "pip")


def get_python(venv_dir):
    if platform.system() == "Windows":
        return str(venv_dir / "Scripts" / "python")
    return str(venv_dir / "bin" / "python")


def install_deps(project_root, venv_dir):
    pip = get_pip(venv_dir)
    reqs = project_root / "requirements.txt"

    log("Upgrading pip...")
    subprocess.run([pip, "install", "--upgrade", "pip"], capture_output=True)

    log("Installing dependencies...")
    result = subprocess.run(
        [pip, "install", "-r", str(reqs)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        error("Failed to install dependencies:")
        print(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
        sys.exit(1)

    installed = subprocess.run(
        [pip, "list", "--format=columns"],
        capture_output=True, text=True,
    )
    count = max(0, len(installed.stdout.strip().split("\n")) - 2)
    log(f"Installed {count} packages")


def create_config(project_root):
    config_path = project_root / "config.json"
    template_path = project_root / "config.json.template"

    if config_path.exists():
        log("config.json already exists — connections preserved")
        return

    if template_path.exists():
        shutil.copy2(str(template_path), str(config_path))
        log("Created config.json from template")
    else:
        config_path.write_text('{"active_profile": null, "profiles": {}}')
        log("Created empty config.json")


def create_launcher(project_root):
    if platform.system() == "Darwin":
        launcher = project_root / "AIO Builder.command"
        launcher.write_text("""#!/bin/bash
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Run install.py first."
    read -p "Press Enter to exit..."
    exit 1
fi
source .venv/bin/activate
echo ""
echo "  AIO Analytics Builder"
echo "  Starting web server..."
echo ""
python3 web-ui/app.py
""")
        os.chmod(str(launcher), 0o755)
        log(f"Created 'AIO Builder.command' — double-click to launch")

    elif platform.system() == "Windows":
        launcher = project_root / "AIO Builder.bat"
        launcher.write_text("""@echo off
cd /d "%~dp0"
if not exist ".venv" (
    echo Virtual environment not found. Run install.py first.
    pause
    exit /b 1
)
call .venv\\Scripts\\activate
echo.
echo   AIO Analytics Builder
echo   Starting web server...
echo.
python web-ui\\app.py
pause
""")
        log(f"Created 'AIO Builder.bat' — double-click to launch")


def launch_server(project_root, venv_dir):
    python = get_python(venv_dir)
    web_app = project_root / "web-ui" / "app.py"
    log(f"Launching AIO web server on http://localhost:5100 ...")
    print(f"""
{GREEN}{BOLD}  ✓ Setup complete!{RESET}

  The web UI is opening in your browser.
  To launch again later, double-click '{BOLD}AIO Builder.command{RESET}'

  Press Ctrl+C to stop the server.
""")
    os.execvp(python, [python, str(web_app)])


# ── Main ──────────────────────────────────────────────────────────────────


def main():
    banner()
    check_python()

    project_root = choose_install_path()
    log(f"Installing to: {project_root}")

    venv_dir = create_venv(project_root)
    install_deps(project_root, venv_dir)
    create_config(project_root)
    create_launcher(project_root)
    launch_server(project_root, venv_dir)


if __name__ == "__main__":
    main()
