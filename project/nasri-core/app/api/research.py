from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthSession, require_roles
from app.schemas.research import ResearchItem, ResearchQueryRequest, ResearchQueryResponse
from app.services.research import ResearchError, run_research

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/query", response_model=ResearchQueryResponse)
async def research_query(
    body: ResearchQueryRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> ResearchQueryResponse:
    try:
        items, report_path = await run_research(
            query=body.query,
            max_results=body.max_results,
            save_report=body.save_report,
        )
    except ResearchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ResearchQueryResponse(
        query=body.query,
        item_count=len(items),
        items=[
            ResearchItem(
                title=i.title,
                url=i.url,
                source=i.source,
                summary=i.summary,
            )
            for i in items
        ],
        report_path=report_path,
    )
