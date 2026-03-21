"""SQLite database with FTS5 for XPlus Contacts."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "contacts.db"


def _sanitize_fts(query: str) -> str:
    """Sanitize input for FTS5 MATCH to prevent injection."""
    cleaned = query.replace('"', '').replace("'", "").replace('*', '').replace('(', '').replace(')', '')
    tokens = cleaned.split()
    if not tokens:
        return '""'
    return " ".join(f'"{t}"' for t in tokens[:20])


class ContactsDB:
    """Thread-safe SQLite contacts database with FTS5 full-text search."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = str(db_path or DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id TEXT PRIMARY KEY,
                    first_name TEXT NOT NULL DEFAULT '',
                    last_name TEXT NOT NULL DEFAULT '',
                    nickname TEXT DEFAULT '',
                    company TEXT DEFAULT '',
                    job_title TEXT DEFAULT '',
                    email TEXT DEFAULT '',
                    email2 TEXT DEFAULT '',
                    phone TEXT DEFAULT '',
                    phone2 TEXT DEFAULT '',
                    mobile TEXT DEFAULT '',
                    address TEXT DEFAULT '',
                    city TEXT DEFAULT '',
                    state TEXT DEFAULT '',
                    zip_code TEXT DEFAULT '',
                    country TEXT DEFAULT '',
                    website TEXT DEFAULT '',
                    linkedin TEXT DEFAULT '',
                    twitter TEXT DEFAULT '',
                    github TEXT DEFAULT '',
                    instagram TEXT DEFAULT '',
                    facebook TEXT DEFAULT '',
                    category TEXT DEFAULT 'personal',
                    tags TEXT DEFAULT '[]',
                    notes TEXT DEFAULT '',
                    photo_url TEXT DEFAULT '',
                    is_favorite INTEGER DEFAULT 0,
                    custom_fields TEXT DEFAULT '{}',
                    interaction_history TEXT DEFAULT '[]',
                    source TEXT DEFAULT 'manual',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_contacted REAL DEFAULT NULL
                );

                CREATE TABLE IF NOT EXISTS categories (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    color TEXT DEFAULT '#6366f1',
                    icon TEXT DEFAULT 'folder',
                    sort_order INTEGER DEFAULT 0,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS interaction_log (
                    id TEXT PRIMARY KEY,
                    contact_id TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'note',
                    content TEXT NOT NULL,
                    date REAL NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_contacts_category ON contacts(category);
                CREATE INDEX IF NOT EXISTS idx_contacts_favorite ON contacts(is_favorite);
                CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(first_name, last_name);
                CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company);
                CREATE INDEX IF NOT EXISTS idx_contacts_updated ON contacts(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_interactions_contact ON interaction_log(contact_id);
                CREATE INDEX IF NOT EXISTS idx_interactions_date ON interaction_log(date DESC);
            """)

            # Create FTS5 virtual table
            try:
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS contacts_fts USING fts5(
                        first_name, last_name, nickname, company, job_title,
                        email, phone, mobile, notes, tags,
                        content='contacts', content_rowid='rowid'
                    )
                """)
            except sqlite3.OperationalError:
                pass  # Already exists

            # Create triggers for FTS sync
            for trigger_sql in [
                """CREATE TRIGGER IF NOT EXISTS contacts_ai AFTER INSERT ON contacts BEGIN
                    INSERT INTO contacts_fts(rowid, first_name, last_name, nickname, company, job_title, email, phone, mobile, notes, tags)
                    VALUES (new.rowid, new.first_name, new.last_name, new.nickname, new.company, new.job_title, new.email, new.phone, new.mobile, new.notes, new.tags);
                END""",
                """CREATE TRIGGER IF NOT EXISTS contacts_ad AFTER DELETE ON contacts BEGIN
                    INSERT INTO contacts_fts(contacts_fts, rowid, first_name, last_name, nickname, company, job_title, email, phone, mobile, notes, tags)
                    VALUES ('delete', old.rowid, old.first_name, old.last_name, old.nickname, old.company, old.job_title, old.email, old.phone, old.mobile, old.notes, old.tags);
                END""",
                """CREATE TRIGGER IF NOT EXISTS contacts_au AFTER UPDATE ON contacts BEGIN
                    INSERT INTO contacts_fts(contacts_fts, rowid, first_name, last_name, nickname, company, job_title, email, phone, mobile, notes, tags)
                    VALUES ('delete', old.rowid, old.first_name, old.last_name, old.nickname, old.company, old.job_title, old.email, old.phone, old.mobile, old.notes, old.tags);
                    INSERT INTO contacts_fts(rowid, first_name, last_name, nickname, company, job_title, email, phone, mobile, notes, tags)
                    VALUES (new.rowid, new.first_name, new.last_name, new.nickname, new.company, new.job_title, new.email, new.phone, new.mobile, new.notes, new.tags);
                END""",
            ]:
                try:
                    conn.execute(trigger_sql)
                except sqlite3.OperationalError:
                    pass

            # Insert default categories
            now = time.time()
            defaults = [
                ("personal", "Personal", "#6366f1", "user", 0),
                ("work", "Trabajo", "#f59e0b", "briefcase", 1),
                ("client", "Cliente", "#10b981", "dollar-sign", 2),
                ("provider", "Proveedor", "#3b82f6", "truck", 3),
                ("partner", "Partner", "#8b5cf6", "handshake", 4),
                ("lead", "Lead", "#ef4444", "target", 5),
                ("family", "Familia", "#ec4899", "heart", 6),
                ("friend", "Amigo", "#14b8a6", "smile", 7),
            ]
            for cat_id, name, color, icon, order in defaults:
                conn.execute(
                    "INSERT OR IGNORE INTO categories (id, name, color, icon, sort_order, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (cat_id, name, color, icon, order, now),
                )
            conn.commit()
        finally:
            conn.close()

    # ── Contact CRUD ──────────────────────────────────────────

    def create_contact(self, data: dict[str, Any]) -> dict:
        now = time.time()
        contact_id = str(uuid.uuid4())[:8]
        data.setdefault("first_name", "")
        data.setdefault("last_name", "")

        if isinstance(data.get("tags"), list):
            data["tags"] = json.dumps(data["tags"])
        if isinstance(data.get("custom_fields"), dict):
            data["custom_fields"] = json.dumps(data["custom_fields"])
        if isinstance(data.get("interaction_history"), list):
            data["interaction_history"] = json.dumps(data["interaction_history"])

        fields = [
            "id", "first_name", "last_name", "nickname", "company", "job_title",
            "email", "email2", "phone", "phone2", "mobile",
            "address", "city", "state", "zip_code", "country",
            "website", "linkedin", "twitter", "github", "instagram", "facebook",
            "category", "tags", "notes", "photo_url", "is_favorite",
            "custom_fields", "interaction_history", "source",
            "created_at", "updated_at",
        ]
        values = {f: data.get(f, "") for f in fields}
        values["id"] = contact_id
        values["created_at"] = now
        values["updated_at"] = now
        values.setdefault("tags", "[]")
        values.setdefault("custom_fields", "{}")
        values.setdefault("interaction_history", "[]")
        values.setdefault("source", "manual")
        values.setdefault("is_favorite", 0)

        cols = ", ".join(values.keys())
        placeholders = ", ".join("?" for _ in values)

        conn = self._get_conn()
        try:
            conn.execute(f"INSERT INTO contacts ({cols}) VALUES ({placeholders})", list(values.values()))
            conn.commit()
            return self.get_contact(contact_id)
        finally:
            conn.close()

    def get_contact(self, contact_id: str) -> dict | None:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
            if not row:
                return None
            return self._row_to_dict(row)
        finally:
            conn.close()

    def update_contact(self, contact_id: str, data: dict[str, Any]) -> dict | None:
        existing = self.get_contact(contact_id)
        if not existing:
            return None

        if isinstance(data.get("tags"), list):
            data["tags"] = json.dumps(data["tags"])
        if isinstance(data.get("custom_fields"), dict):
            data["custom_fields"] = json.dumps(data["custom_fields"])
        if isinstance(data.get("interaction_history"), list):
            data["interaction_history"] = json.dumps(data["interaction_history"])

        data["updated_at"] = time.time()
        skip = {"id", "created_at"}
        sets = []
        vals = []
        for k, v in data.items():
            if k not in skip:
                sets.append(f"{k} = ?")
                vals.append(v)

        if not sets:
            return existing

        vals.append(contact_id)
        conn = self._get_conn()
        try:
            conn.execute(f"UPDATE contacts SET {', '.join(sets)} WHERE id = ?", vals)
            conn.commit()
            return self.get_contact(contact_id)
        finally:
            conn.close()

    def delete_contact(self, contact_id: str) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def list_contacts(
        self,
        category: str | None = None,
        favorite: bool | None = None,
        sort_by: str = "first_name",
        sort_dir: str = "ASC",
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        allowed_sorts = {"first_name", "last_name", "company", "updated_at", "created_at", "last_contacted", "category"}
        if sort_by not in allowed_sorts:
            sort_by = "first_name"
        if sort_dir.upper() not in ("ASC", "DESC"):
            sort_dir = "ASC"

        where = []
        params: list[Any] = []
        if category:
            where.append("category = ?")
            params.append(category)
        if favorite is not None:
            where.append("is_favorite = ?")
            params.append(1 if favorite else 0)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        params.extend([limit, offset])

        conn = self._get_conn()
        try:
            rows = conn.execute(
                f"SELECT * FROM contacts {where_sql} ORDER BY {sort_by} {sort_dir} LIMIT ? OFFSET ?",
                params,
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def search_contacts(self, query: str, limit: int = 50) -> list[dict]:
        """Full-text search across all indexed fields."""
        sanitized = _sanitize_fts(query)
        if sanitized == '""':
            return []

        conn = self._get_conn()
        try:
            # Try FTS5 first
            try:
                rows = conn.execute(
                    """SELECT c.* FROM contacts c
                       JOIN contacts_fts f ON c.rowid = f.rowid
                       WHERE contacts_fts MATCH ?
                       ORDER BY rank
                       LIMIT ?""",
                    (sanitized, limit),
                ).fetchall()
                if rows:
                    return [self._row_to_dict(r) for r in rows]
            except sqlite3.OperationalError:
                pass

            # Fallback to LIKE search
            like = f"%{query}%"
            rows = conn.execute(
                """SELECT * FROM contacts WHERE
                   first_name LIKE ? OR last_name LIKE ? OR nickname LIKE ? OR
                   company LIKE ? OR email LIKE ? OR phone LIKE ? OR
                   mobile LIKE ? OR notes LIKE ? OR tags LIKE ?
                   ORDER BY first_name LIMIT ?""",
                (like, like, like, like, like, like, like, like, like, limit),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_stats(self) -> dict:
        conn = self._get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
            favorites = conn.execute("SELECT COUNT(*) FROM contacts WHERE is_favorite = 1").fetchone()[0]
            by_category = {}
            for row in conn.execute("SELECT category, COUNT(*) as cnt FROM contacts GROUP BY category"):
                by_category[row[0]] = row[1]
            recent = conn.execute(
                "SELECT COUNT(*) FROM contacts WHERE created_at > ?", (time.time() - 604800,)
            ).fetchone()[0]
            return {
                "total": total,
                "favorites": favorites,
                "by_category": by_category,
                "added_this_week": recent,
            }
        finally:
            conn.close()

    # ── Categories ────────────────────────────────────────────

    def list_categories(self) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def create_category(self, name: str, color: str = "#6366f1", icon: str = "folder") -> dict:
        cat_id = name.lower().replace(" ", "_")[:20]
        now = time.time()
        conn = self._get_conn()
        try:
            max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM categories").fetchone()[0]
            conn.execute(
                "INSERT OR REPLACE INTO categories (id, name, color, icon, sort_order, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (cat_id, name, color, icon, max_order + 1, now),
            )
            conn.commit()
            return {"id": cat_id, "name": name, "color": color, "icon": icon}
        finally:
            conn.close()

    def delete_category(self, cat_id: str) -> bool:
        if cat_id in ("personal", "work"):
            return False
        conn = self._get_conn()
        try:
            conn.execute("UPDATE contacts SET category = 'personal' WHERE category = ?", (cat_id,))
            cursor = conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ── Interactions ──────────────────────────────────────────

    def add_interaction(self, contact_id: str, interaction_type: str, content: str, date: float | None = None) -> dict:
        int_id = str(uuid.uuid4())[:8]
        now = time.time()
        date = date or now
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO interaction_log (id, contact_id, type, content, date, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (int_id, contact_id, interaction_type, content, date, now),
            )
            conn.execute("UPDATE contacts SET last_contacted = ? WHERE id = ?", (date, contact_id))
            conn.commit()
            return {"id": int_id, "contact_id": contact_id, "type": interaction_type, "content": content, "date": date}
        finally:
            conn.close()

    def get_interactions(self, contact_id: str, limit: int = 50) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM interaction_log WHERE contact_id = ? ORDER BY date DESC LIMIT ?",
                (contact_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Import/Export ─────────────────────────────────────────

    def export_vcard(self, contact_id: str | None = None) -> str:
        """Export one or all contacts as vCard 3.0."""
        if contact_id:
            contacts = [self.get_contact(contact_id)]
            contacts = [c for c in contacts if c]
        else:
            contacts = self.list_contacts(limit=10000)

        vcards = []
        for c in contacts:
            lines = [
                "BEGIN:VCARD",
                "VERSION:3.0",
                f"N:{c['last_name']};{c['first_name']};;;",
                f"FN:{c['first_name']} {c['last_name']}".strip(),
            ]
            if c.get("nickname"):
                lines.append(f"NICKNAME:{c['nickname']}")
            if c.get("company"):
                lines.append(f"ORG:{c['company']}")
            if c.get("job_title"):
                lines.append(f"TITLE:{c['job_title']}")
            if c.get("email"):
                lines.append(f"EMAIL;TYPE=INTERNET:{c['email']}")
            if c.get("email2"):
                lines.append(f"EMAIL;TYPE=INTERNET:{c['email2']}")
            if c.get("phone"):
                lines.append(f"TEL;TYPE=WORK:{c['phone']}")
            if c.get("phone2"):
                lines.append(f"TEL;TYPE=HOME:{c['phone2']}")
            if c.get("mobile"):
                lines.append(f"TEL;TYPE=CELL:{c['mobile']}")
            if c.get("address") or c.get("city"):
                addr = f";;{c.get('address', '')};{c.get('city', '')};{c.get('state', '')};{c.get('zip_code', '')};{c.get('country', '')}"
                lines.append(f"ADR;TYPE=HOME:{addr}")
            if c.get("website"):
                lines.append(f"URL:{c['website']}")
            if c.get("notes"):
                lines.append(f"NOTE:{c['notes'][:500]}")
            tags = c.get("tags", [])
            if tags:
                lines.append(f"CATEGORIES:{','.join(tags) if isinstance(tags, list) else tags}")
            lines.append("END:VCARD")
            vcards.append("\r\n".join(lines))
        return "\r\n".join(vcards)

    def import_vcard(self, vcard_text: str) -> int:
        """Import vCard data. Returns number of contacts imported."""
        count = 0
        current: dict[str, Any] = {}
        for line in vcard_text.replace("\r\n ", "").replace("\r\n\t", "").split("\n"):
            line = line.strip()
            if line == "BEGIN:VCARD":
                current = {}
            elif line == "END:VCARD" and current:
                self.create_contact(current)
                count += 1
                current = {}
            elif ":" in line:
                key, _, value = line.partition(":")
                key_base = key.split(";")[0].upper()
                if key_base == "N":
                    parts = value.split(";")
                    current["last_name"] = parts[0] if len(parts) > 0 else ""
                    current["first_name"] = parts[1] if len(parts) > 1 else ""
                elif key_base == "FN" and not current.get("first_name"):
                    parts = value.split(" ", 1)
                    current["first_name"] = parts[0]
                    current["last_name"] = parts[1] if len(parts) > 1 else ""
                elif key_base == "NICKNAME":
                    current["nickname"] = value
                elif key_base == "ORG":
                    current["company"] = value.rstrip(";")
                elif key_base == "TITLE":
                    current["job_title"] = value
                elif key_base == "EMAIL":
                    if not current.get("email"):
                        current["email"] = value
                    else:
                        current["email2"] = value
                elif key_base == "TEL":
                    if "CELL" in key.upper():
                        current["mobile"] = value
                    elif not current.get("phone"):
                        current["phone"] = value
                    else:
                        current["phone2"] = value
                elif key_base == "ADR":
                    parts = value.split(";")
                    if len(parts) >= 3:
                        current["address"] = parts[2]
                    if len(parts) >= 4:
                        current["city"] = parts[3]
                    if len(parts) >= 5:
                        current["state"] = parts[4]
                    if len(parts) >= 6:
                        current["zip_code"] = parts[5]
                    if len(parts) >= 7:
                        current["country"] = parts[6]
                elif key_base == "URL":
                    current["website"] = value
                elif key_base == "NOTE":
                    current["notes"] = value
                elif key_base == "CATEGORIES":
                    current["tags"] = value.split(",")
        return count

    # ── Helpers ───────────────────────────────────────────────

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        for field in ("tags", "custom_fields", "interaction_history"):
            if field in d and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d

    def count_contacts(self, category: str | None = None) -> int:
        conn = self._get_conn()
        try:
            if category:
                return conn.execute("SELECT COUNT(*) FROM contacts WHERE category = ?", (category,)).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        finally:
            conn.close()
