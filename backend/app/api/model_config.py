from __future__ import annotations

from collections.abc import Callable, Generator

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlmodel import Session

from app.core.crypto import SecretCipher
from app.core.security import create_get_current_user
from app.model_config_schemas import (
    CustomModelUpsert,
    CustomModelView,
    ModelConfigView,
    PreferencesPayload,
    PreferencesView,
    ProviderUpsert,
    ProviderView,
    QuickSwitchPayload,
    UsageSummary,
)
from app.models import User
from app.services import model_config_service as service
from app.services.ai_gateway_client import AiGatewayClient

SessionDependency = Callable[[], Generator[Session, None, None]]
PROVIDER_ID_PATTERN = r"^[a-z0-9][a-z0-9._-]{0,63}$"


def _cipher(request: Request) -> SecretCipher:
    return request.app.state.model_cipher


def _gateway(request: Request) -> AiGatewayClient:
    return request.app.state.ai_gateway_client


def create_model_config_router(session_dependency: SessionDependency) -> APIRouter:  # noqa: C901
    router = APIRouter(prefix="/api/model-config", tags=["model-config"])
    get_current_user = create_get_current_user(session_dependency)

    def _invalidate(request: Request, user_uid: str) -> None:
        _gateway(request).invalidate_user_model_config(user_uid)

    @router.get("", response_model=ModelConfigView)
    def get_model_config(
        request: Request,
        user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> ModelConfigView:
        return service.get_config_view(session, user.uid, _cipher(request))

    @router.put("/providers/{provider_id}", response_model=ProviderView)
    def put_provider(
        request: Request,
        payload: ProviderUpsert,
        provider_id: str = Path(pattern=PROVIDER_ID_PATTERN),
        user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> ProviderView:
        cipher = _cipher(request)
        row = service.upsert_provider(session, user.uid, provider_id, payload, cipher)
        _invalidate(request, user.uid)
        return service.provider_view(row, cipher)

    @router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
    def remove_provider(
        request: Request,
        provider_id: str = Path(pattern=PROVIDER_ID_PATTERN),
        user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> None:
        if not service.delete_provider(session, user.uid, provider_id):
            raise HTTPException(status_code=404, detail="Provider 不存在")
        _invalidate(request, user.uid)

    @router.put("/custom-models", response_model=CustomModelView)
    def put_custom_model(
        request: Request,
        payload: CustomModelUpsert,
        user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> CustomModelView:
        row = service.upsert_custom_model(session, user.uid, payload)
        _invalidate(request, user.uid)
        return service.custom_model_view(row)

    @router.delete(
        "/custom-models/{model_row_id}", status_code=status.HTTP_204_NO_CONTENT
    )
    def remove_custom_model(
        request: Request,
        model_row_id: str,
        user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> None:
        if not service.delete_custom_model(session, user.uid, model_row_id):
            raise HTTPException(status_code=404, detail="自定义模型不存在")
        _invalidate(request, user.uid)

    @router.put("/preferences", response_model=PreferencesView)
    def put_preferences(
        request: Request,
        payload: PreferencesPayload,
        user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> PreferencesView:
        service.validate_preferences(session, user, payload, _gateway(request))
        row = service.save_preferences(session, user.uid, payload)
        _invalidate(request, user.uid)
        return service._preferences_view(row)

    @router.patch("/quick-switch", response_model=PreferencesView)
    def patch_quick_switch(
        request: Request,
        payload: QuickSwitchPayload,
        user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> PreferencesView:
        row = service.apply_quick_switch(session, user, payload, _gateway(request))
        _invalidate(request, user.uid)
        return service._preferences_view(row)

    @router.get("/usage", response_model=UsageSummary)
    def get_usage(
        days: int = Query(default=30, ge=1, le=365),
        user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> UsageSummary:
        return service.usage_summary(session, user.uid, days)

    return router
