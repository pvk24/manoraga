"""User taste profile (use case 4). SQLite, one file, no ML yet.

Two kinds of signal:
- preferences: explicit settings ("I'm a beginner", "I like Tamil songs", "favourite composer: Dikshitar")
- feedback: likes/dislikes on raagas, krithis, composers, captured from conversation
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "user_data.db"

ALLOWED_PREFS = {
    "level": "beginner | intermediate | advanced — controls how technical explanations are",
    "languages": "preferred song languages, e.g. ['Tamil', 'Telugu']",
    "favourite_composers": "list of composers",
    "favourite_artists": "list of performers (free text; not yet used for ranking)",
    "interests": "free-text list of things they want to learn about, e.g. ['gamakas', 'tala']",
}


class ProfileStore:
    def __init__(self, path: Path | str = DEFAULT_DB):
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS preferences (
                user_id TEXT, key TEXT, value TEXT, updated_at REAL,
                PRIMARY KEY (user_id, key));
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT, item_type TEXT, item_name TEXT, signal INTEGER, note TEXT, created_at REAL);
            CREATE TABLE IF NOT EXISTS mood_overrides (
                user_id TEXT, item_key TEXT, remove TEXT, "add" TEXT, updated_at REAL,
                PRIMARY KEY (user_id, item_key));
            """
        )

    def set_preference(self, user_id: str, key: str, value) -> dict:
        if key not in ALLOWED_PREFS:
            return {"error": f"Unknown preference '{key}'. Allowed: {list(ALLOWED_PREFS)}"}
        self.conn.execute(
            "INSERT OR REPLACE INTO preferences VALUES (?, ?, ?, ?)",
            (user_id, key, json.dumps(value), time.time()),
        )
        self.conn.commit()
        return {"ok": True, "key": key, "value": value}

    def record_feedback(self, user_id: str, item_type: str, item_name: str, signal: int, note: str = "") -> dict:
        if item_type not in {"raaga", "krithi", "composer"}:
            return {"error": "item_type must be raaga, krithi or composer"}
        if signal not in (1, -1):
            return {"error": "signal must be 1 (like) or -1 (dislike)"}
        self.conn.execute(
            "INSERT INTO feedback (user_id, item_type, item_name, signal, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, item_type, item_name, signal, note, time.time()),
        )
        self.conn.commit()
        return {"ok": True}

    def set_mood_override(self, user_id: str, item_type: str, item_name: str,
                          remove: list[str] | None = None, add: list[str] | None = None) -> dict:
        """The user's own view of a song or raaga ("that's not upbeat, it's soothing"). Applies only to them.
        remove = moods it must never be suggested for; add = moods it should count for. Latest statement wins."""
        if item_type not in {"raaga", "krithi"}:
            return {"error": "item_type must be raaga or krithi"}
        key = f"{item_type}|{item_name.strip().lower()}"
        row = self.conn.execute("SELECT remove, \"add\" FROM mood_overrides WHERE user_id = ? AND item_key = ?",
                                (user_id, key)).fetchone()
        rem, add_ = (json.loads(row[0]), json.loads(row[1])) if row else ([], [])
        for m in remove or []:
            rem = rem + [m] if m not in rem else rem
            add_ = [x for x in add_ if x != m]
        for m in add or []:
            add_ = add_ + [m] if m not in add_ else add_
            rem = [x for x in rem if x != m]
        self.conn.execute("INSERT OR REPLACE INTO mood_overrides VALUES (?, ?, ?, ?, ?)",
                          (user_id, key, json.dumps(rem), json.dumps(add_), time.time()))
        self.conn.commit()
        return {"ok": True, "item": key, "remove": rem, "add": add_}

    def get(self, user_id: str) -> dict:
        prefs = {k: json.loads(v) for k, v in self.conn.execute(
            "SELECT key, value FROM preferences WHERE user_id = ?", (user_id,))}
        # Latest signal per item wins, so a user can change their mind.
        rows = self.conn.execute(
            """SELECT item_type, item_name, signal FROM feedback f
               WHERE user_id = ? AND id = (SELECT MAX(id) FROM feedback
                   WHERE user_id = f.user_id AND item_type = f.item_type AND lower(item_name) = lower(f.item_name))""",
            (user_id,),
        ).fetchall()
        likes: dict[str, list[str]] = {"raaga": [], "krithi": [], "composer": []}
        dislikes: dict[str, list[str]] = {"raaga": [], "krithi": [], "composer": []}
        for t, name, sig in rows:
            (likes if sig > 0 else dislikes)[t].append(name)
        overrides = {k: {"remove": json.loads(r), "add": json.loads(a)} for k, r, a in self.conn.execute(
            "SELECT item_key, remove, \"add\" FROM mood_overrides WHERE user_id = ? ORDER BY item_key", (user_id,))}
        return {"preferences": prefs, "likes": likes, "dislikes": dislikes, "mood_overrides": overrides}
