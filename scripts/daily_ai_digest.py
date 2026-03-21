from __future__ import annotations

import re


AI_KEYWORDS = {
    "openai": 6,
    "anthropic": 6,
    "deepmind": 5,
    "google ai": 5,
    "mistral": 5,
    "perplexity": 5,
    "xai": 5,
    "ai": 2,
    "model": 2,
    "agent": 3,
    "tool": 2,
    "launch": 2,
    "release": 2,
    "coding": 2,
}


def normalize_title(title: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    return re.sub(r"\s+", " ", compact)


def dedupe_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for item in items:
        normalized = normalize_title(item["title"])
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(item)
    return unique


def score_item(item: dict[str, str]) -> int:
    haystack = f"{item.get('title', '')} {item.get('source', '')}".lower()
    score = 0
    for keyword, weight in AI_KEYWORDS.items():
        if keyword in haystack:
            score += weight
    return score


def rank_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    unique_items = dedupe_items(items)
    return sorted(unique_items, key=score_item, reverse=True)


def render_section(date_text: str, items: list[dict[str, str]]) -> str:
    lines = [f"## {date_text}", ""]
    for item in items:
        lines.append(f"- [{item['title']}]({item['link']})")
        lines.append(f"  Source: {item['source']}")
        lines.append(f"  Implication: {item['implication']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def upsert_section(content: str, date_text: str, section: str) -> str:
    section_header = f"## {date_text}\n"
    if section_header not in content:
        if content.endswith("\n"):
            return content + "\n" + section
        return content + "\n\n" + section

    start = content.index(section_header)
    next_start = content.find("\n## ", start + len(section_header))
    if next_start == -1:
        return content[:start].rstrip() + "\n\n" + section
    return content[:start].rstrip() + "\n\n" + section.rstrip() + "\n" + content[next_start:]
