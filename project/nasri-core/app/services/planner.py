from __future__ import annotations

from dataclasses import dataclass

from app.core.settings import get_settings
from app.services.memory import recall_memory


@dataclass
class ReActStep:
    thought: str
    action: str
    action_input: str
    observation: str


class PlannerError(Exception):
    pass


def _normalize_goal(goal: str) -> str:
    return " ".join(goal.strip().split())


def _choose_actions(goal: str) -> list[tuple[str, str, str]]:
    g = goal.lower()
    actions: list[tuple[str, str, str]] = []

    # ReAct-style basit karar akışı
    actions.append(
        (
            "Hedefi netleştirmek için önce bağlamı çıkarıyorum.",
            "analyze_goal",
            goal,
        )
    )

    if any(k in g for k in ["hatırla", "remember", "profil", "kullanıcı", "geçmiş"]):
        actions.append(
            (
                "Geçmiş bilgileri kontrol etmeliyim.",
                "recall_memory",
                goal,
            )
        )

    if any(k in g for k in ["dosya", "file", "klasör", "ara"]):
        actions.append(
            (
                "Dosya işlemi gerektirdiği için file aracı kullanılmalı.",
                "prepare_file_tool",
                goal,
            )
        )

    if any(k in g for k in ["sohbet", "yanıt", "cevapla", "chat"]):
        actions.append(
            (
                "Kullanıcıya verilecek yanıtı taslaklamalıyım.",
                "draft_response",
                goal,
            )
        )

    actions.append(
        (
            "Son planı özetleyip tamamlayabilirim.",
            "finalize",
            goal,
        )
    )
    return actions


def run_planner(goal: str, profile_id: str | None = None) -> tuple[bool, str, list[ReActStep]]:
    normalized_goal = _normalize_goal(goal)
    if not normalized_goal:
        raise PlannerError("Hedef boş olamaz.")

    max_steps = get_settings().planner_max_steps
    actions = _choose_actions(normalized_goal)[:max_steps]

    steps: list[ReActStep] = []
    memory_hint = ""
    for thought, action, action_input in actions:
        if action == "analyze_goal":
            observation = f"Hedef: {normalized_goal}"
        elif action == "recall_memory":
            if profile_id:
                try:
                    hits = recall_memory(profile_id, normalized_goal, top_k=3)
                    if hits:
                        memory_hint = "; ".join(h["text"] for h in hits[:2])
                        observation = f"{len(hits)} bellek kaydı bulundu."
                    else:
                        observation = "Bellek kaydı bulunamadı."
                except Exception as exc:
                    observation = f"Bellek adımı atlandı: {exc}"
            else:
                observation = "profile_id olmadığı için bellek taraması atlandı."
        elif action == "prepare_file_tool":
            observation = "Dosya API endpointleriyle (list/search) eylem planı hazırlanmalı."
        elif action == "draft_response":
            observation = "Yanıt taslağı, chat endpointi ile oluşturulabilir."
        else:
            observation = "Plan sonlandırıldı."

        steps.append(
            ReActStep(
                thought=thought,
                action=action,
                action_input=action_input,
                observation=observation,
            )
        )

    summary = " -> ".join(step.action for step in steps)
    if memory_hint:
        summary += f" | memory_hint: {memory_hint}"
    completed = True
    return completed, summary, steps
