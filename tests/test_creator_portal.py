from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from creator_service.creator_portal import AssetCatalog, AssetRequest, ProcessingState, create_app
from creator_service.infrai_client import InfraiClient, InfraiError
from creator_service.session_store import SessionStore


def test_delivery_waits_for_processing_and_enforces_owner() -> None:
    catalog = AssetCatalog()
    asset = catalog.submit("creator-7", AssetRequest(title="Recovery journal", subscriber_updates=True))

    assert catalog.delivery(asset.asset_id, "creator-7") is None
    assert catalog.mark_ready(asset.asset_id, "another-creator") is None

    ready = catalog.mark_ready(asset.asset_id, "creator-7")
    assert ready is not None
    assert ready.processing is ProcessingState.READY
    assert catalog.delivery(asset.asset_id, "creator-7") is ready


def test_business_rejection_is_decoded_before_http_status() -> None:
    def reject(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "ok": False,
                "data": None,
                "error": {"code": "VERIFICATION_DECLINED", "message": "Verification declined"},
                "metadata": {},
            },
        )

    client = InfraiClient(api_key="test-key", transport=httpx.MockTransport(reject))
    try:
        client.verify_captcha("browser-proof", "127.0.0.1")
    except InfraiError as exc:
        assert exc.status_code == 422
        assert exc.code == "VERIFICATION_DECLINED"
    else:
        raise AssertionError("expected a typed business rejection")
    finally:
        client.close()


def test_authenticated_asset_request_uses_server_session() -> None:
    sessions = SessionStore()
    key = sessions.issue("creator-7", "upstream-session-4")
    web = TestClient(create_app(sessions=sessions), base_url="https://testserver")
    web.cookies.set("creator_session", key)

    response = web.post(
        "/assets", json={"title": "Recovery journal", "subscriber_updates": True}
    )

    assert response.status_code == 202
    assert response.json()["processing"] == "received"
