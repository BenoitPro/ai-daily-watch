from __future__ import annotations

import argparse
import datetime as dt
import email.policy
from email.message import EmailMessage
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
SUMMARY_EMAIL_TO = "benoit.baillon@edhec.com"
DEFAULT_LIMIT = 7
DEFAULT_HOUR = 9
DEFAULT_MINUTE = 0
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


def build_email_subject(date_text: str) -> str:
    return f"Veille IA - {date_text}"


def format_french_date(date_text: str) -> str:
    parsed = dt.date.fromisoformat(date_text)
    months = [
        "janvier",
        "fevrier",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "aout",
        "septembre",
        "octobre",
        "novembre",
        "decembre",
    ]
    return f"{parsed.day} {months[parsed.month - 1]} {parsed.year}"


def build_signal_summary(items: list[dict[str, str]]) -> list[str]:
    top_titles = [item["title"] for item in items[:3]]
    if not top_titles:
        return ["Journee calme, peu de signaux vraiment saillants."]
    return top_titles


def build_topic_radar(items: list[dict[str, str]]) -> str:
    keyword_groups = {
        "Agents": ("agent", "assistant", "automation"),
        "Coding": ("coding", "developer", "code", "python"),
        "Modeles": ("model", "llm", "reasoning"),
        "OpenAI": ("openai",),
        "Anthropic": ("anthropic",),
        "Infrastructure": ("gpu", "chip", "compute", "nvidia"),
    }
    hits: list[str] = []
    haystacks = [f"{item['title']} {item['implication']}".lower() for item in items]
    for label, keywords in keyword_groups.items():
        if any(any(keyword in haystack for keyword in keywords) for haystack in haystacks):
            hits.append(label)
    if not hits:
        return "Signal generaliste"
    return " | ".join(hits[:4])


def build_email_body(date_text: str, items: list[dict[str, str]]) -> str:
    friendly_date = format_french_date(date_text)
    summary_lines = build_signal_summary(items)
    lines = [
        "ALAIN // VEILLE IA",
        friendly_date,
        "",
        "Une note courte, utile, et orientee action.",
        "",
        "Signal du jour",
        "-------------",
    ]
    for summary in summary_lines:
        lines.append(f"- {summary}")
    lines.extend(
        [
            "",
            "Radar du jour",
            "-------------",
            build_topic_radar(items),
            "",
            "A retenir",
            "---------",
        ]
    )
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item['title']}")
        lines.append(f"Source: {item['source']}")
        lines.append(f"Pourquoi c'est important: {item['implication']}")
        lines.append(f"Lien: {item['link']}")
        lines.append("")
    lines.append("Archive GitHub")
    lines.append("--------------")
    lines.append("https://github.com/BenoitPro/ai-daily-watch")
    return "\n".join(lines).strip() + "\n"


def applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_email_html(date_text: str, items: list[dict[str, str]]) -> str:
    friendly_date = html.escape(format_french_date(date_text))
    summaries = "".join(
        f"""
        <tr>
          <td style="padding:0 0 10px 0;font-size:16px;line-height:24px;color:#212c4c;">{html.escape(summary)}</td>
        </tr>
        """
        for summary in build_signal_summary(items)
    )
    if not summaries:
        summaries = """
        <tr>
          <td style="padding:0 0 10px 0;font-size:16px;line-height:24px;color:#212c4c;">Journee calme, peu de signaux vraiment saillants.</td>
        </tr>
        """

    cards = []
    for index, item in enumerate(items, start=1):
        cards.append(
            f"""
            <tr>
              <td style="padding:0 0 18px 0;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #dbe6fb;border-radius:18px;background:#ffffff;">
                  <tr>
                    <td style="padding:20px 22px 8px 22px;">
                      <div style="font-size:12px;line-height:18px;letter-spacing:1.4px;text-transform:uppercase;color:#2d6cdf;font-weight:700;">Actu {index}</div>
                      <div style="padding-top:8px;font-size:24px;line-height:31px;font-weight:700;color:#212c4c;">{html.escape(item['title'])}</div>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:0 22px 10px 22px;font-size:14px;line-height:21px;color:#5e6b8a;">Source: {html.escape(item['source'])}</td>
                  </tr>
                  <tr>
                    <td style="padding:0 22px 18px 22px;font-size:16px;line-height:25px;color:#33405f;">{html.escape(item['implication'])}</td>
                  </tr>
                  <tr>
                    <td style="padding:0 22px 22px 22px;">
                      <a href="{html.escape(item['link'], quote=True)}" style="display:inline-block;padding:12px 18px;border-radius:999px;background:#212c4c;color:#ffffff;font-size:14px;line-height:14px;font-weight:700;text-decoration:none;">Lire la source</a>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            """
        )

    radar = html.escape(build_topic_radar(items))
    cards_markup = "".join(cards)
    return f"""<!doctype html>
<html lang="fr">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Veille IA - {friendly_date}</title>
  </head>
  <body style="margin:0;padding:0;background:#f4f8ff;color:#212c4c;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">Veille IA quotidienne ALAIN: les signaux utiles du jour.</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f4f8ff;">
      <tr>
        <td align="center" style="padding:28px 16px 40px 16px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:680px;background:#ffffff;border-radius:28px;overflow:hidden;">
            <tr>
              <td style="padding:0;background:linear-gradient(135deg,#ffffff 0%,#eef4ff 58%,#dceaff 100%);border-bottom:4px solid #2d6cdf;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td style="padding:30px 30px 28px 30px;">
                      <div style="font-size:12px;line-height:18px;letter-spacing:2px;text-transform:uppercase;color:#2d6cdf;font-weight:700;">ALAIN // VEILLE IA</div>
                      <div style="padding-top:10px;font-size:34px;line-height:39px;font-weight:700;color:#212c4c;">Les actus IA utiles du jour</div>
                      <div style="padding-top:10px;font-size:16px;line-height:24px;color:#4f5f86;">{friendly_date} · note courte, claire, orientee impact.</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:28px 30px 8px 30px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #dbe6fb;border-radius:20px;background:#f7faff;">
                  <tr>
                    <td style="padding:22px 24px;">
                      <div style="font-size:13px;line-height:18px;letter-spacing:1.4px;text-transform:uppercase;color:#2d6cdf;font-weight:700;">Signal du jour</div>
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="padding-top:12px;">
                        {summaries}
                      </table>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:14px 30px 8px 30px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td width="50%" style="padding:0 8px 0 0;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #e3ebfa;border-radius:18px;background:#ffffff;">
                        <tr>
                          <td style="padding:18px 20px;">
                            <div style="font-size:12px;line-height:18px;letter-spacing:1.4px;text-transform:uppercase;color:#7a8cb4;font-weight:700;">Radar</div>
                            <div style="padding-top:8px;font-size:17px;line-height:24px;color:#212c4c;font-weight:700;">{radar}</div>
                          </td>
                        </tr>
                      </table>
                    </td>
                    <td width="50%" style="padding:0 0 0 8px;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #e3ebfa;border-radius:18px;background:#ffffff;">
                        <tr>
                          <td style="padding:18px 20px;">
                            <div style="font-size:12px;line-height:18px;letter-spacing:1.4px;text-transform:uppercase;color:#7a8cb4;font-weight:700;">Archive</div>
                            <div style="padding-top:8px;font-size:16px;line-height:24px;color:#33405f;">Le detail journalier reste trace dans GitHub.</div>
                            <div style="padding-top:10px;"><a href="https://github.com/BenoitPro/ai-daily-watch" style="color:#2d6cdf;font-size:14px;line-height:20px;font-weight:700;text-decoration:none;">Ouvrir l'archive</a></div>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 30px 20px 30px;">
                <div style="font-size:13px;line-height:18px;letter-spacing:1.4px;text-transform:uppercase;color:#2d6cdf;font-weight:700;padding-bottom:14px;">A retenir</div>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                  {cards_markup}
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:0 30px 30px 30px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-top:1px solid #e8eefb;">
                  <tr>
                    <td style="padding-top:18px;font-size:13px;line-height:20px;color:#6c7b9b;">
                      Envoi automatique quotidien depuis le poste local. Format editorial ALAIN, sobre, blanc, bleu, lisible sur mobile et desktop.
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def build_raw_email_source(recipient: str, subject: str, text_body: str, html_body: str) -> str:
    message = EmailMessage()
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(text_body, subtype="plain", charset="utf-8")
    message.add_alternative(html_body, subtype="html", charset="utf-8")
    return message.as_string(policy=email.policy.SMTP)


def build_outlook_applescript(raw_source: str) -> str:
    return f'''
tell application "Microsoft Outlook"
    set msg to make new outgoing message with properties {{source:"{applescript_string(raw_source)}"}}
    send msg
end tell
'''


def send_summary_email(date_text: str, items: list[dict[str, str]], recipient: str = SUMMARY_EMAIL_TO) -> None:
    subject = build_email_subject(date_text)
    text_body = build_email_body(date_text, items)
    html_body = build_email_html(date_text, items)
    raw_source = build_raw_email_source(
        recipient=recipient,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )
    script = build_outlook_applescript(raw_source=raw_source)
    result = subprocess.run(
        ["/usr/bin/osascript"],
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Mail send failed")


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
    send_summary_email(date_text, digest_items)
    if changed:
        print(f"Committed, pushed, and emailed {date_text}.")
    else:
        print(f"No changes to commit for {date_text}, but push and email succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
