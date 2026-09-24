from fastapi import HTTPException


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Sessão inválida ou expirada. Entre novamente.",
        headers={"WWW-Authenticate": "Bearer"},
    )
