from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_key: str = "changeme"
    katago_binary: str = "/usr/local/bin/katago"
    katago_model: str = "/opt/katago/kata1-b18c384nbt-s9996604416-d4316597426.bin.gz"
    katago_config: str = "/opt/katago/analysis.cfg"
    max_queue_depth: int = 5
    visits_quick: int = 32
    visits_standard: int = 100
    visits_deep: int = 400
    allowed_origins: str = "*"

    model_config = {"env_file": ".env"}


settings = Settings()
