# Fresh sessions

`FRESH_SESSION_STARTS` is an optional JSON environment variable mapping chat IDs
to timezone-aware ISO timestamps. Default `{}` leaves all existing behavior intact.
Example: `{"123":"2026-10-27T10:00:00+08:00"}`.

For configured chats (including their topics):
- Only conversation events at or after the boundary enter model context.
- Hub window recovery still works for new messages after a restart.
- Gist history reads/writes and startup imports are skipped; old archives remain intact.
- Automatic Hub recall uses `/api/memory/recall` memory objects, not the mixed
  gateway context containing raw turns, corridor summaries, dreams and continuity.
  Gist identity, relationship, milestones and vocabulary remain available; rolling
  conversation summaries are excluded. Long-term memories are not deleted.
- Cross-window context remains enabled under existing privacy rules. Both source
  and destination boundaries apply, including to cached/legacy records.
- Proactive moments remain enabled, using the fresh local history and memory-only
  recall in these chats. Existing frequency and public-chat privacy rules remain.
- Normal replies, model safety checks, routing, and new Hub capture remain unchanged.

Changing the timestamp starts another session. Removing a chat from the variable
restores its original retrieval behavior and may reintroduce pre-reset history.
This is not a provider account unlock or a way to bypass content restrictions.
