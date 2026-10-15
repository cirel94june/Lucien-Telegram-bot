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
        self.assertFalse(bot._superseded_by_later_reply(job(1, reply=False), self.queue_of(job(2))))

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
        self.assertEqual(seen, [(1, False, "superseded"), (2, False, "ceci"), (3, False, "superseded"), (4, True, "ceci")])

    def test_superseded_message_never_turns_into_a_random_interjection(self):
        with mock.patch.object(bot.random, "random", return_value=0.0), \
                mock.patch.object(bot, "_load_window_history", return_value=[]), \
                mock.patch.object(bot, "_save_window_history"), \
                mock.patch.object(bot, "send_reaction"), \
                mock.patch.object(bot, "call_claude") as model, \
                mock.patch.dict(bot.LAST_SPOKE, {}, clear=True):
            bot.process_message_background(*job(1, reply=False, reason="superseded"))
        model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
