from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.feed import router as feed_router
from app.api.search import router as search_router
from app.db.database import init_db
from app.db.repository import FeedReader, PostReader, SqlitePostRepository
from app.ml.like_model import DEFAULT_MODEL_PATH, LikeModel, load_like_model
from app.search.encoder import SentenceTransformerEncoder, TextEncoder
from app.services.search import build_index


def utc_now() -> datetime:
    return datetime.now(UTC)


def create_app(
    encoder: TextEncoder | None = None,
    repository: PostReader | None = None,
    feed_repository: FeedReader | None = None,
    clock: Callable[[], datetime] = utc_now,
    like_model: LikeModel | None = None,
) -> FastAPI:
    """Wire the application. Tests pass fakes; production uses SQLite + the pretrained encoder."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        app.state.encoder = encoder or SentenceTransformerEncoder()
        # The in-memory search index is built once here, at startup.
        app.state.search_index = build_index(repository or SqlitePostRepository(), app.state.encoder)
        # The Lab 05 like model is loaded once, at startup (strategy=learned answers 503 without it).
        if like_model is not None:
            app.state.like_model = like_model
        elif DEFAULT_MODEL_PATH.exists():
            app.state.like_model = load_like_model(DEFAULT_MODEL_PATH)
        else:
            app.state.like_model = None
        yield

    app = FastAPI(title="InstaKill", lifespan=lifespan)
    app.state.clock = clock  # the only place the feed gets "now" from
    app.state.feed_repository = feed_repository  # None -> SqliteFeedRepository per request

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    register_error_handlers(app)
    app.include_router(search_router)
    app.include_router(feed_router)
    return app


app = create_app()
