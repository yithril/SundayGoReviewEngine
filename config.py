from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_key: str = "changeme"
    katago_binary: str = "/usr/local/bin/katago"
    katago_model: str = "/opt/katago/kata1-b18c384nbt-s9996604416-d4316597426.bin.gz"
    katago_human_model: str = "/opt/katago/b18c384nbt-humanv0.bin.gz"
    katago_config: str = "/opt/katago/analysis.cfg"
    katago_config_fast: str | None = None  # for /suggest; falls back to katago_config
    katago_config_slow: str | None = None  # for /analyze worker; falls back to katago_config
    katago_max_concurrent: int = 4
    max_queue_depth: int = 30
    visits_quick: int = 32
    visits_standard: int = 100
    visits_deep: int = 400
    allowed_origins: str = "*"

    model_config = {"env_file": ".env"}


settings = Settings()
