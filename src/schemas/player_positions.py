"""Catálogo compartilhado com o app e validação das preferências do jogador."""

from typing import Annotated
from pydantic import AfterValidator
from pydantic_core import PydanticCustomError

MODALITIES = {
    "campo": {
        "label": "Futebol de Campo",
        "positions": {
            "goleiro": "Goleiro",
            "zagueiro": "Zagueiro",
            "lateral_direito": "Lateral direito",
            "lateral_esquerdo": "Lateral esquerdo",
            "volante": "Volante",
            "meia": "Meia",
            "atacante": "Atacante",
        },
    },
    "futsal": {
        "label": "Futsal",
        "positions": {
            "goleiro": "Goleiro",
            "fixo": "Fixo",
            "ala_direita": "Ala direita",
            "ala_esquerda": "Ala esquerda",
            "pivo": "Pivô",
        },
    },
    "fut7": {
        "label": "Fut7",
        "positions": {
            "goleiro": "Goleiro",
            "fixo": "Fixo",
            "ala_direita": "Ala direita",
            "ala_esquerda": "Ala esquerda",
            "meia": "Meia",
            "pivo": "Pivô",
        },
    },
}


def validate_positions(value):
    if not value:
        raise PydanticCustomError(
            "positions_invalid", "Escolha pelo menos uma posição em uma modalidade."
        )
    for sport, positions in value.items():
        if sport not in MODALITIES:
            raise PydanticCustomError("positions_invalid", "Modalidade inválida.")
        if not positions or any(
            (p not in MODALITIES[sport]["positions"] for p in positions)
        ):
            raise PydanticCustomError(
                "positions_invalid",
                "Escolha posições válidas para cada modalidade selecionada.",
            )
        if len(set(positions)) != len(positions):
            raise PydanticCustomError(
                "positions_invalid", "Não repita posições na mesma modalidade."
            )
    return value


PlayerPositions = Annotated[dict[str, list[str]], AfterValidator(validate_positions)]
