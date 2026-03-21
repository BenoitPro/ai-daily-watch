# AI Daily Commit Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local macOS agent that writes a daily AI news digest into one Markdown file, commits it, and pushes it to GitHub every day.

**Architecture:** A single Python entrypoint fetches and ranks a few free news sources, updates `AI_NEWS_LOG.md`, and optionally performs git add/commit/push. A LaunchAgent runs that entrypoint on a fixed daily schedule and writes logs locally.

**Tech Stack:** Python 3 standard library, `unittest`, Git, GitHub CLI, macOS `launchd`

---

### Task 1: Repository Skeleton

**Files:**
- Create: `README.md`
- Create: `AI_NEWS_LOG.md`
- Create: `scripts/daily_ai_digest.py`
- Create: `tests/test_daily_ai_digest.py`
- Create: `launchd/com.benoitpro.ai-daily-watch.plist`

**Step 1: Write the failing test**

Add a test that imports the future script module and asserts it can render a daily section from sample items.

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_daily_ai_digest.py -v`
Expected: FAIL because the module or function does not exist yet.

**Step 3: Write minimal implementation**

Create the script module and the smallest rendering function needed to make the first test pass.

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests/test_daily_ai_digest.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_daily_ai_digest.py scripts/daily_ai_digest.py README.md AI_NEWS_LOG.md
git commit -m "feat: scaffold daily ai digest agent"
```

### Task 2: Ranking and Log Updates

**Files:**
- Modify: `scripts/daily_ai_digest.py`
- Modify: `tests/test_daily_ai_digest.py`

**Step 1: Write the failing test**

Add tests for deduplication, keyword scoring, and replacing an existing section for the same date.

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_daily_ai_digest.py -v`
Expected: FAIL on missing behavior.

**Step 3: Write minimal implementation**

Implement pure functions for normalization, ranking, and idempotent file updates.

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests/test_daily_ai_digest.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_daily_ai_digest.py scripts/daily_ai_digest.py
git commit -m "feat: rank ai news and update single log file"
```

### Task 3: CLI, Git Operations, and Dry Run

**Files:**
- Modify: `scripts/daily_ai_digest.py`
- Modify: `tests/test_daily_ai_digest.py`

**Step 1: Write the failing test**

Add tests for argument parsing and commit message generation.

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_daily_ai_digest.py -v`
Expected: FAIL on missing CLI helpers.

**Step 3: Write minimal implementation**

Add `--dry-run`, `--date`, and `--limit` options plus the git command wrapper.

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests/test_daily_ai_digest.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_daily_ai_digest.py scripts/daily_ai_digest.py
git commit -m "feat: add cli flow and git automation"
```

### Task 4: Scheduling and Docs

**Files:**
- Modify: `README.md`
- Modify: `launchd/com.benoitpro.ai-daily-watch.plist`

**Step 1: Write the failing test**

Add a small test that validates the LaunchAgent template placeholders and default program path.

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_daily_ai_digest.py -v`
Expected: FAIL on missing config expectations.

**Step 3: Write minimal implementation**

Document installation steps and create a LaunchAgent template plus an installer path in the script or README.

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests/test_daily_ai_digest.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add README.md launchd/com.benoitpro.ai-daily-watch.plist tests/test_daily_ai_digest.py
git commit -m "docs: add launchd automation setup"
```

### Task 5: Production Wiring

**Files:**
- Modify: `README.md`
- Modify: `scripts/daily_ai_digest.py`

**Step 1: Run the full test suite**

Run: `python3 -m unittest tests/test_daily_ai_digest.py -v`
Expected: PASS

**Step 2: Run a dry run against today**

Run: `python3 scripts/daily_ai_digest.py --dry-run --date 2026-03-21`
Expected: Printed Markdown section with 5 to 10 items.

**Step 3: Run the real command**

Run: `python3 scripts/daily_ai_digest.py --date 2026-03-21`
Expected: `AI_NEWS_LOG.md` updated locally and committed.

**Step 4: Create/push repository**

Run: `gh repo create <name> --public --source=. --remote=origin --push`
Expected: Repository exists on the authenticated account and `main` is pushed.

**Step 5: Install LaunchAgent**

Run:

```bash
mkdir -p ~/Library/LaunchAgents
cp launchd/com.benoitpro.ai-daily-watch.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.benoitpro.ai-daily-watch.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.benoitpro.ai-daily-watch.plist
```

Expected: Agent is loaded and scheduled for daily execution.
