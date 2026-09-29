from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://enterprise:enterprise@localhost:5439/enterprise_assistant"
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    chroma_host: str = "localhost"
    chroma_port: int = 8025

    # "development" allows default JWT secret; "production" refuses to start with it.
    environment: str = "development"
    # Demo account password — was hardcoded; now overridable via env.
    demo_password: str = "demo1234"
    # Use LLM-based task decomposer; falls back to keyword routing when Ollama unavailable.
    use_llm_decomposer: bool = True
    # Cap user request text to prevent prompt-flooding and abuse.
    max_request_length: int = 2000
    # Requests per minute per IP on the /api/requests POST endpoint.
    rate_limit_requests_per_minute: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


settings = Settings()
