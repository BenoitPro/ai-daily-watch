from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG_FILE = REPO_ROOT / "AI_NEWS_LOG.md"
LAUNCHD_FILE = REPO_ROOT / "launchd" / "com.benoitpro.ai-daily-watch.plist"
DEFAULT_LIMIT = 7
DEFAULT_HOUR = 9
DEFAULT_MINUTE = 15
USER_AGENT = "ai-daily-watch/1.0"

GOOGLE_NEWS_QUERIES = [
    '"artificial intelligence" OR "AI agent" OR LLM',
    "OpenAI OR Anthropic OR DeepMind OR Mistral OR Perplexity OR xAI",
]

HN_QUERIES = [
    "OpenAI agent",
    "Anthropic model",
]

AI_KEYWORDS = {
    "openai": 7,
    "anthropic": 7,
    "deepmind": 6,
    "google ai": 5,
    "mistral": 6,
    "perplexity": 5,
    "xai": 5,
    "artificial intelligence": 4,
    "ai": 2,
    "llm": 4,
    "model": 2,
    "agent": 3,
    "tool": 2,
    "launch": 2,
    "release": 2,
    "coding": 2,
}

IMPLICATION_RULES = [
    (("agent", "assistant", "automation"), "AI agents are becoming more practical for day-to-day workflows."),
    (("coding", "developer", "code"), "Developer tooling keeps getting more automated and competitive."),
    (("model", "llm", "reasoning"), "Model quality and capability shifts are worth watching for product planning."),
    (("open source", "weights"), "Open models continue lowering adoption costs and increasing optionality."),
    (("chip", "gpu", "compute", "nvidia"), "Compute access remains a strategic constraint in the AI stack."),
    (("policy", "regulation", "law", "eu"), "Regulatory pressure is rising and could change shipping constraints."),
]


def normalize_title(title: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    return re.sub(r"\s+", " ", compact)


def dedupe_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for item in items:
        title = item.get("title", "").strip()
        link = item.get("link", "").strip()
        if not title or not link:
            continue
        normalized = normalize_title(title)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(item)
    return unique


def parse_datetime(value: str) -> dt.datetime | None:
    if not value:
        return None
    candidates = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    for pattern in candidates:
        try:
            parsed = dt.datetime.strptime(value, pattern)
            return parsed.replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    return None


def score_item(item: dict[str, str]) -> int:
    haystack = f"{item.get('title', '')} {item.get('source', '')}".lower()
    score = 0
    for keyword, weight in AI_KEYWORDS.items():
        if keyword in haystack:
            score += weight

    published = parse_datetime(item.get("published", ""))
    if published is not None:
        age_days = max(0, (dt.datetime.now(dt.timezone.utc) - published).days)
        if age_days <= 1:
            score += 4
        elif age_days <= 3:
            score += 2
    return score


def rank_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    unique_items = dedupe_items(items)
    return sorted(unique_items, key=score_item, reverse=True)


def infer_implication(title: str) -> str:
    lowered = title.lower()
    for keywords, message in IMPLICATION_RULES:
        if any(keyword in lowered for keyword in keywords):
            return message
    return "Worth tracking for tooling, product strategy, and workflow changes."


def build_digest_items(raw_items: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    ranked = rank_items(raw_items)
    selected: list[dict[str, str]] = []
    for item in ranked[: max(1, limit)]:
        selected.append(
            {
                "title": item["title"],
                "source": item.get("source", "Unknown source"),
                "link": item["link"],
                "implication": item.get("implication") or infer_implication(item["title"]),
            }
        )
    if selected:
        return selected
    return [
        {
            "title": "Low signal day for AI news",
            "source": "Internal fallback",
            "link": "https://github.com",
            "implication": "No strong signal surfaced today, but the daily log still captures continuity.",
        }
    ]


def render_section(date_text: str, items: list[dict[str, str]]) -> str:
    lines = [f"## {date_text}", ""]
    for item in items:
        lines.append(f"- [{item['title']}]({item['link']})")
        lines.append(f"  Source: {item['source']}")
        lines.append(f"  Implication: {item['implication']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def initial_log_content() -> str:
    return "# AI News Log\n\nDaily AI watch entries are appended here.\n"


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


def update_log_file(log_path: pathlib.Path, date_text: str, items: list[dict[str, str]]) -> pathlib.Path:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    content = log_path.read_text() if log_path.exists() else initial_log_content()
    if not content.strip():
        content = initial_log_content()
    if not content.startswith("# AI News Log"):
        content = initial_log_content().rstrip() + "\n\n" + content.lstrip()
    updated = upsert_section(content, date_text, render_section(date_text, items))
    log_path.write_text(updated)
    return log_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and commit a daily AI news digest.")
    parser.add_argument("--dry-run", action="store_true", help="Print the rendered section without writing or pushing.")
    parser.add_argument("--date", help="Override the target date in YYYY-MM-DD format.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Number of news items to keep.")
    return parser.parse_args(argv)


def resolve_date(date_override: str | None) -> str:
    if date_override:
        return dt.date.fromisoformat(date_override).isoformat()
    return dt.date.today().isoformat()


def build_commit_message(date_text: str) -> str:
    return f"chore: daily AI watch {date_text}"


def git_binary() -> str:
    return shutil.which("git") or "/usr/bin/git"


def run_git(args: list[str], cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [git_binary(), *args],
        cwd=str(cwd or REPO_ROOT),
        check=False,
        capture_output=True,
        text=True,
    )


def split_title_and_source(raw_title: str) -> tuple[str, str]:
    if " - " not in raw_title:
        return html.unescape(raw_title), ""
    title, source = raw_title.rsplit(" - ", 1)
    return html.unescape(title.strip()), html.unescape(source.strip())


def parse_google_news_feed(xml_text: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, str]] = []
    for item in root.findall("./channel/item"):
        raw_title = (item.findtext("title") or "").strip()
        title, source = split_title_and_source(raw_title)
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        items.append(
            {
                "title": title,
                "source": source or "Google News",
                "link": link,
                "published": (item.findtext("pubDate") or "").strip(),
            }
        )
    return items


def parse_hn_response(json_text: str) -> list[dict[str, str]]:
    payload = json.loads(json_text)
    items: list[dict[str, str]] = []
    for hit in payload.get("hits", []):
        title = (hit.get("title") or hit.get("story_title") or "").strip()
        if not title:
            continue
        link = (hit.get("url") or hit.get("story_url") or "").strip()
        if not link and hit.get("objectID"):
            link = f"https://news.ycombinator.com/item?id={hit['objectID']}"
        if not link:
            continue
        items.append(
            {
                "title": title,
                "source": "Hacker News",
                "link": link,
                "published": (hit.get("created_at") or "").strip(),
            }
        )
    return items


def build_google_news_url(query: str) -> str:
    encoded = urllib.parse.urlencode(
        {
            "q": query,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }
    )
    return f"https://news.google.com/rss/search?{encoded}"


def build_hn_url(query: str) -> str:
    encoded = urllib.parse.urlencode({"query": query, "tags": "story"})
    return f"https://hn.algolia.com/api/v1/search_by_date?{encoded}"


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_candidate_items() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []

    for query in GOOGLE_NEWS_QUERIES:
        try:
            items.extend(parse_google_news_feed(fetch_text(build_google_news_url(query))))
        except Exception as exc:
            print(f"Google News fetch failed for query {query!r}: {exc}", file=sys.stderr)

    for query in HN_QUERIES:
        try:
            items.extend(parse_hn_response(fetch_text(build_hn_url(query))))
        except Exception as exc:
            print(f"Hacker News fetch failed for query {query!r}: {exc}", file=sys.stderr)

    return items


def ensure_origin_remote() -> None:
    remote = run_git(["remote", "get-url", "origin"])
    if remote.returncode != 0:
        raise RuntimeError("Git remote 'origin' is missing. Configure the GitHub repository before running the live mode.")


def commit_and_push(log_path: pathlib.Path, date_text: str) -> bool:
    relative_log = str(log_path.relative_to(REPO_ROOT))
    add_result = run_git(["add", relative_log, str(LAUNCHD_FILE.relative_to(REPO_ROOT))])
    if add_result.returncode != 0:
        raise RuntimeError(add_result.stderr.strip() or "git add failed")

    diff_result = run_git(["diff", "--cached", "--quiet"])
    if diff_result.returncode == 0:
        push_result = run_git(["push", "origin", "main"])
        if push_result.returncode != 0:
            raise RuntimeError(push_result.stderr.strip() or "git push failed")
        return False
    if diff_result.returncode not in {0, 1}:
        raise RuntimeError(diff_result.stderr.strip() or "git diff --cached failed")

    commit_result = run_git(["commit", "-m", build_commit_message(date_text)])
    if commit_result.returncode != 0:
        raise RuntimeError(commit_result.stderr.strip() or "git commit failed")

    push_result = run_git(["push", "origin", "main"])
    if push_result.returncode != 0:
        raise RuntimeError(push_result.stderr.strip() or "git push failed")
    return True


def build_launch_agent_plist(
    python_path: str,
    script_path: str,
    repo_root: str,
    hour: int,
    minute: int,
) -> str:
    repo = pathlib.Path(repo_root)
    stdout_log = repo / "logs" / "ai-daily-watch.out.log"
    stderr_log = repo / "logs" / "ai-daily-watch.err.log"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.benoitpro.ai-daily-watch</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python_path}</string>
    <string>{script_path}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>{repo_root}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StandardOutPath</key>
  <string>{stdout_log}</string>
  <key>StandardErrorPath</key>
  <string>{stderr_log}</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>{hour}</integer>
    <key>Minute</key>
    <integer>{minute}</integer>
  </dict>
</dict>
</plist>
"""


def write_launch_agent_file() -> pathlib.Path:
    (REPO_ROOT / "logs").mkdir(parents=True, exist_ok=True)
    LAUNCHD_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAUNCHD_FILE.write_text(
        build_launch_agent_plist(
            python_path=sys.executable,
            script_path=str(REPO_ROOT / "scripts" / "daily_ai_digest.py"),
            repo_root=str(REPO_ROOT),
            hour=DEFAULT_HOUR,
            minute=DEFAULT_MINUTE,
        )
    )
    return LAUNCHD_FILE


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    date_text = resolve_date(args.date)
    raw_items = fetch_candidate_items()
    digest_items = build_digest_items(raw_items, args.limit)

    if args.dry_run:
        print(render_section(date_text, digest_items))
        return 0

    update_log_file(LOG_FILE, date_text, digest_items)
    ensure_origin_remote()
    changed = commit_and_push(LOG_FILE, date_text)
    if changed:
        print(f"Committed and pushed {date_text}.")
    else:
        print(f"No changes to commit for {date_text}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
