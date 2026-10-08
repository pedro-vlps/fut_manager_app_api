"""Arquivo principal da aplicação FastAPI para o fut_manager_app_api."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api_crud_generate_libary.routers.router import Router

from src.configs.settings import settings
from src.configs.db_connection import engine
from src.databases.scripts.create_schema import create_schema
from src.models import CRUD_MODELS
from src.routers.auth import router as auth_router
from src.routers.groups import router as groups_router
from src.routers.lifecycle import router as lifecycle_router
from src.routers.event_write_guard import event_write_guard
from src.routers.system import router as system_router
from src.routers.group_requests import router as group_requests_router
from src.routers.seasons import router as seasons_router
from src.routers.trophies import router as trophies_router
from src.routers.scheduling import router as scheduling_router
from src.routers.draw import router as draw_router
from src.routers.championships import router as championships_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Inicializa recursos configurados para o ciclo de vida da aplicação."""
    if settings.create_schema_on_startup:
        await create_schema()
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


app.include_router(system_router)
app.include_router(auth_router)
app.include_router(groups_router)
app.include_router(group_requests_router)
app.include_router(seasons_router)
app.include_router(trophies_router)
app.include_router(scheduling_router)
app.include_router(draw_router)
app.include_router(championships_router)
app.include_router(lifecycle_router)

for crud_model in CRUD_MODELS:
    router_options = {
        key: value for key, value in crud_model.items() if key not in {"prefix", "tags"}
    }
    app.include_router(
        Router(**router_options).router,
        prefix=crud_model["prefix"],
        tags=crud_model["tags"],
        dependencies=[Depends(event_write_guard(crud_model["model_class"]))],
    )
