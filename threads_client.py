"""Minimal zero-dependency client for the official Meta Threads Graph API."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_API_BASE = "https://graph.threads.net/v1.0"
DEFAULT_TOKEN_BASE = "https://graph.threads.net"
MAX_TEXT_LENGTH = 500


class ThreadsApiError(RuntimeError):
    """Raised when the Threads Graph API returns an error or times out."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: int | None = None,
        error_subcode: int | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.error_subcode = error_subcode
        self.raw_payload = raw_payload or {}


class ThreadsClient:
    """Client for Meta Threads publishing and token management endpoints."""

    def __init__(
        self,
        access_token: str | None = None,
        api_base: str = DEFAULT_API_BASE,
        token_base: str = DEFAULT_TOKEN_BASE,
        timeout_sec: float = 30.0,
        opener: urllib.request.OpenerDirector | None = None,
    ) -> None:
        self.access_token = access_token.strip() if access_token else None
        self.api_base = api_base.rstrip("/")
        self.token_base = token_base.rstrip("/")
        self.timeout_sec = timeout_sec
        self._opener = opener

    def _request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if params:
            clean_params = {k: v for k, v in params.items() if v is not None}
            query = urllib.parse.urlencode(clean_params)
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{query}"

        body_bytes: bytes | None = None
        headers = {"Accept": "application/json"}
        if form_data is not None:
            clean_form = {k: v for k, v in form_data.items() if v is not None}
            body_bytes = urllib.parse.urlencode(clean_form).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        req = urllib.request.Request(url=url, data=body_bytes, headers=headers, method=method)
        try:
            open_fn = self._opener.open if self._opener is not None else urllib.request.urlopen
            with open_fn(req, timeout=self.timeout_sec) as resp:
                raw_text = resp.read().decode("utf-8")
                return json.loads(raw_text) if raw_text else {}
        except urllib.error.HTTPError as exc:
            raw_body = exc.read().decode("utf-8", errors="replace")
            payload: dict[str, Any] = {}
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError:
                pass
            err_obj = payload.get("error", {}) if isinstance(payload, dict) else {}
            err_msg = err_obj.get("message") or raw_body or str(exc)
            raise ThreadsApiError(
                f"Threads API HTTP {exc.code}: {err_msg}",
                status_code=exc.code,
                error_code=err_obj.get("code"),
                error_subcode=err_obj.get("error_subcode"),
                raw_payload=payload,
            ) from exc
        except urllib.error.URLError as exc:
            raise ThreadsApiError(f"Network error calling Threads API: {exc.reason}") from exc

    def _require_token(self) -> str:
        if not self.access_token:
            raise ThreadsApiError("THREADS_ACCESS_TOKEN is not set.")
        return self.access_token

    def get_me(self) -> dict[str, Any]:
        """Return id, username, and name for the authenticated Threads user."""
        token = self._require_token()
        return self._request(
            "GET",
            f"{self.api_base}/me",
            params={"fields": "id,username,name", "access_token": token},
        )

    def exchange_short_lived_token(self, short_lived_token: str, app_secret: str) -> dict[str, Any]:
        """Exchange a 1-hour short-lived token for a 60-day long-lived token."""
        if not short_lived_token.strip():
            raise ValueError("short_lived_token must not be empty")
        if not app_secret.strip():
            raise ValueError("app_secret must not be empty")
        return self._request(
            "GET",
            f"{self.token_base}/access_token",
            params={
                "grant_type": "th_exchange_token",
                "client_secret": app_secret.strip(),
                "access_token": short_lived_token.strip(),
            },
        )

    def refresh_long_lived_token(self, long_lived_token: str | None = None) -> dict[str, Any]:
        """Refresh a non-expired long-lived token (>= 24h old) for another 60 days."""
        token = (long_lived_token or self._require_token()).strip()
        return self._request(
            "GET",
            f"{self.token_base}/refresh_access_token",
            params={
                "grant_type": "th_refresh_token",
                "access_token": token,
            },
        )

    def create_container(
        self,
        user_id: str,
        media_type: str = "TEXT",
        text: str | None = None,
        image_url: str | None = None,
        video_url: str | None = None,
        reply_to_id: str | None = None,
    ) -> str:
        """Create a Threads media container and return its container ID."""
        token = self._require_token()
        media_type_upper = media_type.upper()
        if text is not None and len(text) > MAX_TEXT_LENGTH:
            raise ValueError(
                f"Post text exceeds {MAX_TEXT_LENGTH} characters ({len(text)} given)."
            )
        if media_type_upper == "TEXT" and not (text and text.strip()):
            raise ValueError("TEXT container requires non-empty text.")
        if media_type_upper == "IMAGE" and not image_url:
            raise ValueError("IMAGE container requires image_url.")
        if media_type_upper == "VIDEO" and not video_url:
            raise ValueError("VIDEO container requires video_url.")

        form: dict[str, Any] = {
            "media_type": media_type_upper,
            "access_token": token,
        }
        if text is not None:
            form["text"] = text
        if image_url is not None:
            form["image_url"] = image_url
        if video_url is not None:
            form["video_url"] = video_url
        if reply_to_id is not None:
            form["reply_to_id"] = reply_to_id

        data = self._request("POST", f"{self.api_base}/{user_id}/threads", form_data=form)
        container_id = data.get("id")
        if not container_id:
            raise ThreadsApiError(f"Container creation returned no id: {data}", raw_payload=data)
        return str(container_id)

    def get_container_status(self, container_id: str) -> dict[str, Any]:
        """Fetch container processing status and optional error_message."""
        token = self._require_token()
        return self._request(
            "GET",
            f"{self.api_base}/{container_id}",
            params={"fields": "status,error_message", "access_token": token},
        )

    def wait_for_container(
        self,
        container_id: str,
        timeout_sec: float = 60.0,
        poll_interval_sec: float = 2.0,
    ) -> str:
        """Poll a container until it is FINISHED or PUBLISHED."""
        deadline = time.monotonic() + timeout_sec
        while True:
            info = self.get_container_status(container_id)
            status = str(info.get("status", "")).upper()
            if status in ("FINISHED", "PUBLISHED"):
                return status
            if status in ("ERROR", "EXPIRED"):
                err_detail = info.get("error_message") or "unknown error"
                raise ThreadsApiError(
                    f"Container {container_id} failed with status {status}: {err_detail}",
                    raw_payload=info,
                )
            if time.monotonic() >= deadline:
                raise ThreadsApiError(
                    f"Timed out waiting for container {container_id} (last status={status or 'UNKNOWN'}).",
                    raw_payload=info,
                )
            time.sleep(poll_interval_sec)

    def publish_container(self, user_id: str, creation_id: str) -> str:
        """Publish a finished container and return the published Threads post ID."""
        token = self._require_token()
        data = self._request(
            "POST",
            f"{self.api_base}/{user_id}/threads_publish",
            form_data={"creation_id": creation_id, "access_token": token},
        )
        post_id = data.get("id")
        if not post_id:
            raise ThreadsApiError(f"Publish returned no id: {data}", raw_payload=data)
        return str(post_id)

    def publish_post(
        self,
        user_id: str,
        text: str | None = None,
        media_type: str = "TEXT",
        image_url: str | None = None,
        video_url: str | None = None,
        reply_to_id: str | None = None,
        wait_timeout_sec: float = 60.0,
        poll_interval_sec: float = 2.0,
    ) -> str:
        """Create, wait for processing, and publish a single Threads post or reply."""
        container_id = self.create_container(
            user_id=user_id,
            media_type=media_type,
            text=text,
            image_url=image_url,
            video_url=video_url,
            reply_to_id=reply_to_id,
        )
        status = self.wait_for_container(
            container_id,
            timeout_sec=wait_timeout_sec,
            poll_interval_sec=poll_interval_sec,
        )
        if status == "PUBLISHED":
            return container_id
        return self.publish_container(user_id=user_id, creation_id=container_id)

    def publish_thread(
        self,
        user_id: str,
        main_text: str,
        reply_texts: list[str] | None = None,
        media_type: str = "TEXT",
        image_url: str | None = None,
        video_url: str | None = None,
        reply_delay_sec: float = 3.0,
        wait_timeout_sec: float = 60.0,
        poll_interval_sec: float = 2.0,
    ) -> list[str]:
        """Publish a root post (TEXT/IMAGE/VIDEO) followed by optional chained replies."""
        published_ids: list[str] = []
        root_id = self.publish_post(
            user_id=user_id,
            text=main_text,
            media_type=media_type,
            image_url=image_url,
            video_url=video_url,
            wait_timeout_sec=wait_timeout_sec,
            poll_interval_sec=poll_interval_sec,
        )
        published_ids.append(root_id)

        parent_id = root_id
        for reply_text in reply_texts or []:
            if not reply_text.strip():
                continue
            if reply_delay_sec > 0:
                time.sleep(reply_delay_sec)
            reply_id = self.publish_post(
                user_id=user_id,
                text=reply_text,
                reply_to_id=parent_id,
                wait_timeout_sec=wait_timeout_sec,
                poll_interval_sec=poll_interval_sec,
            )
            published_ids.append(reply_id)
            parent_id = reply_id

        return published_ids
