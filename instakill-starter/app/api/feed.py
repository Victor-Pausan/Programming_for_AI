"""HTTP edge for the feed: parses query parameters, maps errors, formats JSON."""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.db.repository import SqliteFeedRepository
from app.services.feed import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    MIN_LIMIT,
    FeedStrategy,
    InvalidFeedRequestError,
    ModelUnavailableError,
    UserNotFoundError,
    get_feed,
)

router = APIRouter()


class FeedPost(BaseModel):
    post_id: int
    user_id: int
    content: str
    created_at: datetime
    score: float | None = None


class FeedResponse(BaseModel):
    user_id: int
    strategy: FeedStrategy
    posts: list[FeedPost]


@router.get("/feed", response_model=FeedResponse, response_model_exclude_none=True)
def feed(
    request: Request,
    user_id: Annotated[int, Query(description="The user whose feed is requested")],
    limit: Annotated[int, Query(ge=MIN_LIMIT, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    strategy: FeedStrategy = FeedStrategy.FOR_YOU,
) -> FeedResponse:
    repository = getattr(request.app.state, "feed_repository", None) or SqliteFeedRepository()
    try:
        page = get_feed(user_id, repository, now=request.app.state.clock(),
                        limit=limit, strategy=strategy,
                        like_model=getattr(request.app.state, "like_model", None))
    except UserNotFoundError as exc:
        raise HTTPException(404, detail={"code": "user_not_found", "message": str(exc)}) from exc
    except ModelUnavailableError as exc:
        raise HTTPException(503, detail={"code": "model_unavailable", "message": str(exc)}) from exc
    except InvalidFeedRequestError as exc:
        raise HTTPException(422, detail={"code": "invalid_feed_request", "message": str(exc)}) from exc
    return FeedResponse(
        user_id=page.user_id,
        strategy=page.strategy,
        posts=[
            FeedPost(
                post_id=item.post.id,
                user_id=item.post.user_id,
                content=item.post.content,
                created_at=item.post.created_at,
                score=None if item.score is None else round(item.score, 6),
            )
            for item in page.items
        ],
    )
