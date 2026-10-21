"""Company research module for the web UI.

Performs the same 5-area research the CLI /build-demo does:
1. Company overview (industry, products, regions)
2. Industry benchmarks (realistic metric ranges)
3. Use-case context (real category names, markets)
4. Goals/thresholds (regulatory targets, SLAs)
5. Brand colors (hex codes from brand guidelines)

Uses DuckDuckGo HTML search (no API key needed) to gather context,
then structures it for the story generation prompt.
"""

import re
import time
import requests
from typing import Dict, List, Optional
from urllib.parse import quote_plus


def _ddg_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Search DuckDuckGo and return results as [{title, snippet, url}]."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
            time.sleep(1)
        return [
            {"title": r.get("title", ""), "snippet": r.get("body", ""), "url": r.get("href", "")}
            for r in raw if r.get("title") and r.get("body")
        ]
    except ImportError:
        pass

    # Fallback: DuckDuckGo HTML scraping
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        r = requests.get(
            f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        html = r.text
        results = []
        blocks = re.findall(
            r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'class="result__snippet"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )
        for url, title, snippet in blocks[:max_results]:
            title = re.sub(r'<[^>]+>', '', title).strip()
            snippet = re.sub(r'<[^>]+>', '', snippet).strip()
            if title and snippet:
                results.append({"title": title, "snippet": snippet, "url": url})
        return results
    except Exception:
        return []


def _extract_hex_colors(text: str) -> List[str]:
    """Extract hex color codes from text."""
    return list(set(re.findall(r'#[0-9A-Fa-f]{6}\b', text)))


def research_company(
    company: str,
    industry: str = "",
    use_case: str = "",
    depth: str = "quick",
    progress_fn=None,
) -> Dict[str, str]:
    """Research a company and return structured context for story generation.

    Args:
        company: Company name
        industry: Industry (optional, helps focus searches)
        use_case: Use case / topic
        depth: "quick" (2-3 searches) or "detailed" (5-7 searches)
        progress_fn: Optional callback(message) for progress updates

    Returns:
        Dict with keys: company_context, benchmarks, use_case_context,
        goals_thresholds, brand_colors, raw_results
    """
    def _progress(msg):
        if progress_fn:
            progress_fn(msg)

    results = {
        "company_context": "",
        "benchmarks": "",
        "use_case_context": "",
        "goals_thresholds": "",
        "brand_colors": {},
        "raw_results": [],
    }

    industry_hint = f" {industry}" if industry else ""
    use_case_hint = f" {use_case}" if use_case else ""

    def _search_with_retry(query, label):
        _progress(label)
        for attempt in range(2):
            hits = _ddg_search(query, max_results=4)
            if hits:
                return hits
            time.sleep(2)
        return []

    # --- Search 1: Company overview ---
    company_results = _search_with_retry(
        f"{company}{industry_hint} company overview products services",
        f"Researching {company}...",
    )
    if company_results:
        results["company_context"] = "\n".join([f"- {r['title']}: {r['snippet']}" for r in company_results])
        results["raw_results"].extend(company_results)

    # --- Search 2: Industry benchmarks ---
    bench_query = f"{industry or company} {use_case or 'business'} industry benchmarks KPIs metrics typical ranges"
    bench_results = _search_with_retry(bench_query, "Finding industry benchmarks...")
    if bench_results:
        results["benchmarks"] = "\n".join([f"- {r['title']}: {r['snippet']}" for r in bench_results])
        results["raw_results"].extend(bench_results)

    if depth == "detailed":
        # --- Search 3: Use-case specific context ---
        if use_case:
            uc_results = _search_with_retry(
                f"{company}{industry_hint} {use_case} operations segments regions customers",
                f"Researching {use_case} context...",
            )
            if uc_results:
                results["use_case_context"] = "\n".join([f"- {r['title']}: {r['snippet']}" for r in uc_results])
                results["raw_results"].extend(uc_results)

        # --- Search 4: Goals and thresholds ---
        goals_results = _search_with_retry(
            f"{industry or company}{use_case_hint} targets SLA compliance threshold benchmark goals",
            "Finding goals and thresholds...",
        )
        if goals_results:
            results["goals_thresholds"] = "\n".join([f"- {r['title']}: {r['snippet']}" for r in goals_results])
            results["raw_results"].extend(goals_results)

        # --- Search 5: Brand colors ---
        brand_results = _search_with_retry(
            f"{company} brand guidelines color palette hex primary",
            "Looking up brand colors...",
        )
        if brand_results:
            all_text = " ".join([r["snippet"] for r in brand_results])
            hex_colors = _extract_hex_colors(all_text)
            if hex_colors:
                results["brand_colors"] = {
                    "primary": hex_colors[0],
                    "secondary": hex_colors[1] if len(hex_colors) > 1 else "",
                }
            results["raw_results"].extend(brand_results)

    _progress("Research complete")
    return results


def format_research_for_prompt(research: Dict) -> str:
    """Format research results into a context block for the story prompt."""
    sections = []

    if research.get("company_context"):
        sections.append(f"""COMPANY RESEARCH:
{research['company_context']}""")

    if research.get("benchmarks"):
        sections.append(f"""INDUSTRY BENCHMARKS:
{research['benchmarks']}""")

    if research.get("use_case_context"):
        sections.append(f"""USE CASE CONTEXT:
{research['use_case_context']}""")

    if research.get("goals_thresholds"):
        sections.append(f"""GOALS & THRESHOLDS:
{research['goals_thresholds']}""")

    if research.get("brand_colors"):
        bc = research["brand_colors"]
        sections.append(f"""BRAND COLORS FOUND:
Primary: {bc.get('primary', 'not found')}
Secondary: {bc.get('secondary', 'not found')}""")

    if not sections:
        return ""

    return """
RESEARCH RESULTS (use these to ground the demo in reality — real dimension values, realistic metric ranges, actual business context):
""" + "\n\n".join(sections)
