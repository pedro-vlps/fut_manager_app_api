from fastapi import APIRouter
from src.controllers import system as controller
from src.schemas.system import HealthResponse

router = APIRouter()


@router.get("/", response_model=HealthResponse)
def hello_world():
    return controller.hello_world()
