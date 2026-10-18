# AiO 2.0 Claude Code Playbook (Jacob's lane)

Copy-paste prompts for Claude in VS Code, in the same order as the plan doc. Lane: Tableau Studio, Slack trigger after the "aha", and closing the loop.

Deadline: video submitted by **Wed 10/21, 11:59pm PT** (target 9:00pm PT).

---

## How to use this file

- Open the AiO repo in VS Code and start Claude Code from the extension panel.
- Save this file in the repo as `docs/v2/PLAYBOOK.md`, so you can `@`-mention it.
- **Plan mode** (Shift+Tab until it says plan mode): use it for any prompt marked **[PLAN]**. Claude proposes changes without editing. Approve, then let it run.
- Run `/clear` between steps so each one starts with a clean context. The project `CLAUDE.md` (Step 0.3) carries the background forward.
- Replace anything in `<ANGLE_BRACKETS>` before you paste.
- After each step, run the end-of-step prompt in the [Utility prompts](#utility-prompts) section to commit and log progress.

### Safety rules (read once)

- The Studio guide is marked **confidential and pre-release**. If the AiO repo is public, or shared beyond the team, keep the guide in a git-ignored folder (Step 0.2 sets this up).
- Never paste the Studio discovery-file token, Slack webhook URLs, or Salesforce tokens into chat. Keep them in `.env` (git-ignored) and have scripts read them from there.
- Use synthetic or placeholder data (e.g., `CUSTOMER_1`) in anything posted to Slack during testing.

---

## Step 0: One-time setup (Thu, ~15 min)

### 0.1 Branch

```text
Create and check out a branch named feature/v2-studio-trigger from the latest main. Show me git status and the last 5 commits on main so I know what I'm branching from.
```

### 0.2 Put the reference docs in the repo

Copy `tableau-studio-guide.md`, `AIO_CURRENT_PROCESS.md`, and (if you have it) `tableau-external-client-api-reference.md` into `docs/v2/private/`. Then:

```text
Add docs/v2/private/ and .env to .gitignore if they aren't already ignored. Confirm with git check-ignore that docs/v2/private/tableau-studio-guide.md and .env are ignored. Do not commit anything in docs/v2/private/.
```

### 0.3 Project context for Claude

```text
Append a section called "AiO v2: Jacob's lane" to CLAUDE.md at the repo root (create the file if it's missing). Keep it under 40 lines and include:
- Goal: after the demo "aha" (the "Who needs action?" segment), AiO v2 (1) builds the story workbook in Tableau Studio through the External Client API, connected to the Data 360 semantic model, (2) ships an AiO skill for Tableau Agent, (3) posts the finding to Slack with a button that creates a Salesforce Task through a Flow, and (4) as a stretch, measures whether the action happened.
- Reference docs: docs/v2/private/tableau-studio-guide.md (confidential, never commit), docs/v2/private/AIO_CURRENT_PROCESS.md, docs/v2/PLAYBOOK.md.
- Teammates' lanes: Matthew Torpey owns the single SDM; Jordan Bethea owns Puppet Mode (natural-language driving of Studio through Tableau MCP). Don't modify their modules without asking me.
- Rules: secrets only in .env; never print the Studio discovery token; every new /build-demo phase writes to the existing checkpoint file so reruns skip completed phases; prefer deterministic API calls over LLM steps in the build path.
- Deadline: video due Wed 10/21 11:59pm PT; code freeze Tue 10/20 end of day.
Show me the diff before saving.
```

### 0.4 Orient on the codebase **[PLAN]**

```text
Read @CLAUDE.md and @docs/v2/private/AIO_CURRENT_PROCESS.md, then explore the repo. Don't edit anything. Give me:
1. Where /build-demo is defined and how its phases run, in order, with file paths.
2. How the checkpoint file is written and read, and how a rerun skips a phase.
3. Where the story metadata lives (primary metric, worst segments, the "Who needs action?" cut) and what it looks like.
4. How the existing Pulse .twb workbook and the walkthrough .docx are generated.
5. Your recommendation for where to add three things: a "studio" output, a "close-loop" phase or command, and a Tableau Agent skill folder.
Keep it to one page.
```

---

## Thursday 10/15: Kickoff and Studio spike (2.5h)

### 1.1 Kickoff message (draft only)

```text
Draft a short Slack message to Matt and Jordan for today's kickoff. Propose this split: Jordan owns live, natural-language driving of Tableau Studio through Tableau MCP (Puppet Mode); I own the deterministic External Client API build step, the AiO skill inside Tableau Agent, the Data 360 connection, and the post-aha Slack action. Ask them to confirm: demo customer and story, shared demo org, Slack workspace, branch names, Monday 10/19 as integration day, and who has an internal Studio build. Under 120 words. Draft only, don't send it.
```

### 1.2 Studio API smoke test

Open Tableau Studio first and wait for it to finish loading.

```text
Using @docs/v2/private/tableau-studio-guide.md (section "Directly call the Tableau External Client API"), create scripts/studio/studio_client.py:
- Find the newest discovery file in ~/Library/Application Support/Tableau/Tableau/ExternalApi/<pid>.json (macOS) or %LOCALAPPDATA%/Tableau/Tableau/ExternalApi/ (Windows), and skip files whose pid isn't running.
- Expose a small client: health(), get(path), post(path, body), handling HTTP 202 by polling for up to 30s.
- Never print or log the token. Mask it as *** in any error output.
- Add a CLI: python scripts/studio/studio_client.py health | workbook | site-workbooks.
Then run health, workbook, and site-workbooks, and show me the output with the apiVersion and applicationVersion from the discovery file.
```

### 1.3 Map the API surface

If you have `tableau-external-client-api-reference.md`:

```text
Read @docs/v2/private/tableau-external-client-api-reference.md. Make a table of every endpoint grouped by category (Application, Dashboards, Service, Site, Storyboards, Workbook, Worksheets), with method, path, and one-line purpose. Then answer yes or no, with the endpoint: can the API (a) connect or add a data source, (b) create a worksheet, (c) put fields on rows, columns, color, or filters, (d) create a dashboard and add sheets, (e) set titles and formatting, (f) save or publish the workbook? Save the result to docs/v2/studio-api-map.md.
```

If you don't have it:

```text
Use scripts/studio/studio_client.py to probe the API. Try GET on v0/workbook, v0/site/workbooks, and any discovery, OpenAPI, or schema endpoints you can find (e.g., v0/openapi.json, v0/docs). Report what exists. Don't make any write calls yet.
```

### 1.4 Tableau MCP headless check (internal build only)

```text
Following the "Use Your Agent to Author with Tableau MCP" section of @docs/v2/private/tableau-studio-guide.md: clone https://github.com/tableau/tableau-mcp into ~/dev/tableau-mcp, check out feature/desktop, run npm ci and npm run build, then register it as a project-scoped MCP server named tableau-desktop (stdio, node build/index.desktop.js, env TRANSPORT=stdio and TABLEAU_EXTERNAL_API=true). Tell me when it's done so I can restart and run /mcp to confirm it connected. Check that Node is 22.7.5 or later first.
```

After restarting, test it:

```text
Using the tableau-desktop MCP server, tell me which workbooks are open in Tableau Studio and list the worksheets in the active one. Don't change anything.
```

If this fails because you don't have an internal build, note it for Jordan and move on. The API path doesn't need MCP.

### 1.5 Data 360 connection test

```text
I need the Studio workbook connected to the Data 360 semantic model (Tableau Semantics) that Matt's SDM creates. Based on docs/v2/studio-api-map.md and the guide, tell me whether this can be done through the External Client API. If it can, write and run the calls against the demo org's semantic model <SEMANTIC_MODEL_NAME>. If it can't, give me the shortest manual click path in Studio, and a script that verifies afterward, through the API, that the workbook has that data source attached.
```

### 1.6 Can a Tableau Agent skill call out to Slack?

```text
Create a minimal Tableau Agent skill to test whether a skill can run a local script that makes a network call. Follow the "Author a skill by hand" rules in @docs/v2/private/tableau-studio-guide.md (kebab-case name matching the folder, frontmatter with name and description, short body, scripts in scripts/).
- Skill name: aio-ping. Trigger phrase: "aio ping".
- It runs scripts/ping.py, which posts "AiO ping from Tableau Agent" to the Slack incoming webhook in the SLACK_WEBHOOK_URL environment variable (read from ~/.aio/.env).
- Put the source in tableau_agent_skills/aio-ping/ in this repo, and write scripts/install_tableau_skills.sh to copy every folder in tableau_agent_skills/ to "~/Documents/My Tableau Repository (Beta)/Tableau Agent/skills/".
Run the installer, then tell me exactly what to do in Studio (/reload-skills, then "aio ping") and where to look in the Tableau Agent logs if it fails.
```

### 1.7 Slack and Flow access check

```text
Check what I can do in the demo org. Use the Salesforce CLI with org alias <DEMO_ORG_ALIAS> (if it isn't authorized, give me the sf org login web command). Report: (1) whether my user can create and activate Flows, (2) whether a Screen Flow can be launched by URL with input variables, (3) whether the org has the Salesforce for Slack integration or Slack actions in Flow, and (4) whether Named Credentials or HTTP Callout actions are available in Flow. Read-only, change nothing.
```

---

## Friday 10/16: Studio build phase and first Slack message (2.5h)

### 2.1 Design the Studio phase **[PLAN]**

```text
Plan a new "studio" output for /build-demo. Use docs/v2/studio-api-map.md, your notes from the codebase walkthrough, and the story shape in AIO_CURRENT_PROCESS.md (What is wrong, Where is it worst, Why, Who needs action). Propose:
- Four worksheets, one per story question, with the exact fields from the story dataset and SDM for each, plus the chart type for each.
- One dashboard that lays them out in story order, titled from the company and use case.
- The ordered list of External Client API calls, and the checkpoint keys each step writes.
- What falls back to Tableau Agent or a manual step if an endpoint is missing.
Write the plan to docs/v2/studio-phase-design.md. Don't write code yet.
```

### 2.2 Build it

```text
Implement docs/v2/studio-phase-design.md:
- Add a studio builder module that uses scripts/studio/studio_client.py.
- Register "studio" as an output choice in /build-demo, and write checkpoint entries per step so a rerun skips completed steps.
- Add a --dry-run flag that prints the API calls without sending them.
Run it in dry-run mode on the most recent demo in demos/, then for real against the open Studio workbook. Show me the result of GET v0/workbook afterward, so I can confirm the four sheets and the dashboard exist.
```

### 2.3 First Slack message

```text
Create scripts/slack/post_insight.py. It takes a JSON insight payload (company, metric name, segment, current value, prior value, percent change, recommended owner, and a follow-up URL) and posts a Slack Block Kit message to SLACK_WEBHOOK_URL from .env with:
- A header line naming the problem in plain words.
- A section with metric, segment, and change, formatted as a percentage.
- A "Create follow-up" URL button that opens the follow-up URL. A URL button means we don't need a Slack interactivity endpoint.
Add --dry-run to print the Block Kit JSON. Generate a test payload from the latest demo's story metadata, using placeholder names, and post it to my test channel.
```

---

## Saturday 10/17: Flow and an end-to-end click (1.5h)

### 3.1 Build the Flow **[PLAN first]**

```text
Plan, then build, a Screen Flow named AiO_Create_Followup in Salesforce metadata (force-app/ or this repo's existing metadata folder):
- Input variables (available for input): segment, metric, changePct, ownerName, accountId (optional), demoSlug.
- One screen that shows a pre-filled summary and a Confirm button.
- On confirm: create a Task with Subject "AiO follow-up: <metric> in <segment>", the details in Description, Type "AiO Alert" (or a Subject prefix if we don't want a custom picklist value), ActivityDate today + 2, and OwnerId set to the running user.
- Optionally, if a Named Credential for the Slack webhook exists, post "Follow-up created" back to Slack.
Deploy to <DEMO_ORG_ALIAS> with the sf CLI, activate it, and give me the launch URL format with input variables in the query string.
```

### 3.2 Connect the button

```text
Update scripts/slack/post_insight.py so the "Create follow-up" button URL is the AiO_Create_Followup launch URL for <DEMO_ORG_ALIAS>, with the payload values URL-encoded as Flow inputs. Post a test message. After I click it and confirm, run a SOQL query to show me the Task that was created.
```

---

## Sunday 10/18: AiO skill in Tableau Agent and the close-loop phase (1.5h)

### 4.1 AiO story skill for Tableau Agent

```text
Using the skill rules in @docs/v2/private/tableau-studio-guide.md ("Author a skill by hand"), write tableau_agent_skills/aio-story/SKILL.md, keeping the body under 150 lines:
- Description triggers on: "walk the AiO story", "where is it worst", "who needs action", "send this to the owner".
- Body: how to read the AiO story sheets in the open workbook, how to answer the four story questions in order, and the counter-trend segment rule (at least one segment is flat or improving).
- "Send to owner" step: build the insight payload from the active sheet's selection or the story metadata, then run scripts/send_to_owner.py, which calls the same logic as scripts/slack/post_insight.py.
- Put long reference material in references/, not in the body.
Install it with scripts/install_tableau_skills.sh, and tell me the prompts to test it in Studio after /reload-skills, including two that should NOT trigger it.
```

### 4.2 Close-loop phase in AiO

```text
Add a close-loop step to AiO. It can be a new phase that runs after the walkthrough in /build-demo, or a /close-loop command; pick whichever fits the existing command structure and tell me why. It should:
- Read the story metadata for the "Who needs action?" segment and build the insight payload.
- Post it with scripts/slack/post_insight.py (respecting --dry-run).
- Record the post in the checkpoint so a rerun doesn't post twice.
- Add a "Close the loop" section to the walkthrough .docx: what the alert says, what the button does, and what to click during the demo.
Run it end to end on the latest demo.
```

---

## Monday 10/19: Integration (2.5h)

### 5.1 Merge teammates' work

```text
Fetch all remote branches. Show me what's new on Matt's SDM branch <MATT_BRANCH> and Jordan's Puppet Mode branch <JORDAN_BRANCH> since main, as file lists and a short summary for each. Then merge them into my branch one at a time (SDM first). If there are conflicts, stop and explain each one before resolving it. Don't force-push.
```

### 5.2 Clean full run

```text
Run a full clean build of the team's chosen demo <COMPANY>_<USE_CASE> from scratch: Tableau Next on the shared SDM, then the studio output, then close-loop. Before you start, list what you'll delete from the previous checkpoint. Log every phase's start, end, and duration. If a phase fails, stop, show me the error, and propose a fix. At the end, give me a pass or fail table per phase.
```

### 5.3 Video outline (team sync)

```text
Draft a 5-minute video outline for the team: Problem (30s), Matt's SDM, Jordan's Puppet Mode driving Studio, my segment (about 75s: story in Studio on Data 360, "send this to the owner", Slack alert, one click creates the Task in Salesforce, then the loop metric if ready), and Result (30s, with time saved per SE demo build). Map each beat to the judging criteria: Tableau Depth, Impact, Build Quality, Innovation, Pitch, and the bonus multiplier. Include a timing column. Save it to docs/v2/video-outline.md.
```

---

## Tuesday 10/20: Hardening, stretch decision, code freeze (2.5h)

### 6.1 Preflight check

```text
Create scripts/preflight.py that checks, in order, and prints pass or fail with a fix hint for each: Tableau Studio is running and v0/health is OK; the story workbook is open and has the four sheets and the dashboard; the AiO skills are installed in the Tableau Agent skills folder; SLACK_WEBHOOK_URL is set and a dry-run payload is valid; <DEMO_ORG_ALIAS> is authorized; the AiO_Create_Followup Flow is active; the Data 360 semantic model is reachable. Run it.
```

### 6.2 Stretch: close-the-loop metric

Pick one option.

Option A, CRM loop metric (low cost):

```text
Add a loop metric for the demo: the count of Tasks with Type "AiO Alert" (or our Subject prefix) created and closed since the alert. Work with Matt's SDM code to add Task as a source and a metric in the semantic model. If that won't be ready by tonight, fall back to a SOQL-backed number that the walkthrough doc and Slack confirmation can show. Tell me which path you took.
```

Option B, Tableau Agent ask ledger (customer-zero angle):

```text
Write scripts/analytics/ask_ledger_report.py to parse "~/Documents/My Tableau Repository (Beta)/Tableau Agent/logs/ask-ledger.jsonl": count asks, tools called, failures (is_error true), and time per ask, for today's demo build session. Output a CSV we could load into Data 360, and a three-line summary I can say in the video ("X asks, Y tool calls, Z errors, built in N minutes"). Don't include prompt text in the output.
```

### 6.3 Backup and freeze

```text
Run scripts/preflight.py, then do a full dry run of my demo segment. After I confirm it worked: commit everything, tag the commit v2.0-freeze-jacob, push the branch, and save the open Studio workbook to demos/<COMPANY>_<USE_CASE>/ as a backup.
```

---

## Wednesday 10/21: Record and submit

### 7.1 Reset demo state

```text
Reset the demo to a clean state for recording. List the AiO Alert Tasks created today in <DEMO_ORG_ALIAS> and delete them only after I confirm. Delete the test messages in Slack if the webhook allows it (otherwise tell me which to delete by hand). Re-open the saved Studio workbook, then run scripts/preflight.py.
```

### 7.2 Talk track

```text
From docs/v2/video-outline.md, write my word-for-word talk track for my ~75-second segment, with the on-screen action for each line. About 190 words. Plain language, no jargon the judges would need explained.
```

### 7.3 Submission checklist

```text
Give me a submission checklist: video length 5:00 or less, the file name, every teammate's name in the submission, the contest Slack workflow steps, and a fallback if the upload fails. Target submission is 9:00pm PT.
```

---

## Utility prompts

### End of each step: commit and log

```text
Summarize what changed in this step in three bullets. Commit with a clear message (no secrets, nothing from docs/v2/private/). Then append today's date, the step number, and those bullets to docs/v2/progress-log.md.
```

### Where am I versus the plan?

```text
Compare docs/v2/progress-log.md with the day-by-day plan in @docs/v2/PLAYBOOK.md. Today is <DAY>. Tell me: what's done, what's behind, and what to cut, following the cut order: Agent Analytics build first, then the Slack button (keep the notification), then the Tableau Agent skill, then Studio API automation (keep a saved workbook).
```

### Studio debugging

```text
A Studio step failed: <PASTE ERROR, WITH ANY TOKEN REMOVED>. Using the Troubleshooting section of @docs/v2/private/tableau-studio-guide.md, check in this order: any Studio error dialog text I give you; ask-ledger.jsonl for "is_error": true; the latest desktop-mcp-*.log for error, warning, Timeout, or validation lines; tab-agent.log for ERROR or WARNING lines; and Logs/log.txt for connectivity, hyper, or excp lines. Show only the relevant lines near <TIME>, then propose a fix.
```

### Team update (draft)

```text
Draft a 5-line Slack update for Matt and Jordan from today's entries in docs/v2/progress-log.md: done, next, blocked, and what I need from each of them. Draft only.
```
