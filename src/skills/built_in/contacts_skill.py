"""Contacts skill — Firulais controls XPlus Contacts."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from ..base_skill import BaseSkill


class ContactsSkill(BaseSkill):
    """Manage contacts via commands or natural language."""

    @property
    def name(self) -> str:
        return "contacts"

    @property
    def description(self) -> str:
        return "Gestión de contactos: crear, buscar, editar, eliminar, importar/exportar"

    @property
    def triggers(self) -> list[str]:
        return [
            "!contacto", "!contactos", "!contact", "!contacts",
            "contacto", "contactos", "agregar contacto", "buscar contacto",
            "nuevo contacto", "crear contacto", "eliminar contacto",
        ]

    async def execute(self, command: str, context: dict[str, Any] | None = None) -> str:
        """Handle contact commands."""
        from src.apps.contacts.database import ContactsDB
        db = ContactsDB()

        cmd = command.lower().strip()

        # Stats
        if any(w in cmd for w in ["stats", "estadísticas", "cuántos", "resumen"]):
            stats = await asyncio.to_thread(db.get_stats)
            lines = [
                f"📊 **Estadísticas de contactos:**",
                f"- Total: **{stats['total']}**",
                f"- Favoritos: **{stats['favorites']}**",
                f"- Agregados esta semana: **{stats['added_this_week']}**",
            ]
            if stats['by_category']:
                lines.append("- Por categoría:")
                for cat, count in stats['by_category'].items():
                    lines.append(f"  - {cat}: {count}")
            return "\n".join(lines)

        # Search
        if any(w in cmd for w in ["buscar", "busca", "search", "encuentra", "find"]):
            query = cmd
            for w in ["!contactos", "!contacto", "!contacts", "!contact", "buscar", "busca", "search", "find", "encuentra"]:
                query = query.replace(w, "")
            query = query.strip()
            if not query:
                return "¿Qué contacto quieres buscar?"
            results = await asyncio.to_thread(db.search_contacts, query)
            if not results:
                return f"No encontré contactos con '{query}'"
            lines = [f"🔍 **{len(results)} resultado(s) para '{query}':**"]
            for c in results[:10]:
                name = f"{c['first_name']} {c['last_name']}".strip()
                info = c.get('company') or c.get('email') or c.get('phone') or ''
                fav = "⭐" if c.get('is_favorite') else ""
                lines.append(f"- {fav} **{name}** ({info}) [ID: {c['id']}]")
            if len(results) > 10:
                lines.append(f"... y {len(results) - 10} más")
            return "\n".join(lines)

        # List
        if any(w in cmd for w in ["lista", "listar", "list", "todos", "all", "ver contactos"]):
            contacts = await asyncio.to_thread(db.list_contacts, limit=20)
            if not contacts:
                return "📇 No hay contactos aún. Abre http://localhost:8767 para empezar."
            lines = [f"📇 **{len(contacts)} contactos (mostrando hasta 20):**"]
            for c in contacts:
                name = f"{c['first_name']} {c['last_name']}".strip()
                info = c.get('company') or c.get('email') or ''
                fav = "⭐" if c.get('is_favorite') else ""
                lines.append(f"- {fav} **{name}** — {info} [{c['category']}]")
            return "\n".join(lines)

        # Create from natural language (basic)
        if any(w in cmd for w in ["agregar", "crear", "nuevo", "add", "create", "new"]):
            # Try to parse "agregar contacto Juan Pérez email@test.com"
            parts = cmd
            for w in ["!contactos", "!contacto", "agregar", "crear", "nuevo", "contacto", "add", "create", "new", "contact"]:
                parts = parts.replace(w, "")
            parts = parts.strip()
            if not parts:
                return "Abre http://localhost:8767 y presiona N para crear un contacto con todos los detalles."

            # Simple name parsing
            words = parts.split()
            data: dict[str, Any] = {}
            data["first_name"] = words[0] if words else ""
            data["last_name"] = " ".join(words[1:]) if len(words) > 1 else ""

            # Check for email in words
            for w in words:
                if "@" in w:
                    data["email"] = w
                    if w == data.get("first_name"):
                        data["first_name"] = w.split("@")[0]
                    elif w in data.get("last_name", ""):
                        data["last_name"] = data["last_name"].replace(w, "").strip()

            contact = await asyncio.to_thread(db.create_contact, data)
            name = f"{contact['first_name']} {contact['last_name']}".strip()
            return f"✅ Contacto **{name}** creado (ID: {contact['id']}). Edítalo en http://localhost:8767"

        # Delete
        if any(w in cmd for w in ["eliminar", "borrar", "delete", "remove"]):
            parts = cmd
            for w in ["!contactos", "!contacto", "eliminar", "borrar", "delete", "remove", "contacto", "contact"]:
                parts = parts.replace(w, "")
            cid = parts.strip()
            if not cid:
                return "Necesito el ID del contacto. Busca primero con: buscar contacto [nombre]"
            deleted = await asyncio.to_thread(db.delete_contact, cid)
            return f"✅ Contacto eliminado." if deleted else f"❌ No encontré contacto con ID '{cid}'"

        # Default — show help
        return (
            "📇 **XPlus Contacts** — http://localhost:8767\n\n"
            "Comandos disponibles:\n"
            "- `buscar [nombre/email/empresa]` — Buscar contactos\n"
            "- `listar` — Ver todos los contactos\n"
            "- `agregar [nombre]` — Crear contacto rápido\n"
            "- `eliminar [id]` — Eliminar contacto\n"
            "- `estadísticas` — Ver resumen\n\n"
            "O abre la app web completa: **http://localhost:8767**"
        )
