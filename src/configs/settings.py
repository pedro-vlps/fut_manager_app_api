"""Configurações validadas da aplicação."""

from urllib.parse import quote

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações carregadas de variáveis `FUT_MANAGER_*` ou de um `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="FUT_MANAGER_",
        extra="ignore",
    )

    app_name: str
    debug: bool
    database_host: str = Field(min_length=1)
    database_port: int = Field(ge=1, le=65535)
    database_name: str = Field(min_length=1)
    database_user: str = Field(min_length=1)
    database_password: SecretStr
    database_echo: bool
    create_schema_on_startup: bool
    cors_origins: list[str] = Field(default_factory=list)

    @field_validator("database_host", "database_name", "database_user")
    @classmethod
    def strip_database_values(cls, value: str) -> str:
        """Evita parâmetros de conexão formados apenas por espaços."""
        value = value.strip()
        if not value:
            raise ValueError("não pode ser vazio")
        return value

    @property
    def database_url(self) -> str:
        """Monta a URL assíncrona a partir das variáveis individuais do banco."""
        user = quote(self.database_user, safe="")
        password = quote(self.database_password.get_secret_value(), safe="")
        database = quote(self.database_name, safe="")
        return (
            f"postgresql+asyncpg://{user}:{password}@{self.database_host}:"
            f"{self.database_port}/{database}"
        )


settings = Settings()
