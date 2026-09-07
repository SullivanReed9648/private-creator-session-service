from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from .infrai_client import InfraiClient, InfraiError
from .session_store import ServerSession, SessionStore


class SignupRequest(BaseModel):
    widget_record_id: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=12)
    name: str = Field(min_length=1, max_length=80)
    captcha_token: str = Field(min_length=1)
    request_id: UUID


class LoginRequest(BaseModel):
    user_id: str = Field(min_length=1)


class ProcessingState(StrEnum):
    RECEIVED = "received"
    READY = "ready"


class AssetRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    subscriber_updates: bool = False


class AssetView(BaseModel):
    asset_id: str
    title: str
    processing: ProcessingState
    subscriber_updates: bool


@dataclass
class AssetRecord:
    asset_id: str
    owner_id: str
    title: str
    processing: ProcessingState
    subscriber_updates: bool


class AssetCatalog:
    def __init__(self) -> None:
        self._assets: dict[str, AssetRecord] = {}

    def submit(self, owner_id: str, request: AssetRequest) -> AssetRecord:
        record = AssetRecord(
            asset_id=str(uuid4()),
            owner_id=owner_id,
            title=request.title,
            processing=ProcessingState.RECEIVED,
            subscriber_updates=request.subscriber_updates,
        )
        self._assets[record.asset_id] = record
        return record

    def mark_ready(self, asset_id: str, owner_id: str) -> AssetRecord | None:
        record = self._assets.get(asset_id)
        if not record or record.owner_id != owner_id:
            return None
        record.processing = ProcessingState.READY
        return record

    def delivery(self, asset_id: str, owner_id: str) -> AssetRecord | None:
        record = self._assets.get(asset_id)
        if not record or record.owner_id != owner_id:
            return None
        if record.processing is not ProcessingState.READY:
            return None
        return record


def create_app(
    infrai: InfraiClient | None = None,
    sessions: SessionStore | None = None,
    assets: AssetCatalog | None = None,
) -> FastAPI:
    app = FastAPI(title="Private creator delivery")
    app.state.infrai = infrai
    app.state.sessions = sessions or SessionStore()
    app.state.assets = assets or AssetCatalog()

    def client() -> InfraiClient:
        if app.state.infrai is None:
            app.state.infrai = InfraiClient()
        return app.state.infrai

    def current_session(
        creator_session: str | None = Cookie(default=None),
    ) -> ServerSession:
        session = app.state.sessions.resolve(creator_session)
        if session is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required")
        return session

    def map_infrai_error(exc: InfraiError) -> HTTPException:
        client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        return HTTPException(
            status_code=client_status,
            detail={"code": exc.code, "message": str(exc)},
        )

    @app.post("/signup", status_code=status.HTTP_201_CREATED)
    def signup(payload: SignupRequest, request: Request) -> dict[str, str]:
        try:
            client().verify_captcha(
                payload.captcha_token,
                request.client.host if request.client else None,
                widget_record_id=payload.widget_record_id,
            )
            user = client().create_user(
                str(payload.email), payload.password, payload.name, str(payload.request_id)
            )
        except InfraiError as exc:
            raise map_infrai_error(exc) from exc
        return {"user_id": str(user["id"]), "status": "created"}

    @app.post("/login")
    def login(payload: LoginRequest, response: Response) -> dict[str, str]:
        try:
            upstream = client().create_session(payload.user_id)
        except InfraiError as exc:
            raise map_infrai_error(exc) from exc
        session_key = app.state.sessions.issue(payload.user_id, str(upstream["id"]))
        response.set_cookie(
            "creator_session",
            session_key,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=8 * 60 * 60,
        )
        return {"status": "authenticated"}

    @app.post("/assets", response_model=AssetView, status_code=status.HTTP_202_ACCEPTED)
    def submit_asset(
        payload: AssetRequest, session: ServerSession = Depends(current_session)
    ) -> AssetRecord:
        return app.state.assets.submit(session.user_id, payload)

    @app.post("/assets/{asset_id}/ready", response_model=AssetView)
    def mark_asset_ready(
        asset_id: str, session: ServerSession = Depends(current_session)
    ) -> AssetRecord:
        record = app.state.assets.mark_ready(asset_id, session.user_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        return record

    @app.get("/assets/{asset_id}/delivery", response_model=AssetView)
    def get_delivery(
        asset_id: str, session: ServerSession = Depends(current_session)
    ) -> AssetRecord:
        record = app.state.assets.delivery(asset_id, session.user_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Ready asset not found")
        return record

    return app


@lru_cache
def application() -> FastAPI:
    return create_app()


app = application()
