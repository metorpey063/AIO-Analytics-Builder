# /close-loop — Build the demo's follow-up action into the org

Closes the loop on an AiO demo story. It **builds ONE follow-up action into the demo org**, so the audience can trigger it during the meeting. Claude Code is not running at demo time; Salesforce closes the loop itself.

What gets installed (Flows, deployed via the Metadata API):
- **Follow-up Flow** (`AiO_{Slug}_Followup`): creates the story's records. These are Tasks per at-risk entity, an escalation Case, or a recovery Campaign, each carrying the drill path and evidence.
- **Notify Flow** (`AiO_{Slug}_Notify`): when the follow-up runs, posts an "action taken" card to Slack through the native Slack action. If Slack isn't connected, it posts to Chatter instead.
- **ONE trigger**, chosen from the story:

| Trigger | How the audience fires it | Default when |
|---|---|---|
| `slack_button` | An insight card in Slack has a **Create follow-ups** link. It opens a confirmation screen that runs the follow-up. | Task / Campaign stories (Pulse and Next) |
| `record_triggered` | A Task whose Subject starts with `AiO Signal: {Metric}` (a threshold breach) runs the follow-up automatically | Case stories (stockout, SLA, route: operational breaches) |
| Agentforce action | Coming in P2: "create follow-ups for the at-risk accounts" | Tableau Next builds, once available |

**Default: one follow-up per demo.** Build more only if the user asks.

It runs standalone against any `demos/{slug}/` and is also offered as the final, optional step of `/build-demo` ("Close the loop"). It adds **Section 7 "Close the Loop"** to the walkthrough `.docx` (Say: / Trigger: / Result: per step, so the presenter knows what to speak to) and a hand-off line at the end of Section 3.

All logic lives in `close_loop.py` (story analysis, Flow generation, deploy). The Flow XML builders live in `close_loop_flows.py`. This command only orchestrates.

## Usage

- `/close-loop {slug}`: plan, confirm, build (deploy), document
- `/close-loop {slug} --test`: rehearse; fires the installed trigger once
- `/close-loop {slug} --reset`: delete the records created by rehearsal
- `/close-loop {slug} --remove`: undeploy the Flows this tool installed
- `/close-loop {slug} --preflight`: read-only org check

If no slug is given, list the `demos/` folders and ask which one. Add `--profile {key}` to target a `/setup` profile other than the active one (e.g. another SE's org).

## Steps

### 1. Source
- **AiO demo folder (default):** `demos/{slug}/` containing the `*_demo.py`, a CSV, and the checkpoint. Nothing more is needed.
- **Existing demo from outside AiO** (only when the SE brings one): ask for the CSV and create `demos/{slug}/` with the CSV and a minimal `{slug}_checkpoint.json` containing `{"story": {company, date_field, entity_field, dimensions}}`. The analysis needs a date column, a primary metric, 2+ segment dimensions, and an entity column. If the metric isn't the first numeric column, write a one-entry `METRIC_CONFIG` in `{slug}_demo.py` (`label`, `field`, `agg`, `sentiment`). A loader for an existing Tableau Next SDM is planned (P3).

### 2. Plan (no org changes)
Run `python close_loop.py plan --slug {slug}`. Show the user:
- the story headline and drill path
- the **action** (records) and the **trigger**, each with its reason
- the Flow names to be deployed
- the Section 7 preview: each step's **Say:** talk track, **Trigger:** and **Result:**. Ask whether the talk track reads right; wording is generated from the story, so if it's off, adjust the plan (`--action`/`--trigger`) or note edits to make in the .docx after build

Let them override: `--action task|case|campaign`, `--trigger slack_button|record_triggered`.

### 2b. Where should the team be told? (Slack or Chatter)

Ask this every time close-loop is built, whether it's run standalone or as the `/build-demo` add-on. It's the only place Slack is set up; `/setup` never asks. Skip the question only if the checkpoint already has `close_loop.notify` from an earlier build and the user didn't ask to change it. In that case, say "Using {Slack #channel | Chatter} like last time" and carry on.

> "When the follow-up runs, where should the team be told?
> 1. **Slack**: an 'action taken' card in a Slack channel. This is the most impressive option, but the org must be connected to Slack. I'll check that now and walk you through anything missing.
> 2. **Chatter**: a post on the record's Chatter feed. It works in every org with no setup.
>
> {If `trigger` is `slack_button`: "This demo's trigger is an alert card with a *Create follow-ups* link. It posts wherever you choose, as a Slack card or a Chatter post."}"

**If Chatter:** use `--notify chatter`. Re-run `plan --notify chatter` so the demo steps say "Chatter", show them, and go to Step 3.

**If Slack:** run the guided check, which is read-only:

1. Run `python close_loop.py slack-check --slug {slug} [--profile K]`. It prints JSON with `ready`, `issues` (each with `code`, `problem`, `fix`), `suggested` (IDs found in the org's existing Slack Flows) and `saved`.
2. If `ready` is true, say "Slack is connected and will post to #{channel_name or channel_id}" and go to Step 3 with `--notify slack`.
3. If `ready` is false, troubleshoot **one issue at a time**, in the order listed. Explain each `problem` in plain words, give the `fix` as numbered click-steps, then wait for the user:
   - **`org_not_connected`**: the org-side Slack connection is missing, and only the user can fix it in Salesforce Setup or Slack. Walk them through the `fix`, ask them to say "done", then re-run `slack-check`. If they can't do it now (no admin access, or no Slack workspace), offer Chatter. Don't loop more than twice on this.
   - **`no_channel` / `bad_channel` / `no_workspace` / `bad_workspace` / `enterprise_id` / `bad_app_id`**: ask the user for the value, following the `fix`. If `suggested` has a value for that field, offer it first: "I found workspace `T…` / app `A…` in an existing Slack Flow in this org. Use it?" Save the values with
     `python setup_slack.py --channel-id C… --workspace-id T… [--channel-name name] [--app-id A…] [--profile K]`
     then re-run `slack-check`. Only pass the flags you have values for; saved values are kept.
   - **`missing_inputs`**: usually the App ID. Use `suggested.app_id` if present (save with `--app-id`). Otherwise explain the `fix`, which is to build one Slack "Send Message" Flow in Flow Builder once, then re-check. Offer Chatter if they'd rather not.
   - **`no_tooling`**: the user lacks admin rights. Flows can't be activated with either option, so stop and tell them to use a System Administrator profile.
4. Also remind them that **the Salesforce app must be invited to the channel** (in Slack: `/invite @Salesforce` in the channel). The check can't verify this, so it's the most common reason a ready setup still doesn't post.
5. Once `ready` is true, go to Step 3 with `--notify slack`. If the user gives up at any point, use `--notify chatter`. The demo still lands.

Never write inline Python for these checks; use only the two commands above.

### 3. Build: confirm first
Deploying changes the org. Ask: "Deploy {N} Flows to {org} (profile {key})? Notify goes to {Slack #channel | Chatter}." Skip the question only if the user already said "build" or "deploy" in this request.

Run `python close_loop.py build --slug {slug} --notify slack|chatter [--action X] [--trigger Y] [--profile K]`. The choice is saved to the checkpoint (`close_loop.notify`), so re-builds reuse it. With `--notify slack`, build stops with the list of fixes if Slack has stopped being ready; go back to Step 2b. It will:
1. Preflight the org (createable objects, Slack action and inputs, Tooling API)
2. Generate the Flows into `demos/{slug}/close_loop_metadata/` and deploy them, then record the names in `cp.close_loop.deployed` (asset ownership)
3. Activate them. Production orgs deploy Flows inactive unless "Deploy processes and flows as active" is on.
4. Write **Section 7 "Close the Loop"** (Say / Trigger / Result) into the walkthrough `.docx`, replacing any earlier version, and add the hand-off line at the end of Section 3

To validate without saving anything, run `--check-only` first.

Relay the demo steps to the user. For `slack_button`, remind them that the alert has to be posted (by `--test`) before the meeting or live.

### 4. Test / Reset (rehearsal)
- **Test.** Confirm first: it creates real records and posts to the shared channel. Run `python close_loop.py test --slug {slug}`.
  - `slack_button`: posts the alert card. The user clicks the link to finish.
  - `record_triggered`: creates the signal Task. Then show the created record links.
  - `--step followup` runs the follow-up Flow directly, skipping the trigger.
- **Reset.** Run `python close_loop.py reset --slug {slug}`.
  - It deletes the test records tracked in the checkpoint.
  - It lists matching records it didn't create (e.g. from the live demo run) and only deletes them with `--yes`. Ask before passing `--yes`.
  - Slack and Chatter posts have to be deleted by hand.

### 5. Remove
Run `python close_loop.py remove --slug {slug}`. It deactivates the Flows and runs a destructive deploy, but only for names listed in `cp.close_loop.deployed`. Never delete Flows that aren't in that list without asking.

### 6. Studio follow-up
If `demos/{slug}/studio_skills/` exists, tell the user to re-run `/studio {slug}` so `aio-audience` picks up the Close the Loop section.

## Slack configuration
Slack is optional, and `/setup` doesn't ask about it. It's set up in **Step 2b** at build time. These are the commands behind that step:
```bash
python close_loop.py slack-check --slug {slug} [--profile K]          # read-only: ready + issues + fixes (JSON)
python setup_slack.py --channel-id C… --workspace-id T… [--app-id A…]  # save IDs (no prompts; Claude runs this)
python setup_slack.py --show                                         # print saved IDs + check
python setup_slack.py                                                # interactive prompts (for a user at a terminal)
```
Result in `config.json` → `profiles.{key}.slack`:
```json
{"workspace_id": "T0123…", "channel_id": "C0123…", "channel_name": "demo-alerts", "app_id": ""}
```
- **Workspace ID is the Slack team ID, starting with `T`.** It is *not* the subdomain in `https://my-workspace.slack.com`. Find it at Workspace menu → Settings → About, or as the `T…` segment in `app.slack.com/client/T…/…`.
- **Channel ID** starts with `C`: channel → View channel details → bottom of the About tab.
- The org must be connected to Slack (Setup → Slack), and the running user must have connected their Slack account.
- Without that, the Flows post to Chatter instead and the demo still lands.
- The Slack inputs are resolved at build time, so re-run `build` after connecting Slack.
- Check readiness at any time with `slack-check` (above). `preflight` prints the raw org report, if needed. Don't write inline Python to call `preflight()`; it returns a dict and needs the profile's `slack` config.

## Troubleshooting
Follow the CLAUDE.md troubleshooting order. Close-loop pitfalls are in CLAUDE.md Known Pitfalls, prefixed "Close the loop:".
- **Deploy failures:** listed per component. Fix the generator in `close_loop_flows.py`, not the deployed XML.
- **Flow ran but no records appeared:** check Setup → Flows → Paused and Failed Flow Interviews.
- **Any genuinely new error:** add it to CLAUDE.md Known Pitfalls with the "Close the loop:" prefix.
