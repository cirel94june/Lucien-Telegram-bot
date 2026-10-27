"""Operator-controlled fresh sessions; original archives are never deleted."""
import json
import os
from datetime import datetime


def timestamp(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.timestamp() if dt.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def load_starts():
    raw = os.environ.get("FRESH_SESSION_STARTS", "{}").strip() or "{}"
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("FRESH_SESSION_STARTS must be a JSON object")
    starts = {}
    for chat_id, value in data.items():
        stamp = timestamp(value)
        if stamp is None or not str(chat_id).lstrip("-").isdigit():
            raise ValueError("FRESH_SESSION_STARTS requires chat IDs and timezone-aware ISO dates")
        starts[str(chat_id)] = stamp
    return starts


STARTS = load_starts()


def active(chat_id):
    return str(chat_id) in STARTS


def filter_events(events, chat_id=None):
    kept = []
    for event in events:
        cid = str(chat_id if chat_id is not None else event.get("chat_id", ""))
        cutoff = STARTS.get(cid)
        if cutoff is None:
            kept.append(event)
            continue
        stamp = timestamp(event.get("created_at") or event.get("timestamp"))
        if stamp is not None and stamp >= cutoff:
            kept.append(event)
    return kept
