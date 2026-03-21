# AI Daily Commit Agent

Local macOS agent that writes one AI news digest per day into a single Markdown file, then commits and pushes it to GitHub.

## What it does

- Fetches a small AI watchlist from free sources
- Keeps only 5 to 10 signal-heavy items
- Writes everything into one file: `AI_NEWS_LOG.md`
- Commits to `main` with the GitHub identity already configured on this Mac
- Pushes to GitHub once per day via macOS `launchd`
- Sends a plain-text email recap to `benoit.baillon@edhec.com`

## Sources

- Google News RSS search for broad AI headlines
- Google News RSS search for major AI labs and tools
- Hacker News Algolia API for technical AI stories

## Local run

Dry run:

```bash
python3 scripts/daily_ai_digest.py --dry-run
```

Live run:

```bash
python3 scripts/daily_ai_digest.py
```

The live run updates GitHub and sends the email summary.

## Schedule

The LaunchAgent is set to run every day at `09:00` local time.

Template file:

`launchd/com.benoitpro.ai-daily-watch.plist`

Installed location on macOS:

`~/Library/LaunchAgents/com.benoitpro.ai-daily-watch.plist`

## Notes

- The digest keeps a single long-lived Markdown log instead of creating one file per day.
- If the news signal is weak, the script still writes a short fallback entry so the file changes and the commit remains real.
- The configured Git identity for this machine is used for attribution.
- Email delivery uses the local Apple Mail setup on this Mac.
