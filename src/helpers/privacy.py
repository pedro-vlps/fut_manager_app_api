"""Criptografia autenticada em repouso e índice cego para busca de e-mail."""
import hashlib
import hmac
from cryptography.fernet import Fernet, MultiFernet
from src.configs.settings import settings

PREFIX = 'enc:v1:'


def cipher():
    keys = settings.personal_data_keys
    if not keys:
        raise RuntimeError('Configure FUT_MANAGER_PERSONAL_DATA_KEYS antes de persistir dados pessoais.')
    return MultiFernet([Fernet(key.get_secret_value().encode()) for key in keys])


def email_lookup(value):
    key = settings.email_lookup_key
    if key is None or len(key.get_secret_value()) < 32:
        raise RuntimeError('Configure FUT_MANAGER_EMAIL_LOOKUP_KEY com um segredo aleatório de pelo menos 32 caracteres.')
    return hmac.new(key.get_secret_value().encode(), value.strip().casefold().encode(), hashlib.sha256).hexdigest()
