from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    typesafe_api_key: SecretStr
    typesafe_model: str = "jev-latest"
    typesafe_url: str = "https://api.typesafe.ai/v1/systemone"
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str = "openrouter/free"
    openrouter_url: str = "https://openrouter.ai/api/v1/chat/completions"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
