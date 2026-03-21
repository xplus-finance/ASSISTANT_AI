"""Pydantic models for XPlus Contacts API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ContactCreate(BaseModel):
    first_name: str = ""
    last_name: str = ""
    nickname: str = ""
    company: str = ""
    job_title: str = ""
    email: str = ""
    email2: str = ""
    phone: str = ""
    phone2: str = ""
    mobile: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    country: str = ""
    website: str = ""
    linkedin: str = ""
    twitter: str = ""
    github: str = ""
    instagram: str = ""
    facebook: str = ""
    category: str = "personal"
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    photo_url: str = ""
    is_favorite: bool = False
    custom_fields: dict[str, str] = Field(default_factory=dict)
    source: str = "manual"


class ContactUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    nickname: str | None = None
    company: str | None = None
    job_title: str | None = None
    email: str | None = None
    email2: str | None = None
    phone: str | None = None
    phone2: str | None = None
    mobile: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    country: str | None = None
    website: str | None = None
    linkedin: str | None = None
    twitter: str | None = None
    github: str | None = None
    instagram: str | None = None
    facebook: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    photo_url: str | None = None
    is_favorite: bool | None = None
    custom_fields: dict[str, str] | None = None


class CategoryCreate(BaseModel):
    name: str
    color: str = "#6366f1"
    icon: str = "folder"


class InteractionCreate(BaseModel):
    type: str = "note"
    content: str
    date: float | None = None
