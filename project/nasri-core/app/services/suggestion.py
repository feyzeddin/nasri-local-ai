from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.settings import get_settings
from app.services.memory import recall_memory


class SuggestionError(Exception):
    pass


@dataclass
class Suggestion:
    title: str
    reason: str
    priority: int


def _time_based_suggestions() -> list[Suggestion]:
    hour = datetime.now().hour
    items: list[Suggestion] = []
    if 6 <= hour < 11:
        items.append(
            Suggestion(
                title="Güne kısa bir planla başla",
                reason="Sabah saatleri odaklı görev planı için en uygun zaman.",
                priority=4,
            )
        )
    elif 11 <= hour < 18:
        items.append(
            Suggestion(
                title="Öncelikli işleri tamamla",
                reason="Gün ortasında enerji seviyesi yüksek, kritik işleri öne çek.",
                priority=4,
            )
        )
    else:
        items.append(
            Suggestion(
                title="Yarın için hazırlık yap",
                reason="Akşam saatlerinde bir sonraki günün planı verimi artırır.",
                priority=3,
            )
        )
    return items


def _memory_based_suggestions(profile_id: str) -> list[Suggestion]:
    items: list[Suggestion] = []
    try:
        memories = recall_memory(profile_id, "tercih alışkanlık plan hatırlat", top_k=3)
    except Exception:
        return items
    for m in memories:
        text = str(m.get("text", "")).strip()
        if not text:
            continue
        items.append(
            Suggestion(
                title="Alışkanlık bazlı öneri",
                reason=f"Geçmiş kayda göre: {text[:140]}",
                priority=5,
            )
        )
    return items


def generate_proactive_suggestions(profile_id: str) -> list[Suggestion]:
    s = get_settings()
    if not s.suggestion_enabled:
        raise SuggestionError("Proaktif öneri motoru devre dışı.")
    pid = profile_id.strip()
    if not pid:
        raise SuggestionError("profile_id boş olamaz.")

    items = _memory_based_suggestions(pid) + _time_based_suggestions()
    # Tekrarlı başlıkları azalt
    uniq: list[Suggestion] = []
    seen: set[str] = set()
    for it in sorted(items, key=lambda x: x.priority, reverse=True):
        key = it.title.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    return uniq[: max(1, s.suggestion_max_items)]
