# Verification and Recovery

A success response from a tool only tells you the call ran. It does not tell you the chart is correct. After building each sheet, read its current state back and check it against the spec.

## Per-sheet checks

| Check | How |
|-------|-----|
| Correct fields placed | Read the worksheet back. Confirm the rows/columns/marks fields match the spec, and that each field has the intended aggregation |
| Correct mark type | Line, Bar, or Square, as the spec says |
| Not blank | Query or inspect the sheet's data and confirm there are rows. For Q4, confirm 20 or fewer rows |
| Filters applied | Q2: recent 3 months. Q3: culprit only. Q4: culprit + recent 3 months + Top 20 |
| Colors (Q2) | Culprit = red, counter-trend = orange, others = gray |
| Sort direction | The worst segment or entity appears first |
| Title | Matches the spec, with real values substituted (no `{braces}` left) |

## Recovery

1. **Field not found.** Re-list the datasource fields, fix the mapping, and rebuild that sheet.
2. **Sheet is blank.**
   - Check the filters. The usual cause is a culprit value that doesn't match exactly, or a date filter outside the data range.
   - Loosen the date filter to the most recent 3 months *of the data*, not of today.
3. **A formatting step fails** (color, label, number format). Leave the sheet structurally correct and note the gap in the final report. Do not block the build on formatting.
4. **A sheet fails twice.** Skip it, keep building the rest, and report what failed.
5. **An error dialog appears in Studio.** Stop, ask the user to copy the message into chat, and then fix based on that message.

Retry each sheet at most once. A fully built dashboard with one formatting gap is a better result than a stalled build.
