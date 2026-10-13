"""Critérios de senha nova, sem restringir o login de contas legadas."""
from unicodedata import category


def missing_password_requirements(password: str) -> list[str]:
    categories = [category(char) for char in password]
    checks = (
        (8 <= len(password) <= 128, 'de 8 a 128 caracteres'),
        ('Lu' in categories, 'uma letra maiúscula'),
        ('Ll' in categories, 'uma letra minúscula'),
        ('Nd' in categories, 'um número'),
        (any(kind[0] in ('P', 'S') for kind in categories), 'um caractere especial'),
    )
    return [label for satisfied, label in checks if not satisfied]
