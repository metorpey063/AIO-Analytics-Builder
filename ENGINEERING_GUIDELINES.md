# AIO Engineering Guidelines

**Core principle: deterministic modules over variable code generation.**

Every build should produce the same quality output regardless of which session generates it. Achieve this by using shared modules with built-in validation, not by writing fresh code each time and hoping the instructions are followed.

## 1. Use the module, not inline code

| Task | Use this module | NOT this |
|------|----------------|----------|
| Data generation | `data_generator.generate_demo_data()` | Inline `generate_data()` function in the demo script |
| Dimension validation | `data_validator.validate_dimension_values()` | Manual checks or hoping the script includes them |
| Viz creation | `viz_builder.build_viz_payload()` or `template_deployer.deploy_template()` | Hand-building VizQL JSON payloads from scratch |
| Dashboard assembly | `dashboard_builder.build_dashboard_payload()` or `template_deployer` | Raw REST dashboard payloads |
| CRM record upsert | `crm_upserter.upsert_crm_records()` | Inline Composite API calls |
| Pulse datasource | `tdsx_builder.publish_hyper_for_indexing()` + `convert_to_self_healing()` | Manual .hyper/.tdsx construction |
| TWB workbook | `twb_builder.build_twb()` + `publish_twb()` | Hand-written Tableau XML |
| Close-the-loop | `close_loop.py` CLI commands | Inline Flow XML or Metadata API calls |
| Field name cleaning | `data_validator` or inline `clean_field_name()` (same regex) | Ad-hoc lowercasing that misses edge cases |

**If a module exists for the task, use it.** If you find yourself writing >10 lines of API plumbing that a module already handles, stop and use the module.

## 2. Config in, output out

Claude's job is **creative** — researching the company, designing the story, choosing metrics and multipliers. The modules handle **execution** — generating rows, building payloads, deploying assets. Keep these separate:

```
Claude provides:              Module handles:
─────────────────             ────────────────
METRIC_CONFIG                 Roster construction
DIMENSION_VALUES              Signal ramp math
multipliers                   Noise scaling
signal_config                 Validation gates
field_map                     Record ID / Day_Offset
label_map                     CSV column naming
                              API payload assembly
```

## 3. Never use generic dimension values

Every dimension must have real, company-specific values researched for the target company. The `data_generator.py` module enforces this — it raises `ValueError` if dimension values match the pattern `{DimName} 1`, `{DimName}_2`, etc.

Examples of what's rejected: `Service_Tier 1`, `Region 2`, `Client_Segment 3`, `Tenure_Band 4`

Examples of what's accepted: `PEO Essentials`, `West Coast`, `Mid-Market (100-499)`, `New (0-1 yr)`

**If dimension values aren't known from research**, ask the user. Never fall back to generic placeholders — they make the demo look fake and defeat AIO's purpose.

## 4. Every metric needs base_range

`METRIC_CONFIG` entries must include `base_range: [min, max]` with realistic starting values for that metric type. Without it, the generator defaults to `[0.55, 0.85]` which is wrong for most metrics:

| Metric type | Realistic base_range |
|------------|---------------------|
| Retention / completion rate | `[0.80, 0.92]` |
| Processing accuracy | `[0.992, 0.999]` |
| Processing days | `[1.5, 3.0]` |
| Resolution hours | `[4.0, 12.0]` |
| Engagement / adoption rate | `[0.25, 0.45]` |
| Churn / error rate | `[0.03, 0.08]` |
| Readmission rate | `[0.10, 0.16]` |
| NPS score | `[35, 55]` |

Research the company's industry benchmarks to set these.

## 5. Template first, fallback second

For Tableau Next dashboards, always try `template_deployer.deploy_template()` first (Z Layout or F Layout). It produces pixel-perfect dashboards with full VizQL specs. Only fall back to `viz_builder` + `dashboard_builder` if the template deployer fails.

For CRMA dashboards, use `crma_dashboard_builder.create_dashboard_from_template()` with Smart Templates.

For Pulse workbooks, use `twb_builder.build_twb()`.

## 6. Check existing before building

Before writing any new code:
1. Check if a module already handles the task
2. Check if another demo script solved the same problem
3. Check CLAUDE.md Known Pitfalls for the API you're about to call
4. Check `discovered_fixes.md` for recent workarounds

## 7. Connection handling

Use the connections module, not hardcoded credentials:
- `load_config(connection_type="salesforce")` for SF/DC builds
- `load_config(connection_type="tableau_cloud")` for Pulse builds
- `load_config(profile_key="specific_key")` only when overriding
- Always pass `profile_key` to `get_sf_token()` for correct token rotation

## 8. Checkpoint everything

Write to the checkpoint after every phase. Include tracking lists (`all_viz_apis`, `all_sdm_apis`, etc.) so retry cleanup only deletes what this build created. Save `cp["story"]` with `dimension_values` so downstream tools (`/close-loop`, `/studio`) have the full context.

## 9. Fail loudly, not silently

- `data_generator` raises `ValueError` on bad dimension values — don't catch it
- `data_validator` returns error lists — check them and stop if non-empty
- API calls: check `r.status_code` and print the error body, don't swallow 400s
- If a phase fails, save the checkpoint (so completed phases aren't re-run) and stop with a clear message

## 10. Viz creation: MCP for vizzes, REST for dashboards

Use the MCP `create_visualization` tool for creating vizzes (slim IR-v2 spec, better quality). Use REST for dashboard assembly — MCP `edit_dashboard` widgets don't render on the canvas. When styling beyond what MCP can set (dual-axis, per-field colors, continuous palettes), use REST PATCH with GET → modify → PATCH.

## 11. Never create IngestAPI DLO relationships

SDM relationships between IngestAPI DLOs and CRM DLOs fail silently — `criteria` always comes back `[]` and queries throw "No join criteria found." Denormalize dimension fields into the fact table instead. Only create relationships within logical views or between CRM-native DLOs.

## 12. Pulse builds must include AI insights

Every Pulse build must call the Pulse Insights API (BAN + Brief) post-build and include the live AI responses in the walkthrough .docx as "Pulse Discover Questions." Never skip this — it's the most impressive part of the demo.

## 13. Walkthrough label rules

Never mix label types in the .docx:
- **"Action:" / "Audience sees:"** → UI navigation sections (Demo Click Path)
- **"Ask:" / "Expected response:"** → AI Q&A sections (Concierge Prompts, Pulse Discover, Studio Skills)
- **"Say:" / "Trigger:" / "Result:"** → Close the Loop section only

## 14. Build it, don't stub it

When asked to "tweak" or "adjust" something, build the full asset first. The user will refine afterward — they don't want a placeholder or instructions for manual steps.

## 15. Asset safety

Only delete assets whose names appear in the checkpoint tracking lists (`all_viz_apis`, `all_sdm_apis`, `all_dash_apis`, `all_ws_apis`). Never delete assets created outside the current build without explicit user confirmation. Protected assets exist on shared orgs.

## 16. Session discipline

- Always write a session summary to memory at the end of a long session
- Use `AskUserQuestion` buttons instead of asking users to type "next" or "continue"
- Be transparent about context limits — say it's due to context, don't be vague
- Ask before pushing to git — never auto-push
- Commit verified fixes immediately — don't let working code sit uncommitted
- Always update CHANGELOG.md with every push
