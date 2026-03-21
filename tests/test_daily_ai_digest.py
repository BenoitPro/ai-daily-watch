import importlib.util
import pathlib
import unittest


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


if __name__ == "__main__":
    unittest.main()
