"""
Google Docs output writer for AIO Analytics Builder.
Creates a Google Doc with the same structure as the .docx walkthrough.
Called from demo scripts when the user selects Google Doc output format.

Usage:
    from google_docs import create_walkthrough_doc
    url = create_walkthrough_doc(
        title="BI Worldwide Sales Incentive — Demo Walkthrough",
        sections=[
            {"heading": "Demo Scenario",    "body": "..."},
            {"heading": "Concierge Prompts", "steps": [
                {"title": "Opening", "question": "...", "answer": "..."},
                ...
            ]},
            {"heading": "Metrics Reference", "metrics": [
                {"label": "...", "description": "...", "why_it_matters": "..."},
                ...
            ]},
            {"heading": "Business Preferences", "body": "..."},
        ],
        google_config={"client_id": ..., "client_secret": ..., "refresh_token": ...},
    )
    print(f"Google Doc created: {url}")
"""

import requests


def _refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    r = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _docs_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}


def _drive_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}


def create_walkthrough_doc(
    title: str,
    sections: list,
    google_config: dict,
) -> str:
    """
    Create a Google Doc with the walkthrough content.

    sections is a list of dicts; each dict has a "heading" key plus one of:
      - "body": str  — plain paragraph block
      - "steps": list of {"title", "question", "answer"}  — Concierge Q&A
      - "metrics": list of {"label", "description", "why_it_matters"}  — metrics ref

    Returns the URL of the created Google Doc.
    """
    access_token = _refresh_access_token(
        google_config["client_id"],
        google_config["client_secret"],
        google_config["refresh_token"],
    )
    h = _docs_headers(access_token)

    # Create empty doc
    r = requests.post(
        "https://docs.googleapis.com/v1/documents",
        headers=h,
        json={"title": title},
    )
    r.raise_for_status()
    doc_id = r.json()["documentId"]
    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

    # Build the full text as a sequence of batchUpdate requests
    requests_list = _build_requests(title, sections)
    if requests_list:
        rb = requests.post(
            f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
            headers=h,
            json={"requests": requests_list},
        )
        rb.raise_for_status()

    return doc_url


def _build_requests(title: str, sections: list) -> list:
    """
    Build a flat list of Docs API batchUpdate requests that insert all content.
    We insert in reverse order (end of doc first) to keep indices stable,
    OR we build the full text and insert once — simpler and more reliable.

    This implementation builds paragraphs as a sequence of insertText requests
    with named styles applied via updateParagraphStyle.
    """
    reqs = []
    # We use a single large insertText at the end approach:
    # collect (text, style) tuples, then insert them in one block and apply styles.
    # Simpler: just insert lines in one go with a plain-text batchUpdate.
    # For heading styles we need separate updateParagraphStyle calls.

    lines = []  # list of (text, paragraph_style)  where style is "HEADING_1" / "HEADING_2" / "NORMAL_TEXT"
    for section in sections:
        heading = section.get("heading", "")
        if heading:
            lines.append((heading, "HEADING_1"))

        if "subsections" in section:
            for sub in section["subsections"]:
                if sub.get("subheading"):
                    lines.append((sub["subheading"], "HEADING_2"))
                if sub.get("body"):
                    lines.append((sub["body"], "NORMAL_TEXT"))

        elif "body" in section:
            lines.append((section["body"], "NORMAL_TEXT"))

        elif "steps" in section:
            lines.append((
                "Each step below shows the question to ask followed by the expected Concierge response, "
                "captured live from the data at build time.",
                "NORMAL_TEXT",
            ))
            for step in section["steps"]:
                lines.append((step["title"], "HEADING_2"))
                q_line = f'Ask: "{step["question"]}"'
                lines.append((q_line, "NORMAL_TEXT"))
                answer = step.get("answer", "")
                if answer:
                    import re
                    clean = re.sub(r"<[^>]+>", "", answer).strip()
                    lines.append((f"Expected response: {clean}", "NORMAL_TEXT"))

        elif "metrics" in section:
            lines.append((
                "Each metric below includes its definition and why it matters to the client. "
                "Use these to frame the story during the demo.",
                "NORMAL_TEXT",
            ))
            for m in section["metrics"]:
                lines.append((m["label"], "HEADING_2"))
                lines.append((f'What it measures: {m["description"]}', "NORMAL_TEXT"))
                lines.append((f'Why it matters: {m["why_it_matters"]}', "NORMAL_TEXT"))

    if not lines:
        return []

    # Build a single insertText at index 1 (after the doc title), then apply styles.
    # We work from the bottom up so indices stay valid.
    # Step 1: Insert all lines (bottom to top).

    # First compute cumulative character positions (top-down) so we can apply styles.
    # Insert order: reverse the list and insert each at index 1.
    # After all insertions, line[0] starts at 1, line[1] at 1+len(line[0])+1, etc.

    # Simpler: insert from bottom to top (reversed), each at index 1.
    # This means the last line ends up at the top — so we need to reverse our list
    # so that after all insertions, the order is correct.

    # We insert each line as: text + "\n" at index 1.
    # After inserting line N at index 1, line N sits at position 1..len(line_N)+1.
    # Then inserting line N-1 at index 1 pushes everything down.
    # So to get [line0, line1, line2, ...] we insert in reverse order: line2, line1, line0.

    reversed_lines = list(reversed(lines))
    for text, _ in reversed_lines:
        reqs.append({
            "insertText": {
                "location": {"index": 1},
                "text": text + "\n",
            }
        })

    # Step 2: Apply paragraph styles by computing start indices from the top.
    index = 1
    for text, style in lines:
        end_index = index + len(text) + 1  # +1 for the \n
        if style in ("HEADING_1", "HEADING_2"):
            reqs.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": end_index},
                    "paragraphStyle": {"namedStyleType": style},
                    "fields": "namedStyleType",
                }
            })
        index = end_index

    return reqs
