"""Unit tests for Threads autoposter modules using mocked HTTP responses."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import autoposter  # noqa: E402
from content_queue import (  # noqa: E402
    load_posts,
    load_state,
    record_published_post,
    render_post,
    select_next_post,
)
from env_utils import load_env, update_env  # noqa: E402
from threads_client import ThreadsApiError, ThreadsClient  # noqa: E402


class _FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._bytes = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._bytes

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeOpener(urllib.request.OpenerDirector):
    def __init__(self, handler) -> None:
        super().__init__()
        self._handler = handler
        self.calls: list[dict] = []

    def open(self, fullurl, data=None, timeout=None):  # type: ignore[override]
        req = fullurl
        parsed = urllib.parse.urlparse(req.full_url)
        query = urllib.parse.parse_qs(parsed.query)
        form = urllib.parse.parse_qs(req.data.decode("utf-8")) if req.data else {}
        call = {
            "method": req.get_method(),
            "path": parsed.path,
            "query": query,
            "form": form,
        }
        self.calls.append(call)
        return _FakeHTTPResponse(self._handler(call))


class TestEnvUtils(unittest.TestCase):
    def test_load_and_update_preserves_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("# comment\nPROMO_CODE=OLD\nOTHER=hello\n", encoding="utf-8")
            update_env(env_path, {"PROMO_CODE": "NEW123", "THREADS_USER_ID": "999"})
            loaded = load_env(env_path)
            self.assertEqual(loaded["PROMO_CODE"], "NEW123")
            self.assertEqual(loaded["OTHER"], "hello")
            self.assertEqual(loaded["THREADS_USER_ID"], "999")
            self.assertIn("# comment", env_path.read_text(encoding="utf-8"))


class TestContentQueue(unittest.TestCase):
    def test_bundled_posts_json_is_valid_within_500_chars(self) -> None:
        posts = load_posts(PROJECT_DIR / "posts.json")
        self.assertGreaterEqual(len(posts), 60)
        sample_promo = "FREEDOM2026TEST"
        organic_count = 0
        longer_count = 0
        for item in posts:
            rendered = render_post(
                item,
                promo_code=sample_promo,
                allow_placeholder=False,
                image_base_url="https://example.com/repo",
            )
            self.assertLessEqual(len(rendered.main_text), 500, rendered.post_id)
            has_promo_placeholder = any("{PROMO_CODE}" in r for r in item.get("replies", []))
            if not has_promo_placeholder:
                organic_count += 1
            if len(rendered.reply_texts) >= 2:
                longer_count += 1
            for reply in rendered.reply_texts:
                self.assertLessEqual(len(reply), 500, rendered.post_id)
                self.assertNotIn("{PROMO_CODE}", reply)
            if has_promo_placeholder:
                self.assertTrue(any(sample_promo in r for r in rendered.reply_texts), rendered.post_id)
            if item.get("image"):
                self.assertTrue((PROJECT_DIR / item["image"]).exists(), item["image"])
                self.assertEqual(rendered.image_url, f"https://example.com/repo/{item['image']}")
        self.assertGreaterEqual(organic_count, 5)
        self.assertGreaterEqual(longer_count, 10)

    def test_image_falls_back_to_none_without_base_url(self) -> None:
        raw = {"id": "img1", "image": "assets/card-10k-to-6k.jpg", "main": "Hello", "replies": []}
        rendered = render_post(raw, promo_code="CODE1", image_base_url="")
        self.assertIsNone(rendered.image_url)
        self.assertEqual(rendered.image_path, "assets/card-10k-to-6k.jpg")

    def test_unconfigured_promo_blocked_unless_dry_run(self) -> None:
        raw = {"id": "p1", "main": "Hello", "replies": ["Code: {PROMO_CODE}"]}
        with self.assertRaises(ValueError):
            render_post(raw, promo_code="YOUR_PROMO_CODE", allow_placeholder=False)
        dry = render_post(raw, promo_code="YOUR_PROMO_CODE", allow_placeholder=True)
        self.assertIn("{PROMO_CODE}", dry.reply_texts[0])

    def test_queue_selection_and_looping(self) -> None:
        posts = [
            {"id": "p1", "main": "One", "replies": []},
            {"id": "p2", "main": "Two", "replies": []},
        ]
        state = {"posted": {}, "history": []}

        first = select_next_post(posts, state, loop_queue=False)
        self.assertEqual(first["id"], "p1")
        record_published_post(state, "p1", ["101"], now=datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc))

        second = select_next_post(posts, state, loop_queue=False)
        self.assertEqual(second["id"], "p2")
        record_published_post(state, "p2", ["102"], now=datetime(2026, 11, 25, 11, 0, tzinfo=timezone.utc))

        self.assertIsNone(select_next_post(posts, state, loop_queue=False))
        looped = select_next_post(posts, state, loop_queue=True)
        self.assertEqual(looped["id"], "p1")


class TestThreadsClient(unittest.TestCase):
    def test_publish_thread_creates_polls_and_publishes_with_reply(self) -> None:
        seq = {"container": 0}

        def handler(call: dict) -> dict:
            path = call["path"]
            if path.endswith("/threads"):
                seq["container"] += 1
                return {"id": f"cont_{seq['container']}"}
            if "/cont_" in path:
                return {"status": "FINISHED"}
            if path.endswith("/threads_publish"):
                cid = call["form"]["creation_id"][0]
                return {"id": f"pub_{cid}"}
            raise AssertionError(f"Unexpected call: {call}")

        opener = _FakeOpener(handler)
        client = ThreadsClient(access_token="tok_123", opener=opener)
        ids = client.publish_thread(
            user_id="user_42",
            main_text="Главный пост",
            reply_texts=["Коммент с кодом CODE1"],
            reply_delay_sec=0.0,
            poll_interval_sec=0.0,
        )
        self.assertEqual(ids, ["pub_cont_1", "pub_cont_2"])
        create_calls = [c for c in opener.calls if c["path"].endswith("/threads")]
        self.assertEqual(len(create_calls), 2)
        self.assertNotIn("reply_to_id", create_calls[0]["form"])
        self.assertEqual(create_calls[1]["form"]["reply_to_id"], ["pub_cont_1"])

    def test_publish_thread_with_image_root_and_text_reply(self) -> None:
        seq = {"container": 0}

        def handler(call: dict) -> dict:
            path = call["path"]
            if path.endswith("/threads"):
                seq["container"] += 1
                return {"id": f"cont_{seq['container']}"}
            if "/cont_" in path:
                return {"status": "FINISHED"}
            if path.endswith("/threads_publish"):
                cid = call["form"]["creation_id"][0]
                return {"id": f"pub_{cid}"}
            raise AssertionError(f"Unexpected call: {call}")

        opener = _FakeOpener(handler)
        client = ThreadsClient(access_token="tok_123", opener=opener)
        ids = client.publish_thread(
            user_id="user_42",
            main_text="Пост с картинкой",
            reply_texts=["Коммент"],
            media_type="IMAGE",
            image_url="https://example.com/assets/card.jpg",
            reply_delay_sec=0.0,
            poll_interval_sec=0.0,
        )
        self.assertEqual(ids, ["pub_cont_1", "pub_cont_2"])
        create_calls = [c for c in opener.calls if c["path"].endswith("/threads")]
        self.assertEqual(create_calls[0]["form"]["media_type"], ["IMAGE"])
        self.assertEqual(create_calls[0]["form"]["image_url"], ["https://example.com/assets/card.jpg"])
        self.assertEqual(create_calls[1]["form"]["media_type"], ["TEXT"])

    def test_container_error_raises_threads_api_error(self) -> None:
        def handler(call: dict) -> dict:
            if call["path"].endswith("/threads"):
                return {"id": "cont_bad"}
            return {"status": "ERROR", "error_message": "INVALID_ASPEC_RATIO"}

        opener = _FakeOpener(handler)
        client = ThreadsClient(access_token="tok_123", opener=opener)
        with self.assertRaises(ThreadsApiError):
            client.publish_post(user_id="user_42", text="Test", poll_interval_sec=0.0)

    def test_token_exchange_and_auto_refresh(self) -> None:
        def handler(call: dict) -> dict:
            if call["path"] == "/access_token":
                return {"access_token": "long_tok_1", "expires_in": 5184000}
            if call["path"] == "/refresh_access_token":
                return {"access_token": "long_tok_2", "expires_in": 5184000}
            raise AssertionError(f"Unexpected call: {call}")

        opener = _FakeOpener(handler)
        client = ThreadsClient(access_token="long_tok_1", opener=opener)
        exchanged = client.exchange_short_lived_token("short_1", "sec_1")
        self.assertEqual(exchanged["access_token"], "long_tok_1")

        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            old_ts = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
            update_env(
                env_path,
                {
                    "THREADS_ACCESS_TOKEN": "long_tok_1",
                    "THREADS_TOKEN_UPDATED_AT": old_ts,
                },
            )
            env = load_env(env_path)
            logger = autoposter._configure_logging(Path(tmp) / "test.log")
            try:
                updated_env = autoposter.maybe_auto_refresh_token(env_path, env, client, logger)
            finally:
                for h in list(logger.handlers):
                    h.close()
                    logger.removeHandler(h)

            self.assertEqual(updated_env["THREADS_ACCESS_TOKEN"], "long_tok_2")
            self.assertEqual(load_env(env_path)["THREADS_ACCESS_TOKEN"], "long_tok_2")


class TestCliDryRun(unittest.TestCase):
    def test_cli_check_and_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_path = tmp_path / ".env"
            state_path = tmp_path / "state.json"
            log_path = tmp_path / "autoposter.log"
            env_path.write_text("PROMO_CODE=DEMO777\n", encoding="utf-8")

            rc_check = autoposter.main(
                [
                    "--env",
                    str(env_path),
                    "--posts",
                    str(PROJECT_DIR / "posts.json"),
                    "--state",
                    str(state_path),
                    "--log",
                    str(log_path),
                    "check",
                ]
            )
            self.assertEqual(rc_check, 0)

            rc_dry = autoposter.main(
                [
                    "--env",
                    str(env_path),
                    "--posts",
                    str(PROJECT_DIR / "posts.json"),
                    "--state",
                    str(state_path),
                    "--log",
                    str(log_path),
                    "post-next",
                    "--dry-run",
                ]
            )
            self.assertEqual(rc_dry, 0)
            self.assertEqual(load_state(state_path)["history"], [])


if __name__ == "__main__":
    unittest.main()
