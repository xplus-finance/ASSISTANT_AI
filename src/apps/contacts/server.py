"""aiohttp web server for XPlus Contacts."""
from __future__ import annotations

import json
import asyncio
from pathlib import Path

from aiohttp import web

from .database import ContactsDB

STATIC_DIR = Path(__file__).parent / "static"
db: ContactsDB | None = None


def get_db() -> ContactsDB:
    global db
    if db is None:
        db = ContactsDB()
    return db


# ── Contact endpoints ─────────────────────────────────────

async def list_contacts(request: web.Request) -> web.Response:
    category = request.query.get("category")
    favorite = request.query.get("favorite")
    sort_by = request.query.get("sort", "first_name")
    sort_dir = request.query.get("dir", "ASC")
    limit = int(request.query.get("limit", 500))
    offset = int(request.query.get("offset", 0))

    fav = None
    if favorite == "1":
        fav = True
    elif favorite == "0":
        fav = False

    contacts = await asyncio.to_thread(
        get_db().list_contacts, category, fav, sort_by, sort_dir, limit, offset
    )
    return web.json_response(contacts)


async def search_contacts(request: web.Request) -> web.Response:
    q = request.query.get("q", "")
    if not q:
        return web.json_response([])
    results = await asyncio.to_thread(get_db().search_contacts, q)
    return web.json_response(results)


async def get_contact(request: web.Request) -> web.Response:
    cid = request.match_info["id"]
    contact = await asyncio.to_thread(get_db().get_contact, cid)
    if not contact:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response(contact)


async def create_contact(request: web.Request) -> web.Response:
    data = await request.json()
    contact = await asyncio.to_thread(get_db().create_contact, data)
    return web.json_response(contact, status=201)


async def update_contact(request: web.Request) -> web.Response:
    cid = request.match_info["id"]
    data = await request.json()
    contact = await asyncio.to_thread(get_db().update_contact, cid, data)
    if not contact:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response(contact)


async def delete_contact(request: web.Request) -> web.Response:
    cid = request.match_info["id"]
    deleted = await asyncio.to_thread(get_db().delete_contact, cid)
    if not deleted:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response({"ok": True})


async def toggle_favorite(request: web.Request) -> web.Response:
    cid = request.match_info["id"]
    contact = await asyncio.to_thread(get_db().get_contact, cid)
    if not contact:
        return web.json_response({"error": "Not found"}, status=404)
    updated = await asyncio.to_thread(
        get_db().update_contact, cid, {"is_favorite": 0 if contact["is_favorite"] else 1}
    )
    return web.json_response(updated)


# ── Category endpoints ────────────────────────────────────

async def list_categories(request: web.Request) -> web.Response:
    cats = await asyncio.to_thread(get_db().list_categories)
    return web.json_response(cats)


async def create_category(request: web.Request) -> web.Response:
    data = await request.json()
    cat = await asyncio.to_thread(get_db().create_category, data["name"], data.get("color", "#6366f1"), data.get("icon", "folder"))
    return web.json_response(cat, status=201)


async def delete_category(request: web.Request) -> web.Response:
    cid = request.match_info["id"]
    ok = await asyncio.to_thread(get_db().delete_category, cid)
    if not ok:
        return web.json_response({"error": "Cannot delete"}, status=400)
    return web.json_response({"ok": True})


# ── Interactions ──────────────────────────────────────────

async def add_interaction(request: web.Request) -> web.Response:
    cid = request.match_info["id"]
    data = await request.json()
    interaction = await asyncio.to_thread(
        get_db().add_interaction, cid, data.get("type", "note"), data["content"], data.get("date")
    )
    return web.json_response(interaction, status=201)


async def get_interactions(request: web.Request) -> web.Response:
    cid = request.match_info["id"]
    interactions = await asyncio.to_thread(get_db().get_interactions, cid)
    return web.json_response(interactions)


# ── Import/Export ─────────────────────────────────────────

async def export_vcards(request: web.Request) -> web.Response:
    cid = request.query.get("id")
    vcard = await asyncio.to_thread(get_db().export_vcard, cid)
    return web.Response(
        text=vcard,
        content_type="text/vcard",
        headers={"Content-Disposition": "attachment; filename=contacts.vcf"},
    )


async def import_vcards(request: web.Request) -> web.Response:
    data = await request.text()
    count = await asyncio.to_thread(get_db().import_vcard, data)
    return web.json_response({"imported": count})


# ── Stats ─────────────────────────────────────────────────

async def get_stats(request: web.Request) -> web.Response:
    stats = await asyncio.to_thread(get_db().get_stats)
    return web.json_response(stats)


# ── Static files & index ─────────────────────────────────

async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


# ── App factory ───────────────────────────────────────────

def create_app() -> web.Application:
    app = web.Application()

    # API routes
    app.router.add_get("/api/contacts", list_contacts)
    app.router.add_get("/api/contacts/search", search_contacts)
    app.router.add_get("/api/contacts/export", export_vcards)
    app.router.add_post("/api/contacts/import", import_vcards)
    app.router.add_get("/api/contacts/stats", get_stats)
    app.router.add_post("/api/contacts", create_contact)
    app.router.add_get("/api/contacts/{id}", get_contact)
    app.router.add_put("/api/contacts/{id}", update_contact)
    app.router.add_delete("/api/contacts/{id}", delete_contact)
    app.router.add_post("/api/contacts/{id}/favorite", toggle_favorite)
    app.router.add_post("/api/contacts/{id}/interactions", add_interaction)
    app.router.add_get("/api/contacts/{id}/interactions", get_interactions)
    app.router.add_get("/api/categories", list_categories)
    app.router.add_post("/api/categories", create_category)
    app.router.add_delete("/api/categories/{id}", delete_category)

    # Static files
    app.router.add_static("/static", STATIC_DIR)
    app.router.add_get("/", index)

    return app


def run_server(host: str = "127.0.0.1", port: int = 8767):
    """Start the contacts server."""
    app = create_app()
    print(f"🗂️  XPlus Contacts running at http://{host}:{port}")
    web.run_app(app, host=host, port=port, print=None)


if __name__ == "__main__":
    run_server()
