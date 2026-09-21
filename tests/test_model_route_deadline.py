import os
import threading
import unittest
from contextlib import ExitStack
from unittest import mock

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test-token")
os.environ["PROACTIVE_ENABLED"] = "false"
os.environ["PROACTIVE_BACKGROUND_ENABLED"] = "false"
os.environ["GIST_HISTORY_IO_ENABLED"] = "false"
os.environ["MEMORY_RECALL_ENABLED"] = "false"

import bot


class ModelRouteDeadlineTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in {
            "CLAUDE_URL": "https://primary.invalid/v1",
            "CLAUDE_KEY": "test-primary",
            "CLAUDE_MODELS": ["primary-one", "primary-two"],
            "API_FORMAT": "openai",
            "BACKUP_BASE_URL": "https://backup.invalid/v1",
            "BACKUP_API_KEY": "test-backup",
            "BACKUP_MODELS": ["backup-one"],
            "BACKUP_API_FORMAT": "openai",
            "CECI_SEEN": {},
        }.items():
            self.stack.enter_context(mock.patch.object(bot, name, value))
        for name in ("build_cross_chat_context", "build_group_identity_hint"):
            self.stack.enter_context(mock.patch.object(bot, name, return_value=""))
        self.stack.enter_context(mock.patch.object(bot, "_hub_process_capabilities", side_effect=lambda text: text))
        self.stack.enter_context(mock.patch.object(bot, "_decode_model_json", side_effect=lambda response: response.json()))

    @staticmethod
    def response(text):
        response = mock.Mock(status_code=200)
        response.json.return_value = {"choices": [{"message": {"content": text}}]}
        return response

    def call(self):
        return bot.call_claude("hello", "", [{"role": "user", "content": "hello"}], "", chat_id="123")

    def test_primary_first_and_transport_timeout_bounded(self):
        with mock.patch.object(bot.requests, "post", return_value=self.response("ok")) as post:
            self.assertEqual(self.call()["text"], "ok")
        self.assertEqual(post.call_count, 1)
        self.assertIn("primary.invalid", post.call_args.args[0])
        connect, read = post.call_args.kwargs["timeout"]
        self.assertGreater(connect, 0)
        self.assertLessEqual(connect, 5)
        self.assertGreater(read, 0)
        self.assertLessEqual(read, 30)

    def test_primary_failures_fall_back_serially(self):
        with mock.patch.object(bot.requests, "post", side_effect=[
            bot.requests.exceptions.Timeout(),
            bot.requests.exceptions.Timeout(),
            self.response("backup"),
        ]) as post:
            self.assertEqual(self.call()["text"], "backup")
        self.assertEqual([c.kwargs["json"]["model"] for c in post.call_args_list],
                         ["primary-one", "primary-two", "backup-one"])

    def test_late_result_ignored_without_starting_second_primary_model(self):
        now = [100.0]

        def post_response(url, **kwargs):
            if "primary.invalid" in url:
                now[0] += 31
                return self.response("too late")
            return self.response("backup")

        with mock.patch.object(bot.time, "monotonic", side_effect=lambda: now[0]), \
                mock.patch.object(bot.requests, "post", side_effect=post_response) as post, \
                mock.patch("builtins.print") as log:
            self.assertEqual(self.call()["text"], "backup")
        self.assertEqual(post.call_count, 2)
        self.assertTrue(any("late response ignored" in str(c) for c in log.call_args_list))
        self.assertFalse(any("模型成功: primary" in str(c) for c in log.call_args_list))

    def test_outer_deadline_still_works_when_transport_ignores_timeout(self):
        release = threading.Event()
        finished = threading.Event()

        def post_response(url, **kwargs):
            if "primary.invalid" in url:
                release.wait(timeout=2)
                finished.set()
                return self.response("late")
            return self.response("backup")

        with mock.patch.object(bot, "_model_api_hard_timeout", return_value=0.03), \
                mock.patch.object(bot.requests, "post", side_effect=post_response) as post:
            try:
                self.assertEqual(self.call()["text"], "backup")
                self.assertFalse(finished.is_set())
            finally:
                release.set()
                self.assertTrue(finished.wait(timeout=1))
            self.assertEqual(post.call_count, 2)

    def test_missing_backup_remains_primary_only(self):
        with mock.patch.object(bot, "BACKUP_API_KEY", ""):
            self.assertEqual([route[-1] for route in bot._model_api_routes()], ["primary"])


if __name__ == "__main__":
    unittest.main()
