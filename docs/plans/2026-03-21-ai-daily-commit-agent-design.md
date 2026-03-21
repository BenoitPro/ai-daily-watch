# AI Daily Commit Agent Design

> Auto-approved from the user's brief because the requested workflow explicitly forbids back-and-forth confirmation.

## Goal

Create a lightweight local agent that runs once per day on this Mac, fetches a small AI news watchlist, updates a single Markdown file in the repository, commits the change, and pushes it to GitHub so the user's contribution graph stays active.

## Constraints

- Single durable content file, not one file per day
- No paid APIs
- Simple and robust over "smart"
- Must run locally on macOS without manual intervention
- Commit must be attributable to the user's GitHub account
- Use GitHub as the long-term archive for the watch log

## Options Considered

### 1. GitHub Actions scheduled workflow

Pros: easy scheduling, no local setup after push.
Cons: does not match the requirement that the agent runs on the user's computer.

### 2. Cron job with shell script

Pros: very small footprint.
Cons: less native on modern macOS, weaker observability than `launchd`.

### 3. `launchd` + Python standard library script

Pros: native macOS scheduling, no extra paid service, easy local logs, easy retries, can run `git` and network fetches directly.
Cons: slightly more setup than cron.

## Chosen Approach

Use a single Python 3 script driven by a `launchd` LaunchAgent. The script fetches a few free RSS feeds, ranks candidate AI stories with simple keyword heuristics, appends one daily section to a single file named `AI_NEWS_LOG.md`, commits the change with the user's Git identity, and pushes to `main`.

## Data Flow

1. LaunchAgent starts once per day.
2. Python script fetches RSS feeds with `urllib`.
3. The script normalizes and deduplicates entries.
4. The script scores entries using recency and AI keyword matches.
5. The top 5 to 10 items are formatted into a dated Markdown section.
6. The script updates `AI_NEWS_LOG.md` only if that day's section is missing or stale.
7. The script runs `git add`, `git commit`, and `git push origin main`.
8. Local logs capture stdout and stderr for debugging.

## Source Strategy

Keep sources simple and free:

- Google News RSS for broad AI headlines
- Google News RSS for major AI labs and tools
- Hacker News Algolia API for technical AI/tooling stories

This mix gives broad coverage without relying on paid APIs or fragile scraping.

## Commit Counting Strategy

To maximize the chance that GitHub counts the contribution:

- Push to the repository's default branch (`main`)
- Use the Git identity already configured for the user's GitHub account
- Make a real file change every day by appending a dated section to `AI_NEWS_LOG.md`
- Push to a repository owned by the authenticated GitHub user
- Prefer a public repository so the contribution is plainly visible

## Repository Layout

- `AI_NEWS_LOG.md`: single long-lived watch file
- `scripts/daily_ai_digest.py`: fetch, score, update, commit, push
- `tests/test_daily_ai_digest.py`: unit tests
- `README.md`: setup and operational notes
- `launchd/com.benoitpro.ai-daily-watch.plist`: LaunchAgent template

## Error Handling

- If one feed fails, continue with the others
- If no fresh stories are available, still update the day's section with a short fallback note so the daily commit remains a real change
- If `git push` fails, keep the local commit and log the error for the next run

## Testing Strategy

- Unit tests for scoring, deduplication, section rendering, and log-file updates
- Dry-run execution to inspect the generated Markdown without pushing
- Real end-to-end execution against the actual repository before declaring success
