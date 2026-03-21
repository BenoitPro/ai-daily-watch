import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
MODULE_PATH = PROJECT_ROOT / "scripts" / "daily_ai_digest.py"


def load_module():
    spec = importlib.util.spec_from_file_location("daily_ai_digest", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RenderSectionTests(unittest.TestCase):
    def test_render_section_includes_date_and_items(self):
        digest = load_module()

        section = digest.render_section(
            "2026-03-21",
            [
                {
                    "title": "OpenAI ships a new coding agent",
                    "source": "Example Source",
                    "link": "https://example.com/story",
                    "implication": "Developer workflows will keep getting more automated.",
                }
            ],
        )

        self.assertIn("## 2026-03-21", section)
        self.assertIn("OpenAI ships a new coding agent", section)
        self.assertIn("Developer workflows will keep getting more automated.", section)


class RankingAndLogTests(unittest.TestCase):
    def test_dedupe_items_removes_same_story_by_normalized_title(self):
        digest = load_module()

        deduped = digest.dedupe_items(
            [
                {"title": "OpenAI releases a new model!", "source": "A", "link": "https://a.test"},
                {"title": "OpenAI releases a new model", "source": "B", "link": "https://b.test"},
            ]
        )

        self.assertEqual(len(deduped), 1)

    def test_rank_items_prioritizes_major_ai_tool_releases(self):
        digest = load_module()

        ranked = digest.rank_items(
            [
                {
                    "title": "Startup raises funding for general SaaS analytics",
                    "source": "Tech Site",
                    "link": "https://example.com/other",
                },
                {
                    "title": "Anthropic launches a new coding model for developers",
                    "source": "Tech Site",
                    "link": "https://example.com/ai",
                },
            ]
        )

        self.assertEqual(ranked[0]["title"], "Anthropic launches a new coding model for developers")

    def test_upsert_section_replaces_existing_day_section(self):
        digest = load_module()

        original = "# AI News Log\n\n## 2026-03-21\n\nOld section\n\n## 2026-03-20\n\nEarlier section\n"
        updated = digest.upsert_section(
            original,
            "2026-03-21",
            "## 2026-03-21\n\nNew section\n",
        )

        self.assertIn("New section", updated)
        self.assertNotIn("Old section", updated)
        self.assertIn("Earlier section", updated)


class CliTests(unittest.TestCase):
    def test_parse_args_supports_dry_run_date_and_limit(self):
        digest = load_module()

        args = digest.parse_args(["--dry-run", "--date", "2026-03-21", "--limit", "5"])

        self.assertTrue(args.dry_run)
        self.assertEqual(args.date, "2026-03-21")
        self.assertEqual(args.limit, 5)

    def test_build_commit_message_uses_date(self):
        digest = load_module()
        self.assertEqual(digest.build_commit_message("2026-03-21"), "chore: daily AI watch 2026-03-21")

    def test_run_git_uses_subprocess(self):
        digest = load_module()

        with mock.patch.object(digest.subprocess, "run") as mocked_run:
            mocked_run.return_value = mock.Mock(returncode=0)
            digest.run_git(["status"])

        mocked_run.assert_called_once()


class GitFlowTests(unittest.TestCase):
    def test_commit_and_push_pushes_even_without_new_staged_changes(self):
        digest = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = pathlib.Path(tmpdir)
            log_path = repo_root / "AI_NEWS_LOG.md"
            launchd_path = repo_root / "launchd" / "com.benoitpro.ai-daily-watch.plist"
            launchd_path.parent.mkdir(parents=True)
            log_path.write_text("log")
            launchd_path.write_text("plist")

            calls = []

            def fake_run_git(args, cwd=None):
                calls.append(args)
                if args[:3] == ["diff", "--cached", "--quiet"]:
                    return mock.Mock(returncode=0, stderr="")
                return mock.Mock(returncode=0, stderr="")

            with mock.patch.object(digest, "REPO_ROOT", repo_root), mock.patch.object(digest, "LAUNCHD_FILE", launchd_path), mock.patch.object(digest, "run_git", side_effect=fake_run_git):
                changed = digest.commit_and_push(log_path, "2026-03-21")

        self.assertFalse(changed)
        self.assertIn(["push", "origin", "main"], calls)


class IntegrationHelpersTests(unittest.TestCase):
    def test_parse_google_news_feed_extracts_story_fields(self):
        digest = load_module()
        xml_text = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>OpenAI launches a new agent - Example Source</title>
      <link>https://news.google.com/articles/example</link>
      <pubDate>Sat, 21 Mar 2026 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

        items = digest.parse_google_news_feed(xml_text)

        self.assertEqual(items[0]["title"], "OpenAI launches a new agent")
        self.assertEqual(items[0]["source"], "Example Source")
        self.assertEqual(items[0]["link"], "https://news.google.com/articles/example")

    def test_build_launch_agent_plist_includes_script_and_logs(self):
        digest = load_module()

        plist = digest.build_launch_agent_plist(
            python_path="/opt/homebrew/bin/python3",
            script_path="/tmp/repo/scripts/daily_ai_digest.py",
            repo_root="/tmp/repo",
            hour=9,
            minute=0,
        )

        self.assertIn("com.benoitpro.ai-daily-watch", plist)
        self.assertIn("/tmp/repo/scripts/daily_ai_digest.py", plist)
        self.assertIn("/tmp/repo/logs/ai-daily-watch.out.log", plist)
        self.assertIn("<integer>9</integer>", plist)
        self.assertIn("<integer>0</integer>", plist)

    def test_build_email_body_includes_top_items(self):
        digest = load_module()

        body = digest.build_email_body(
            "2026-03-21",
            [
                {
                    "title": "OpenAI ships a new coding agent",
                    "source": "Example Source",
                    "link": "https://example.com/story",
                    "implication": "Developer workflows will keep getting more automated.",
                }
            ],
        )

        self.assertIn("ALAIN // VEILLE IA", body)
        self.assertIn("21 mars 2026", body)
        self.assertIn("Signal du jour", body)
        self.assertIn("Radar du jour", body)
        self.assertIn("1. OpenAI ships a new coding agent", body)
        self.assertIn("OpenAI ships a new coding agent", body)
        self.assertIn("Developer workflows will keep getting more automated.", body)

    def test_build_email_subject_uses_date(self):
        digest = load_module()
        self.assertEqual(digest.build_email_subject("2026-03-21"), "Veille IA - 2026-03-21")

    def test_build_mail_applescript_pins_mail_account_and_recipient(self):
        digest = load_module()

        script = digest.build_mail_applescript(
            recipient="benoit.baillon@edhec.com",
            subject="Veille IA - 2026-03-21",
            body="Test body",
        )

        self.assertIn('address:"benoit.baillon@edhec.com"', script)
        self.assertIn('subject:"Veille IA - 2026-03-21"', script)
        self.assertIn('sender:"benoit.baillon@edhec.com"', script)


class FileUpdateTests(unittest.TestCase):
    def test_build_digest_items_creates_fallback_when_sources_are_empty(self):
        digest = load_module()

        items = digest.build_digest_items([], limit=5)

        self.assertEqual(len(items), 1)
        self.assertIn("Low signal", items[0]["title"])

    def test_update_log_file_writes_day_section(self):
        digest = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = pathlib.Path(tmpdir) / "AI_NEWS_LOG.md"
            digest.update_log_file(
                log_path,
                "2026-03-21",
                [
                    {
                        "title": "Anthropic launches a new coding model",
                        "source": "Example",
                        "link": "https://example.com/story",
                        "implication": "Coding workflows will keep improving.",
                    }
                ],
            )

            text = log_path.read_text()

        self.assertIn("# AI News Log", text)
        self.assertIn("## 2026-03-21", text)
        self.assertIn("Anthropic launches a new coding model", text)


class MainFlowTests(unittest.TestCase):
    def test_main_live_run_does_not_regenerate_launch_agent(self):
        digest = load_module()

        with mock.patch.object(digest, "fetch_candidate_items", return_value=[]), mock.patch.object(digest, "build_digest_items", return_value=[{"title": "Low signal day for AI news", "source": "Internal fallback", "link": "https://github.com", "implication": "Fallback."}]), mock.patch.object(digest, "update_log_file"), mock.patch.object(digest, "ensure_origin_remote"), mock.patch.object(digest, "commit_and_push", return_value=True), mock.patch.object(digest, "write_launch_agent_file") as mocked_write_launch_agent, mock.patch.object(digest, "send_summary_email") as mocked_send_summary_email:
            exit_code = digest.main(["--date", "2026-03-21"])

        self.assertEqual(exit_code, 0)
        mocked_write_launch_agent.assert_not_called()
        mocked_send_summary_email.assert_called_once()


if __name__ == "__main__":
    unittest.main()
