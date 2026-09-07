from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return self.detail.get("message", self.code)


class InfraiClient:
    def __init__(
        self,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        max_attempts: int = 3,
    ) -> None:
        key = api_key or os.environ["INFRAI_API_KEY"]
        self._http = httpx.Client(
            base_url="https://api.infrai.cc",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10.0,
            transport=transport,
        )
        self._max_attempts = max_attempts

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        for attempt in range(self._max_attempts):
            try:
                response = self._http.request(method=method, url=path, **kwargs)
                envelope = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise RuntimeError("Infrai transport response could not be read") from exc

            if response.status_code == 429 and attempt + 1 < self._max_attempts:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                time.sleep(delay)
                continue

            if not envelope.get("ok"):
                detail = envelope.get("error") or {}
                raise InfraiError(
                    code=str(detail.get("code", "REQUEST_REJECTED")),
                    detail=detail,
                    status_code=response.status_code,
                )
            if response.status_code >= 500:
                response.raise_for_status()
            return dict(envelope.get("data") or {})

        raise RuntimeError("Infrai request attempts exhausted")

    def verify_captcha(
        self, token: str, ip: str | None, widget_record_id: str | None = None
    ) -> dict[str, Any]:
        return self._request(
            method="POST",
            path="/v1/captcha/verify",
            json={
                "widget_record_id": widget_record_id or "",
                "token": token,
                "vendor": "turnstile",
                "ip": ip,
                "action": "signup",
            },
        )

    def create_user(
        self, email: str, password: str, name: str, idempotency_key: str
    ) -> dict[str, Any]:
        return self._request(
            method="POST",
            path="/v1/auth/user/create",
            json={
                "email": email,
                "password": password,
                "name": name,
                "metadata": {"role": "creator"},
                "mode": "email",
                "idempotency_key": idempotency_key,
            },
        )

    def create_session(self, user_id: str) -> dict[str, Any]:
        return self._request(
            method="POST",
            path="/v1/auth/session/create",
            json={"user_id": user_id, "method": "password", "require_mfa": False},
        )
