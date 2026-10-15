"""排队时只回最新：后面还有同一对话要回复的消息，前面那条只记录不回复。"""
import threading
import unittest
from queue import Queue
from unittest import mock

from test_conversation_continuity import bot


def job(msg_id, *, reply=True, thread=None, image=None, reason="ceci"):
    # 与 enqueue_process_message 的参数顺序一致
    return ("在吗", "-100", "ceci", 1, reply, msg_id, image, None, False, False,
            "supergroup", reason, "1", False, None, thread)


class QueueReplyLatestTest(unittest.TestCase):
    def queue_of(self, *jobs):
        q = Queue()
        for j in jobs:
            q.put(j)
        return q

    def test_earlier_reply_is_superseded_by_a_later_one_in_the_same_thread(self):
        q = self.queue_of(job(2, reply=False), job(3))
        self.assertTrue(bot._superseded_by_later_reply(job(1), q))

    def test_not_superseded_without_a_later_reply(self):
        self.assertFalse(bot._superseded_by_later_reply(job(1), self.queue_of(job(2, reply=False))))
        self.assertFalse(bot._superseded_by_later_reply(job(1), self.queue_of()))

    def test_other_topics_and_images_are_not_skipped(self):
        self.assertFalse(bot._superseded_by_later_reply(job(1, thread="7"), self.queue_of(job(2, thread="8"))))
        self.assertFalse(bot._superseded_by_later_reply(job(1, image="b64"), self.queue_of(job(2))))
        # 原本不回复的也要挡住：不然关键词 / 随机插嘴会把它叫醒，抢在最新那条前面回旧消息
        self.assertTrue(bot._superseded_by_later_reply(job(1, reply=False), self.queue_of(job(2))))
        self.assertFalse(bot._superseded_by_later_reply(
            job(1, reply=False, reason="identity_alias_taught"), self.queue_of(job(2))))

    def test_worker_replies_only_to_the_newest_and_records_the_rest(self):
        q = self.queue_of(job(1), job(2, reply=False), job(3), job(4))
        seen = []
        done = threading.Event()

        def fake(*args):
            seen.append((args[5], args[4], args[11]))
            if args[5] == 4:
                done.set()
        with mock.patch.object(bot, "process_message_background", side_effect=fake):
            threading.Thread(target=bot._chat_process_worker, args=("-100", q), daemon=True).start()
            self.assertTrue(done.wait(2))
        self.assertEqual(seen, [(1, False, "superseded"), (2, False, "superseded"), (3, False, "superseded"), (4, True, "ceci")])

    def test_superseded_message_never_turns_into_a_random_interjection(self):
        with mock.patch.object(bot.random, "random", return_value=0.0), \
                mock.patch.object(bot, "_load_window_history", return_value=[]), \
                mock.patch.object(bot, "_save_window_history"), \
                mock.patch.object(bot, "send_reaction"), \
                mock.patch.object(bot, "call_claude") as model, \
                mock.patch.dict(bot.LAST_SPOKE, {}, clear=True):
            bot.process_message_background(*job(1, reply=False, reason="superseded"))
        model.assert_not_called()


class QueueReviewFollowupTest(unittest.TestCase):
    def test_trigger_word_cannot_wake_a_superseded_message(self):
        with mock.patch.object(bot, "TRIGGER_WORDS", ["在吗"]), \
                mock.patch.object(bot, "_load_window_history", return_value=[]), \
                mock.patch.object(bot, "_save_window_history"), \
                mock.patch.object(bot, "send_reaction"), \
                mock.patch.object(bot, "call_claude") as model, \
                mock.patch.dict(bot.LAST_SPOKE, {}, clear=True):
            bot.process_message_background(*job(1, reply=False, reason="superseded"))
        model.assert_not_called()

    def test_image_turn_keeps_the_earlier_unanswered_text(self):
        """Codex Q1：前面被跳过的文字和后面的图片在同一轮，发给模型时文字不能丢。"""
        history = [
            {"role": "user", "content": "UNANSWERED_SENTINEL", "raw_text": "UNANSWERED_SENTINEL"},
            {"role": "user", "content": "IMAGE_CAPTION", "raw_text": "IMAGE_CAPTION"},
        ]
        image = [{"type": "_bot_image", "media_type": "image/jpeg", "data": "QUJD"},
                 {"type": "text", "text": "IMAGE_CAPTION"}]
        sent = []

        def post(url, **kw):
            sent.append(kw["json"])
            r = mock.Mock(status_code=200, text="")
            r.json.return_value = {"content": [{"type": "text", "text": "看到了"}]}
            return r
        with mock.patch.object(bot, "API_FORMAT", "anthropic"), \
                mock.patch.object(bot, "CLAUDE_URL", "https://primary.invalid/v1"), \
                mock.patch.object(bot, "CLAUDE_MODELS", ["m"]), \
                mock.patch.object(bot, "BACKUP_API_KEY", ""), \
                mock.patch.object(bot, "build_cross_chat_context", return_value=""), \
                mock.patch.object(bot, "build_group_identity_hint", return_value=""), \
                mock.patch.object(bot, "_hub_process_capabilities", side_effect=lambda t: t), \
                mock.patch.object(bot, "_decode_model_json", side_effect=lambda r: r.json()), \
                mock.patch.object(bot.requests, "post", side_effect=post):
            reply = bot.call_claude(image, "", history, "", chat_id="123")
        self.assertEqual(reply["text"], "看到了")
        last = sent[0]["messages"][-1]["content"]
        texts = "".join(b.get("text", "") for b in last if isinstance(b, dict))
        self.assertIn("UNANSWERED_SENTINEL", texts)
        self.assertIn("IMAGE_CAPTION", texts)
        self.assertTrue(any(b.get("type") == "image" for b in last))


if __name__ == "__main__":
    unittest.main()
