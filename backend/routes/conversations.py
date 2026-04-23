"""Conversation history CRUD."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import chat_store

router = APIRouter()


class ConvCreate(BaseModel):
    title: str | None = None


class ConvPatch(BaseModel):
    title: str


@router.get("/conversations")
def list_convs() -> list[dict]:
    return chat_store.list_conversations()


@router.post("/conversations")
def create_conv(body: ConvCreate) -> dict:
    return chat_store.create_conversation((body.title or "").strip())


@router.get("/conversations/{cid}")
def get_conv(cid: str) -> dict:
    c = chat_store.get_conversation(cid)
    if not c:
        raise HTTPException(404, "conversation not found")
    return c


@router.patch("/conversations/{cid}")
def rename_conv(cid: str, body: ConvPatch) -> dict:
    c = chat_store.rename_conversation(cid, body.title.strip())
    if not c:
        raise HTTPException(404, "conversation not found")
    return c


@router.delete("/conversations/{cid}")
def delete_conv(cid: str) -> dict:
    if not chat_store.delete_conversation(cid):
        raise HTTPException(404, "conversation not found")
    return {"ok": True}
