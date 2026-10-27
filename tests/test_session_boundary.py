import os
import unittest
from unittest import mock

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test-token")
for flag in ("PROACTIVE_ENABLED", "PROACTIVE_BACKGROUND_ENABLED", "GIST_HISTORY_IO_ENABLED", "MEMORY_RECALL_ENABLED"):
    os.environ[flag] = "false"

import bot
import cross_window
import session_boundary as boundary


class FreshSessionTest(unittest.TestCase):
    def setUp(self):
        self.cutoff = boundary.timestamp("2026-10-27T02:00:00Z")
        patch = mock.patch.object(boundary, "STARTS", {"123": self.cutoff, "-456": self.cutoff})
        patch.start()
        self.addCleanup(patch.stop)

    def event(self, text, stamp, cid="123"):
        return {"role": "user", "chat_id": cid, "created_at": stamp,
                "content": text, "raw_text": text}

    def test_cutoff_retains_new_and_excludes_old_or_undated(self):
        events = [self.event("old", "2026-10-26T12:00:00Z"),
                  self.event("unknown", ""), self.event("naive", "2026-10-28T12:00:00"),
                  self.event("new", "2026-10-27T02:00:00Z")]
        self.assertEqual([e["content"] for e in boundary.filter_events(events)], ["new"])
        self.assertEqual(len(events), 4)
        self.assertEqual(boundary.filter_events(events, "other"), events)

    def test_final_prompt_filters_hub_restored_records(self):
        events = [self.event("OLD_SENTINEL", "2026-10-26T12:00:00Z"),
                  self.event("NEW_SENTINEL", "2026-10-27T03:00:00Z")]
        text = str(bot.build_model_messages(events))
        self.assertNotIn("OLD_SENTINEL", text)
        self.assertIn("NEW_SENTINEL", text)

    def test_cross_window_isolated_in_both_directions(self):
        self.assertFalse(cross_window.permitted("123", "-456", {"-456"}, "123"))
        self.assertFalse(cross_window.permitted("-789", "123", {"-456"}, "123"))
        self.assertFalse(cross_window.permitted("-456", "-789", {"-456"}, "123"))
        self.assertTrue(cross_window.permitted("-789", "-987", set(), "123"))

    def test_fresh_paths_do_not_read_or_overwrite_remote_archives(self):
        with mock.patch.object(bot.requests, "get") as get, \
                mock.patch.object(bot.requests, "post") as post, \
                mock.patch.object(bot.requests, "patch") as patch, \
                mock.patch.object(bot, "GIST_HISTORY_IO_ENABLED", True), \
                mock.patch.object(bot, "HISTORY_CACHE", {}):
            self.assertEqual(bot.load_history("123"), [])
            bot.save_history([], "123", force=True)
            self.assertEqual(bot.hub_get_context("hello", chat_id="123"), (None, ""))
            self.assertTrue(bot.fetch_memory("123"))
            self.assertEqual(bot.build_cross_chat_context("123"), "")
            self.assertEqual(bot.generate_moment_text("123"), "")
            get.assert_not_called()
            post.assert_not_called()
            patch.assert_not_called()

    def test_configuration_is_explicit_and_timezone_aware(self):
        with mock.patch.dict(os.environ, {"FRESH_SESSION_STARTS": '{"123":"2026-10-27T10:00:00+08:00"}'}):
            self.assertEqual(boundary.load_starts(), {"123": self.cutoff})
        for raw in ('[]', '{"123":"yesterday"}', '{"123":"2026-10-27T10:00:00"}'):
            with mock.patch.dict(os.environ, {"FRESH_SESSION_STARTS": raw}):
                with self.assertRaises(ValueError):
                    boundary.load_starts()
