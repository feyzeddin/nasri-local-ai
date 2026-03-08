from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.core.redis import get_redis
from app.core.security import AuthSession, require_roles
from app.schemas.onboarding import (
    OnboardingAnswerRequest,
    OnboardingStartRequest,
    OnboardingStateResponse,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

_KEY_PREFIX = "onboarding"
_TTL_SECONDS = 60 * 60 * 24

_QUESTIONS = [
    "Sana nasıl hitap etmemi istersin?",
    "Nasri'yi en çok hangi amaçla kullanacaksın?",
    "Varsayılan çalışma tercihin nedir? (local-only / hybrid)",
]


def _key(session_id: str) -> str:
    return f"{_KEY_PREFIX}:{session_id}"


def _next_question(step: int) -> str | None:
    if step >= len(_QUESTIONS):
        return None
    return _QUESTIONS[step]


async def _load_state(session_id: str) -> dict | None:
    raw = await get_redis().get(_key(session_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def _save_state(session_id: str, state: dict) -> None:
    await get_redis().setex(
        _key(session_id),
        _TTL_SECONDS,
        json.dumps(state, ensure_ascii=False),
    )


def _to_response(session_id: str, state: dict) -> OnboardingStateResponse:
    step = int(state.get("step", 0))
    answers = state.get("answers", {})
    completed = step >= len(_QUESTIONS)
    return OnboardingStateResponse(
        session_id=session_id,
        step=step,
        total_steps=len(_QUESTIONS),
        completed=completed,
        next_question=_next_question(step),
        answers=answers,
    )


@router.post("/start", response_model=OnboardingStateResponse)
async def start_onboarding(
    body: OnboardingStartRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> OnboardingStateResponse:
    session_id = body.session_id or str(uuid.uuid4())
    existing = await _load_state(session_id)
    if existing is not None:
        return _to_response(session_id, existing)

    state = {"step": 0, "answers": {}}
    await _save_state(session_id, state)
    return _to_response(session_id, state)


@router.post("/answer", response_model=OnboardingStateResponse)
async def answer_onboarding(
    body: OnboardingAnswerRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> OnboardingStateResponse:
    state = await _load_state(body.session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Onboarding oturumu bulunamadı.")

    step = int(state.get("step", 0))
    if step >= len(_QUESTIONS):
        return _to_response(body.session_id, state)

    answers = dict(state.get("answers", {}))
    answers[f"q{step + 1}"] = body.answer.strip()
    new_state = {"step": step + 1, "answers": answers}
    await _save_state(body.session_id, new_state)
    return _to_response(body.session_id, new_state)


@router.get("/{session_id}", response_model=OnboardingStateResponse)
async def get_onboarding(
    session_id: str,
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> OnboardingStateResponse:
    state = await _load_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Onboarding oturumu bulunamadı.")
    return _to_response(session_id, state)

