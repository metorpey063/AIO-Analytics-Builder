# AiO 2.0 — Quick thoughts and upgrade ideas

*Framed against the "So You Think Your Data Can AI?" scoring: Depth 25%, Impact 25%, Build Quality 20%, Innovation 15%, Pitch 15%, plus a bonus for Data 360 + other Salesforce products + AI.*

## What's already working

- **It solves a real problem every SE has.** Tailored, story-driven demos in minutes instead of hours. The judges feel this pain themselves.
- **The story engine is the differentiator.** Culprit segments, compound drill paths, a counter-trend segment and lagging metrics turn a chart into a decision. That's exactly what the brief asks for.
- **It's field-hardened.** Checkpoint and resume, cleanup on retry, canary validation, self-healing dates, and about 60 documented pitfalls.

## Where it could be stronger

- **Breadth more than integration.** Pulse, Next and CRM Analytics are separate outputs from the same CSV. Judges reward products working *together*.
- **No impact numbers yet.** There's no data on SEs using it, demos built, hours saved or deals touched.
- **Visible seams.** Synthetic data, a few manual UI steps, Next charts whose dates age, and trial-org ingest blocks.
- **It stops at the insight.** Nothing triggers an action after the "aha."

## Upgrade ideas for 2.0

1. **One semantic layer, every surface.** Make the Data 360 / Tableau Semantics model the single source for the Next dashboard, Concierge, a Tableau workbook and alerts. That's the integrated story the Depth criterion asks for.
2. **Tableau Studio "puppet mode."** Drive Studio live through the Studio MCP / External Client API to build the workbook on camera.
   - The agent checks its own work: it exports a dashboard image to review the layout, and pulls summary data to confirm the problem segment really is the worst.
   - This replaces the hand-built `.twb` XML.
   - Package the story rules as a Tableau Agent skill so any SE can use it in Studio.
3. **Tableau Next MCP by default.** The file-upload ingest avoids the Bulk Ingest block. It also sets business preferences and dashboard filters programmatically, and `analyze_data` captures Concierge answers. Use the open Beta server so any SE can enroll.
4. **Trustworthy talk tracks.** Generate the metrics talk tracks, then check each AI answer's direction against the real trend and drop any that contradict the data. That's an uncommon, credible trust moment.
5. **Close the loop.** An alert on the problem segment posts to Slack. Tag the datasource "MCP Enabled" with sample questions so Slackbot answers the same questions from the same governed metric.
6. **Start from the opportunity.** Pull account context and call notes from the Salesforce opportunity into the build, and log the finished demo back to it. Track usage in a small Data 360 model as real proof of impact (customer zero).
7. **Focus the pitch.** Leave out CRM Analytics and the maintenance commands. Time-lapse the build and lead with one measured before/after number.

## Watch-outs

- Driving Studio from your own agent is internal beta only, and publishing through it opens a dialog. Keep a recorded fallback.
- Confirm early that Studio can connect to Tableau Semantics on the demo org.
- Use a real SDO/CDO, not a trial org.

**One line:** *From opportunity to a decision-ready demo, on one semantic layer, across every Tableau surface, verified by the agent that built it.*
