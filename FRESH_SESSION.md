# Fresh sessions

`FRESH_SESSION_STARTS` is an optional JSON environment variable mapping chat IDs
to timezone-aware ISO timestamps. Default `{}` leaves all existing behavior intact.
Example: `{"123":"2026-10-27T10:00:00+08:00"}`.

For configured chats (including their topics):
- Only conversation events at or after the boundary enter model context.
- Hub window recovery still works for new messages after a restart.
- Gist history reads/writes and startup imports are skipped; old archives remain intact.
- Mixed Hub context injection and Gist core-memory fallback are temporarily skipped.
  Stored long-term memories are NOT deleted, but automatic recall is unavailable
  in these sessions until a separately verified retrieval boundary is supported.
- Cross-window context is disabled in both directions for the configured chats.
- Proactive moments are paused for these chats to avoid an alternative recall path.
- Normal replies, model safety checks, routing, and new Hub capture remain unchanged.

Changing the timestamp starts another session. Removing a chat from the variable
restores its original retrieval behavior and may reintroduce pre-reset history.
This is not a provider account unlock or a way to bypass content restrictions.
