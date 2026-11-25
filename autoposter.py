"""CLI entrypoint for automated Threads posting and Meta token management."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from content_queue import (
    UNCONFIGURED_PROMOS,
    load_posts,
    load_state,
    record_published_post,
    render_post,
    save_state,
    select_next_post,
)
from env_utils import load_env, update_env
from threads_client import ThreadsApiError, ThreadsClient


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = BASE_DIR / ".env"
DEFAULT_POSTS_PATH = BASE_DIR / "posts.json"
DEFAULT_STATE_PATH = BASE_DIR / "state.json"
DEFAULT_LOG_PATH = BASE_DIR / "logs" / "autoposter.log"

AUTO_REFRESH_DAYS = 30
MIN_REFRESH_AGE_HOURS = 24


def _close_logging(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def _configure_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("threads_autoposter")
    logger.setLevel(logging.INFO)
    _close_logging(logger)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


def _parse_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "да"}


def _parse_float(raw: str | None, default: float) -> float:
    if not raw:
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


def _parse_iso_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def maybe_auto_refresh_token(
    env_path: Path,
    env: dict[str, str],
    client: ThreadsClient,
    logger: logging.Logger,
    now: datetime | None = None,
) -> dict[str, str]:
    """Refresh the long-lived token if it is at least AUTO_REFRESH_DAYS old."""
    current_now = now or datetime.now(timezone.utc)
    updated_at = _parse_iso_datetime(env.get("THREADS_TOKEN_UPDATED_AT"))
    if updated_at is None:
        return env
    if current_now - updated_at < timedelta(days=AUTO_REFRESH_DAYS):
        return env

    logger.info("Long-lived token is older than %d days; attempting automatic refresh.", AUTO_REFRESH_DAYS)
    try:
        resp = client.refresh_long_lived_token(env.get("THREADS_ACCESS_TOKEN"))
        new_token = resp.get("access_token")
        if new_token:
            client.access_token = str(new_token)
            updates = {
                "THREADS_ACCESS_TOKEN": str(new_token),
                "THREADS_TOKEN_UPDATED_AT": current_now.isoformat(),
            }
            update_env(env_path, updates)
            env = {**env, **updates}
            logger.info("Successfully refreshed long-lived Threads access token.")
    except ThreadsApiError as exc:
        logger.warning("Auto-refresh failed (continuing with existing token): %s", exc)
    return env


def cmd_setup_token(args: argparse.Namespace, env_path: Path, logger: logging.Logger) -> int:
    env = load_env(env_path)
    short_token = args.short_token or ""
    if not short_token:
        short_token = input(
            "Вставь токен из User Token Generator (кнопка «Копировать»): "
        ).strip()
    if not short_token:
        print("Ошибка: пустой токен.", file=sys.stderr)
        return 1

    app_secret = args.app_secret or env.get("THREADS_APP_SECRET", "").strip()
    if not app_secret and not args.no_exchange:
        app_secret = input(
            "Вставь Threads App Secret (или нажми Enter, чтобы сохранить токен напрямую): "
        ).strip()

    client = ThreadsClient()
    expires_in: object = "unknown"
    if app_secret and not args.no_exchange:
        logger.info("Exchanging token for 60-day long-lived token...")
        token_data = client.exchange_short_lived_token(short_token, app_secret)
        long_token = str(token_data.get("access_token", "")).strip()
        if not long_token:
            print(f"Ошибка: Meta API не вернул access_token: {token_data}", file=sys.stderr)
            return 1
        expires_in = token_data.get("expires_in", "unknown")
    else:
        long_token = short_token

    client.access_token = long_token
    me = client.get_me()
    user_id = str(me.get("id", "")).strip()
    username = str(me.get("username", "")).strip()
    now_iso = datetime.now(timezone.utc).isoformat()

    updates = {
        "THREADS_ACCESS_TOKEN": long_token,
        "THREADS_USER_ID": user_id,
        "THREADS_USERNAME": username,
        "THREADS_TOKEN_UPDATED_AT": now_iso,
    }
    if app_secret:
        updates["THREADS_APP_SECRET"] = app_secret
    update_env(env_path, updates)
    logger.info(
        "Token saved to %s for @%s (id=%s, expires_in=%s sec).",
        env_path,
        username or "?",
        user_id or "?",
        expires_in,
    )
    print(f"Готово! Подключён аккаунт @{username} (ID: {user_id}). Токен сохранён в {env_path}")
    return 0


def cmd_refresh_token(args: argparse.Namespace, env_path: Path, logger: logging.Logger) -> int:
    env = load_env(env_path)
    token = env.get("THREADS_ACCESS_TOKEN", "").strip()
    if not token:
        print("Ошибка: THREADS_ACCESS_TOKEN не задан в .env. Сначала запусти setup-token.", file=sys.stderr)
        return 1

    updated_at = _parse_iso_datetime(env.get("THREADS_TOKEN_UPDATED_AT"))
    now = datetime.now(timezone.utc)
    if updated_at and not args.force and (now - updated_at) < timedelta(hours=MIN_REFRESH_AGE_HOURS):
        print(
            "Токену меньше 24 часов — по правилам Meta его можно обновлять минимум через 24 часа "
            "(используй --force, если уверен)."
        )
        return 0

    client = ThreadsClient(access_token=token)
    resp = client.refresh_long_lived_token(token)
    new_token = str(resp.get("access_token", "")).strip()
    if not new_token:
        print(f"Ошибка обновления токена: {resp}", file=sys.stderr)
        return 1

    update_env(
        env_path,
        {
            "THREADS_ACCESS_TOKEN": new_token,
            "THREADS_TOKEN_UPDATED_AT": now.isoformat(),
        },
    )
    logger.info("Refreshed long-lived token (expires_in=%s).", resp.get("expires_in", "unknown"))
    print("Токен успешно продлён ещё на 60 дней.")
    return 0


def cmd_check(args: argparse.Namespace, env_path: Path, posts_path: Path) -> int:
    env = load_env(env_path)
    promo_code = env.get("PROMO_CODE", "").strip()
    image_base_url = env.get("IMAGE_BASE_URL", "").strip()
    posts = load_posts(posts_path)

    promo_ready = promo_code not in UNCONFIGURED_PROMOS
    image_posts = 0
    for raw in posts:
        rendered = render_post(
            raw,
            promo_code=promo_code,
            allow_placeholder=not promo_ready,
            image_base_url=image_base_url,
        )
        if rendered.image_path or rendered.image_url:
            image_posts += 1

    print(f"posts.json OK: {len(posts)} постов прошли проверку (<= 500 символов, с картинками: {image_posts}).")
    if image_base_url:
        print(f"IMAGE_BASE_URL: {image_base_url}")
    elif image_posts:
        print("IMAGE_BASE_URL: не задан (посты с картинками будут безопасно публиковаться как TEXT).")
    if promo_ready:
        print(f"PROMO_CODE: задан ({promo_code}).")
    else:
        print("PROMO_CODE: НЕ ЗАДАН (в .env пока заглушка — укажи реальный промокод из Freedom).")

    token = env.get("THREADS_ACCESS_TOKEN", "").strip()
    if not token:
        print("THREADS_ACCESS_TOKEN: не задан. Запусти setup-token после создания Meta App.")
        return 0

    client = ThreadsClient(access_token=token)
    try:
        me = client.get_me()
        print(f"Threads API OK: @{me.get('username')} (id={me.get('id')}).")
    except ThreadsApiError as exc:
        print(f"Threads API ошибка: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_status(env_path: Path, posts_path: Path, state_path: Path) -> int:
    env = load_env(env_path)
    posts = load_posts(posts_path)
    state = load_state(state_path)
    posted_map = state.get("posted", {})

    unposted_count = sum(1 for item in posts if str(item["id"]) not in posted_map)
    promo_code = env.get("PROMO_CODE", "").strip()
    username = env.get("THREADS_USERNAME", "").strip() or "(не подключён)"
    updated_at = _parse_iso_datetime(env.get("THREADS_TOKEN_UPDATED_AT"))
    token_age = (
        f"{(datetime.now(timezone.utc) - updated_at).days} дн."
        if updated_at is not None
        else "неизвестно"
    )

    print(f"Аккаунт Threads: @{username.lstrip('@')}")
    print(f"Промокод (.env): {promo_code or '(не задан)'}")
    print(f"Возраст токена: {token_age}")
    print(f"Всего постов в очереди: {len(posts)} | Неопубликовано: {unposted_count}")
    if state.get("history"):
        last = state["history"][-1]
        print(f"Последний пост: {last['post_id']} в {last['posted_at']} -> IDs {last['published_ids']}")
    else:
        print("Публикаций ещё не было.")
    return 0


def cmd_post_next(
    args: argparse.Namespace,
    env_path: Path,
    posts_path: Path,
    state_path: Path,
    logger: logging.Logger,
) -> int:
    env = load_env(env_path)
    posts = load_posts(posts_path)
    state = load_state(state_path)

    loop_queue = args.loop or _parse_bool(env.get("LOOP_QUEUE"), default=False)
    promo_code = env.get("PROMO_CODE", "").strip()
    image_base_url = env.get("IMAGE_BASE_URL", "").strip()

    raw_post = select_next_post(posts, state, loop_queue=loop_queue, target_id=args.id)
    if raw_post is None:
        logger.info("Queue exhausted (all %d posts already published and LOOP_QUEUE=false).", len(posts))
        print("Все посты из posts.json уже опубликованы. Включи LOOP_QUEUE=true в .env или добавь новые посты.")
        return 0

    rendered = render_post(
        raw_post,
        promo_code=promo_code,
        allow_placeholder=args.dry_run,
        image_base_url=image_base_url,
    )

    if args.dry_run:
        print(f"[DRY-RUN] Пост ID={rendered.post_id} (категория: {rendered.category})")
        if rendered.image_url:
            print(f"[IMAGE URL]: {rendered.image_url}")
        elif rendered.image_path:
            print(f"[IMAGE LOCAL]: {rendered.image_path} (без IMAGE_BASE_URL уйдёт как TEXT)")
        print("--- ОСНОВНОЙ ПОСТ ---")
        print(rendered.main_text)
        for idx, reply in enumerate(rendered.reply_texts, start=1):
            print(f"--- КОММЕНТАРИЙ #{idx} ---")
            print(reply)
        return 0

    token = env.get("THREADS_ACCESS_TOKEN", "").strip()
    if not token:
        print("Ошибка: THREADS_ACCESS_TOKEN не задан в .env.", file=sys.stderr)
        return 1

    client = ThreadsClient(access_token=token)
    env = maybe_auto_refresh_token(env_path, env, client, logger)

    user_id = env.get("THREADS_USER_ID", "").strip()
    if not user_id:
        me = client.get_me()
        user_id = str(me.get("id", "")).strip()
        if not user_id:
            print("Ошибка: не удалось определить THREADS_USER_ID через /me.", file=sys.stderr)
            return 1
        update_env(env_path, {"THREADS_USER_ID": user_id, "THREADS_USERNAME": str(me.get("username", ""))})

    reply_delay = _parse_float(env.get("REPLY_DELAY_SEC"), default=3.0)
    media_type = "IMAGE" if rendered.image_url else "TEXT"
    if rendered.image_path and not rendered.image_url:
        logger.info("IMAGE_BASE_URL not configured; posting '%s' as TEXT fallback.", rendered.post_id)
    logger.info(
        "Publishing post '%s' (%s, media=%s) for user_id=%s...",
        rendered.post_id,
        rendered.category,
        media_type,
        user_id,
    )
    published_ids = client.publish_thread(
        user_id=user_id,
        main_text=rendered.main_text,
        reply_texts=rendered.reply_texts,
        media_type=media_type,
        image_url=rendered.image_url,
        reply_delay_sec=reply_delay,
    )
    record_published_post(state, rendered.post_id, published_ids)
    save_state(state_path, state)
    logger.info("Published post '%s' -> Threads IDs: %s", rendered.post_id, published_ids)
    print(f"Успешно опубликовано: {rendered.post_id} (Threads IDs: {', '.join(published_ids)})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Threads Autoposter CLI for Meta Threads Graph API")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV_PATH, help="Path to .env file")
    parser.add_argument("--posts", type=Path, default=DEFAULT_POSTS_PATH, help="Path to posts.json")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH, help="Path to state.json")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG_PATH, help="Path to log file")

    sub = parser.add_subparsers(dest="command", required=True)

    p_setup = sub.add_parser("setup-token", help="Save or exchange a Threads token into .env")
    p_setup.add_argument("--short-token", default="", help="Token from Meta User Token Generator")
    p_setup.add_argument("--app-secret", default="", help="Optional Threads App Secret for token exchange")
    p_setup.add_argument("--no-exchange", action="store_true", help="Save token directly without th_exchange_token")

    p_refresh = sub.add_parser("refresh-token", help="Refresh 60-day long-lived token")
    p_refresh.add_argument("--force", action="store_true", help="Attempt refresh even if token is < 24h old")

    sub.add_parser("check", help="Validate .env, posts.json, and Threads API credentials")
    sub.add_parser("status", help="Show queue progress and token status")

    p_post = sub.add_parser("post-next", help="Publish the next queued post (and its reply)")
    p_post.add_argument("--dry-run", action="store_true", help="Preview next post without publishing")
    p_post.add_argument("--loop", action="store_true", help="Loop queue after all posts are published")
    p_post.add_argument("--id", default=None, help="Publish a specific post id from posts.json")

    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = build_parser()
    args = parser.parse_args(argv)
    logger = _configure_logging(args.log)

    try:
        if args.command == "setup-token":
            return cmd_setup_token(args, args.env, logger)
        if args.command == "refresh-token":
            return cmd_refresh_token(args, args.env, logger)
        if args.command == "check":
            return cmd_check(args, args.env, args.posts)
        if args.command == "status":
            return cmd_status(args.env, args.posts, args.state)
        if args.command == "post-next":
            return cmd_post_next(args, args.env, args.posts, args.state, logger)
    except (ThreadsApiError, ValueError, FileNotFoundError) as exc:
        logger.error("%s", exc)
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    finally:
        _close_logging(logger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
