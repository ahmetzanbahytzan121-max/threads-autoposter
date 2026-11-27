"""Queue management, validation, and posting history state for Threads posts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from threads_client import MAX_TEXT_LENGTH


PROMO_PLACEHOLDER = "{PROMO_CODE}"
UNCONFIGURED_PROMOS = {"", "YOUR_PROMO_CODE", "ТВОЙ_ПРОМОКОД", "CHANGE_ME"}


@dataclass(frozen=True)
class RenderedPost:
    """A validated post ready to be published to Threads."""

    post_id: str
    category: str
    main_text: str
    reply_texts: list[str]
    image_url: str | None = None
    image_path: str | None = None
    topic_tag: str | None = None


def _render_text(template: str, promo_code: str, allow_placeholder: bool) -> str:
    if PROMO_PLACEHOLDER in template:
        if not promo_code or promo_code in UNCONFIGURED_PROMOS:
            if not allow_placeholder:
                raise ValueError(
                    "PROMO_CODE in .env is not configured yet. Set your real Freedom promo code first."
                )
            return template
        return template.replace(PROMO_PLACEHOLDER, promo_code)
    return template


def load_posts(posts_path: Path) -> list[dict[str, Any]]:
    """Load and structurally validate post entries from posts.json."""
    if not posts_path.exists():
        raise FileNotFoundError(f"Posts file not found: {posts_path}")
    data = json.loads(posts_path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("posts.json must be a non-empty JSON array.")

    seen_ids: set[str] = set()
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Post at index {idx} must be a JSON object.")
        post_id = str(item.get("id", "")).strip()
        if not post_id:
            raise ValueError(f"Post at index {idx} is missing a non-empty 'id'.")
        if post_id in seen_ids:
            raise ValueError(f"Duplicate post id '{post_id}' in posts.json.")
        seen_ids.add(post_id)

        main = item.get("main")
        if not isinstance(main, str) or not main.strip():
            raise ValueError(f"Post '{post_id}' is missing a non-empty 'main' string.")
        replies = item.get("replies", [])
        if not isinstance(replies, list) or any(not isinstance(r, str) for r in replies):
            raise ValueError(f"Post '{post_id}' has invalid 'replies' (must be list of strings).")
        for field in ("image", "image_url", "topic_tag"):
            val = item.get(field)
            if val is not None and not isinstance(val, str):
                raise ValueError(f"Post '{post_id}' has invalid '{field}' (must be string).")

    return data


def render_post(
    raw_post: dict[str, Any],
    promo_code: str,
    allow_placeholder: bool = False,
    image_base_url: str = "",
) -> RenderedPost:
    """Substitute PROMO_CODE, resolve optional image URL, and enforce character limits."""
    post_id = str(raw_post["id"]).strip()
    category = str(raw_post.get("category", "general")).strip()
    main_text = _render_text(raw_post["main"], promo_code, allow_placeholder).strip()
    reply_texts = [
        _render_text(reply, promo_code, allow_placeholder).strip()
        for reply in raw_post.get("replies", [])
        if reply.strip()
    ]

    if len(main_text) > MAX_TEXT_LENGTH:
        raise ValueError(
            f"Post '{post_id}' main text exceeds {MAX_TEXT_LENGTH} chars ({len(main_text)})."
        )
    for i, reply_text in enumerate(reply_texts, start=1):
        if len(reply_text) > MAX_TEXT_LENGTH:
            raise ValueError(
                f"Post '{post_id}' reply #{i} exceeds {MAX_TEXT_LENGTH} chars ({len(reply_text)})."
            )

    raw_image_url = str(raw_post.get("image_url") or "").strip()
    raw_image_path = str(raw_post.get("image") or "").strip()
    resolved_image_url: str | None = None
    if raw_image_url:
        resolved_image_url = raw_image_url
    elif raw_image_path and image_base_url.strip():
        resolved_image_url = f"{image_base_url.strip().rstrip('/')}/{raw_image_path.lstrip('/')}"

    raw_topic_tag = str(raw_post.get("topic_tag") or "").strip()

    return RenderedPost(
        post_id=post_id,
        category=category,
        main_text=main_text,
        reply_texts=reply_texts,
        image_url=resolved_image_url,
        image_path=raw_image_path or None,
        topic_tag=raw_topic_tag or None,
    )


def load_state(state_path: Path) -> dict[str, Any]:
    """Load posting history state from disk."""
    if not state_path.exists():
        return {"posted": {}, "history": []}
    data = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"posted": {}, "history": []}
    data.setdefault("posted", {})
    data.setdefault("history", [])
    return data


def save_state(state_path: Path, state: dict[str, Any]) -> None:
    """Persist posting history state to disk."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def select_next_post(
    posts: list[dict[str, Any]],
    state: dict[str, Any],
    loop_queue: bool = False,
    target_id: str | None = None,
) -> dict[str, Any] | None:
    """Choose the next unposted item, or oldest-posted item when loop_queue=True."""
    if target_id is not None:
        for item in posts:
            if str(item["id"]) == target_id:
                return item
        raise ValueError(f"Post id '{target_id}' not found in posts.json.")

    posted_map: dict[str, Any] = state.get("posted", {})
    for item in posts:
        if str(item["id"]) not in posted_map:
            return item

    if not loop_queue:
        return None

    last_posted_id = state["history"][-1]["post_id"] if state.get("history") else None

    def _sort_key(item: dict[str, Any]) -> tuple[int, str, int]:
        pid = str(item["id"])
        meta = posted_map.get(pid, {})
        count = int(meta.get("count", 0))
        last_at = str(meta.get("last_posted_at", ""))
        avoid_immediate_repeat = 1 if (len(posts) > 1 and pid == last_posted_id) else 0
        return (avoid_immediate_repeat, count, last_at)

    return min(posts, key=_sort_key)


def record_published_post(
    state: dict[str, Any],
    post_id: str,
    published_ids: list[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Update state in memory after a post is published and return the updated state."""
    ts = (now or datetime.now(timezone.utc)).isoformat()
    posted_map = state.setdefault("posted", {})
    prev = posted_map.get(post_id, {})
    posted_map[post_id] = {
        "count": int(prev.get("count", 0)) + 1,
        "last_posted_at": ts,
        "last_published_ids": published_ids,
    }
    history = state.setdefault("history", [])
    history.append(
        {
            "post_id": post_id,
            "published_ids": published_ids,
            "posted_at": ts,
        }
    )
    # Keep recent history bounded to last 200 events.
    if len(history) > 200:
        state["history"] = history[-200:]
    return state
