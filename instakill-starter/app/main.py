from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.search import router as search_router
from app.db.database import init_db
from app.db.repository import PostReader, SqlitePostRepository
from app.search.encoder import SentenceTransformerEncoder, TextEncoder
from app.services.search import build_index


def create_app(
    encoder: TextEncoder | None = None,
    repository: PostReader | None = None,
) -> FastAPI:
    """Wire the application. Tests pass fakes; production uses SQLite + the pretrained encoder."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        app.state.encoder = encoder or SentenceTransformerEncoder()
        # The in-memory search index is built once here, at startup.
        app.state.search_index = build_index(repository or SqlitePostRepository(), app.state.encoder)
        yield

    app = FastAPI(title="InstaKill", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    register_error_handlers(app)
    app.include_router(search_router)
    return app


app = create_app()
