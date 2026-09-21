"""Arquivo principal da aplicação FastAPI para o fut_manager_app_api."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from api_crud_generate_libary.routers.router import Router

from src.configs.settings import settings
from src.configs.db_connection import engine
from src.databases.scripts.create_schema import create_schema
from src.models import CRUD_MODELS


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Inicializa recursos configurados para o ciclo de vida da aplicação."""
    if settings.create_schema_on_startup:
        await create_schema()
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

@app.get("/")
def hello_world():
    """Retorna a mensagem inicial da API."""
    return {"message": "Hello World"}

for crud_model in CRUD_MODELS:
    router_options = {
        key: value for key, value in crud_model.items() if key not in {"prefix", "tags"}
    }
    app.include_router(
        Router(**router_options).router,
        prefix=crud_model["prefix"],
        tags=crud_model["tags"],
    )
