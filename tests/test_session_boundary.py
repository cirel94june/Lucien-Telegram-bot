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

    def test_cross_window_restored_with_existing_privacy(self):
        self.assertTrue(cross_window.permitted("123", "-456", {"-456"}, "123"))
        self.assertTrue(cross_window.permitted("-789", "123", {"-456"}, "123"))
        self.assertFalse(cross_window.permitted("-456", "-789", {"-456"}, "123"))
        self.assertTrue(cross_window.permitted("-789", "-987", set(), "123"))

    def test_cross_window_filters_source_and_destination_even_cached_legacy_rows(self):
        context = cross_window.CrossWindowContext()
        old = self.event("OLD_SENTINEL", "2026-10-27T01:00:00Z", "-789")
        new = self.event("NEW_SENTINEL", "2026-10-27T03:00:00Z", "-789")
        del old["chat_id"]
        del new["chat_id"]
        def render(events, **kwargs):
            return [{"content": e["content"]} for e in events]
        with mock.patch.object(cross_window.time, "time", return_value=self.cutoff + 7200):
            for source, destination in (("-789", "123"), ("-456", "123"), ("-456", "-999")):
                context.cache = {(source, ""): [old, new]}
                text = context.build(destination, {}, private_chats={"-456", "-999"},
                                     ceci_id="123", render=render)
                self.assertNotIn("OLD_SENTINEL", text)
                self.assertIn("NEW_SENTINEL", text)

    def test_fresh_paths_do_not_read_or_overwrite_remote_archives(self):
        with mock.patch.object(bot.requests, "get") as get, \
                mock.patch.object(bot.requests, "post") as post, \
                mock.patch.object(bot.requests, "patch") as patch, \
                mock.patch.object(bot, "GIST_HISTORY_IO_ENABLED", True), \
                mock.patch.object(bot, "HISTORY_CACHE", {}):
            self.assertEqual(bot.load_history("123"), [])
            bot.save_history([], "123", force=True)
            get.assert_not_called()
            post.assert_not_called()
            patch.assert_not_called()

    def test_memory_only_recall_excludes_gateway_raw_fields_and_obeys_ai_scope(self):
        response = mock.Mock()
        response.json.return_value = {
            "results": [{"content": "KEPT_MEMORY", "source_context": "OLD_RAW"},
                        {"content": "INACTIVE", "status": "deleted"}],
            "inject_text": "OLD_GATEWAY", "recent_turns": "OLD_RAW"}
        with mock.patch.object(bot.requests, "get", return_value=response) as get, \
                mock.patch.object(bot.requests, "post") as post, \
                mock.patch.object(bot, "MEMORY_HUB_URL", "https://hub.invalid"), \
                mock.patch.object(bot, "MEMORY_HUB_SECRET", "test"), \
                mock.patch.object(bot, "AI_ID", "lucien"):
            text, _ = bot.hub_get_context("hello", chat_id="123", chat_type="private")
            self.assertIn("KEPT_MEMORY", text)
            self.assertNotIn("OLD_", text)
            self.assertNotIn("INACTIVE", text)
            self.assertEqual(get.call_args.kwargs["params"]["ai_id"], "lucien")
            self.assertTrue(get.call_args.args[0].endswith("/api/memory/recall"))
            post.assert_not_called()

    def test_gist_core_available_without_old_conversation_summaries(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = {"files": {"memory.json": {"content":
            '{"core":{"identity":"CORE_IDENTITY"},"rolling_7days":"OLD_ROLLING",'
            '"summaries_123":[{"content":"OLD_SUMMARY"}]}'}}}
        with mock.patch.object(bot.requests, "get", return_value=response), \
                mock.patch.object(bot, "MEMORY_URL", "https://gist.github.com/test"), \
                mock.patch.object(bot, "GIST_TOKEN", "test"):
            text = bot.fetch_memory("123")
            self.assertIn("CORE_IDENTITY", text)
            self.assertNotIn("OLD_", text)

    def test_proactive_generation_uses_fresh_context_and_existing_completion_guard(self):
        with mock.patch.object(bot, "load_history", return_value=[]) as load, \
                mock.patch.object(bot, "fetch_memory", return_value="CORE_IDENTITY"), \
                mock.patch.object(bot, "hub_get_context", return_value=("KEPT_MEMORY", "")), \
                mock.patch.object(bot, "_call_ai_simple", return_value="Hello again.") as call, \
                mock.patch.object(bot, "_proactive_text_complete", return_value=True):
            self.assertEqual(bot.generate_moment_text("123"), "Hello again.")
            load.assert_called_once_with("123")
            self.assertIn("KEPT_MEMORY", call.call_args.args[0])

    def test_configuration_is_explicit_and_timezone_aware(self):
        with mock.patch.dict(os.environ, {"FRESH_SESSION_STARTS": '{"123":"2026-10-27T10:00:00+08:00"}'}):
            self.assertEqual(boundary.load_starts(), {"123": self.cutoff})
        for raw in ('[]', '{"123":"yesterday"}', '{"123":"2026-10-27T10:00:00"}'):
            with mock.patch.dict(os.environ, {"FRESH_SESSION_STARTS": raw}):
                with self.assertRaises(ValueError):
                    boundary.load_starts()
