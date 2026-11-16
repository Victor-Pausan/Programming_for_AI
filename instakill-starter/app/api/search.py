"""HTTP edge for search: parses query parameters and formats the response."""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.services.search import MAX_LIMIT, MIN_LIMIT, InvalidSearchError, search_posts

router = APIRouter()


class SearchResult(BaseModel):
    post_id: int
    user_id: int
    content: str
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


@router.get("/search", response_model=SearchResponse)
def search(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=500, description="Search text")],
    limit: Annotated[int, Query(ge=MIN_LIMIT, le=MAX_LIMIT)] = 10,
) -> SearchResponse:
    try:
        hits = search_posts(q, limit, request.app.state.search_index, request.app.state.encoder)
    except InvalidSearchError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_query", "message": str(exc)}
        ) from exc
    return SearchResponse(
        query=q,
        results=[
            SearchResult(
                post_id=hit.post.id,
                user_id=hit.post.user_id,
                content=hit.post.content,
                score=round(hit.score, 6),
            )
            for hit in hits
        ],
    )
