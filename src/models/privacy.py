"""Tipos SQLAlchemy para persistir dados pessoais cifrados."""
import json
from sqlalchemy.types import TypeDecorator, Text
from src.helpers.privacy import PREFIX, cipher


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return PREFIX + cipher().encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None or not value.startswith(PREFIX):
            return value  # Compatibilidade apenas durante o backfill controlado.
        return cipher().decrypt(value[len(PREFIX):].encode()).decode()


class EncryptedJSON(EncryptedText):
    def process_bind_param(self, value, dialect):
        return super().process_bind_param(json.dumps(value, ensure_ascii=False) if value is not None else None, dialect)

    def process_result_value(self, value, dialect):
        if isinstance(value, (dict, list)):
            return value
        plain = super().process_result_value(value, dialect)
        return json.loads(plain) if plain is not None else None
