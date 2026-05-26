# Analytics Builder

A Claude Code tool for Salesforce/Tableau Solutions Engineers to rapidly build compelling demo assets across three platforms: **Tableau Pulse**, **Tableau Next**, and **Salesforce Data Cloud**.

> For a full feature overview, see [OVERVIEW.md](OVERVIEW.md).

---

## What it does

- Generates synthetic data with an engineered story signal (a deliberate metric decline that creates urgency)
- Publishes to Tableau Cloud as a Pulse datasource with metric definitions and group subscriptions
- Pushes to Salesforce Data Cloud and builds a full Tableau Next workspace: Semantic Data Model, metrics, visualizations, and dashboard
- Produces a ready-to-run demo walkthrough document (`.docx`) for the SE to use in front of a customer

---

## Prerequisites

- **Python 3.10+** — check with `python3 --version` in a terminal
- **VS Code** with the **Claude Code extension** installed
- A **Tableau Cloud** site with a Personal Access Token (for Pulse builds)
- A **Salesforce CDO or SDO** with Data Cloud and Tableau Next enabled (for Next builds)

> **Tableau Next orgs take 1–2 hours to provision.** See the setup checklist in `/build-demo` before starting.

---

## Getting started

### Step 1 — Unzip and open the folder

Unzip `Analytics Builder.zip` wherever you want to keep it. Then open the folder in VS Code:

- **File → Open Folder…** → select the `Analytics Builder` folder → click **Open**

### Step 2 — Open a terminal and install dependencies

- In VS Code: **View → Terminal** (or `` Ctrl+` `` / `` Cmd+` ``)
- In the terminal that opens at the bottom, run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> **Windows:** use `.venv\Scripts\activate` instead of `source .venv/bin/activate`

You only need to do this once. The install takes about 30–60 seconds.

> **Every time you reopen VS Code**, re-run `source .venv/bin/activate` before using the tool — otherwise Python won't find the installed packages.

### Step 3 — Open Claude Code and run setup

Open the Claude Code panel in VS Code (click the Claude icon in the sidebar, or use the Command Palette: `Cmd+Shift+P` → "Claude Code"). Make sure the workspace is set to the `Analytics Builder` folder.

In the Claude Code chat, type:

```
/setup
```

Claude will walk you through connecting your Tableau Cloud PAT and/or Salesforce credentials one step at a time, test each connection, and save everything to `config.json`.

### Step 4 — Build a demo

Once setup passes, type:

```
/build-demo
```

Claude will ask for the company name, use case, persona, and story signal — then generate the data, publish to Tableau Cloud and/or Salesforce Data Cloud, and hand you a walkthrough document (`.docx`) when it's done.

### Step 5 — Keep the demo current

Demo data is generated up to today's date. Before showing a demo that was built more than a few weeks ago, run:

```
/refresh-demo
```

This updates the date offset on the Tableau Next Semantic Data Model so the signal always appears current — no data re-ingestion needed. Make it a habit to run this before every demo session.

---

## Project structure

```
analytics-builder/
├── connections.py          # All auth logic — import this everywhere
├── oauth_flow.py           # Salesforce OAuth browser flow (port 8080)
├── setup.py                # Setup wizard logic called by /setup
├── config.json.template    # Safe to commit — shows required fields
├── config.json             # Your credentials — gitignored, never commit
├── requirements.txt
├── CLAUDE.md               # Project instructions for Claude
├── .claude/
│   ├── commands/
│   │   ├── build-demo.md     # /build-demo slash command
│   │   ├── refresh-demo.md   # /refresh-demo slash command
│   │   └── setup.md          # /setup slash command
│   └── settings.local.json # Local Claude permissions (gitignored)
└── demos/                  # Generated demo scripts and outputs (gitignored)
```

---

## Output modes

| Mode | What gets built |
|------|----------------|
| `pulse` | Publishes a `.hyper` datasource to Tableau Cloud, creates Pulse metric definitions, creates a group, subscribes the group to all metrics |
| `next` | Pushes data to Salesforce Data Cloud, builds a Semantic Data Model, metrics, visualizations, and a dashboard |
| `both` | Both of the above |
| `csv` | Exports the generated dataset as a CSV file |

Every build produces a `.docx` demo walkthrough with a focused click path, talking points, and suggested questions — one document per demo, with sections for each output mode that was built.

---

## Multi-org support

`config.json` supports multiple named profiles so you can switch between customer orgs or sandbox environments without re-running setup. Use `/setup` to add or reconfigure a profile.

---

## Security notes

- `config.json` is gitignored — credentials never leave your machine
- The OAuth refresh token is stored locally and only exchanged for short-lived access tokens at runtime
- Claude Code's autonomous mode (which allows script execution without confirmation prompts) is only activated during a build session and reverted immediately after
