"""Arquivo principal da aplicação FastAPI para o fut_manager_app_api."""

from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def hello_world():
    """Retorna a mensagem inicial da API."""
    return {"message": "Hello World"}
