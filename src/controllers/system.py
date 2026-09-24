from src.schemas.system import HealthResponse


def hello_world() -> HealthResponse:
    return HealthResponse(message="Hello World")
