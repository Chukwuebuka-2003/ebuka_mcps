from pydantic import Field
from pydantic_settings import BaseSettings
from urllib.parse import quote_plus


class Settings(BaseSettings):
    # Postgres configuration
    POSTGRES_USER: str = Field(..., env="POSTGRES_USER")
    POSTGRES_PASSWORD: str = Field(..., env="POSTGRES_PASSWORD")
    POSTGRES_HOST: str = Field(..., env="POSTGRES_HOST")
    POSTGRES_PORT: str = Field(..., env="POSTGRES_PORT")
    POSTGRES_DB: str = Field(..., env="POSTGRES_DB")

    # Redis configuration
    REDIS_URL: str = Field(..., env="REDIS_URL")

    # Pinecone config
    PINECONE_API_KEY: str = Field(..., env="PINECONE_API_KEY")
    PINECONE_ENVIRONMENT: str = Field(..., env="PINECONE_ENVIRONMENT")

    # Azure
    AZURE_STORAGE_CONNECTION_STRING: str = Field(
        ..., env="AZURE_STORAGE_CONNECTION_STRING"
    )

    # LLM / OpenAI config
    LLM_API_KEY: str = Field(..., env="LLM_API_KEY")
    OPENAI_API_KEY: str = Field(..., env="OPENAI_API_KEY")
    OMNI_MEMORY_PROVIDER: str = Field(..., env="OMNI_MEMORY_PROVIDER")

    # Dynamically generated async DB URL with SSL and Neon pooler settings
    @property
    def DATABASE_URL(self) -> str:
        # Use Neon pooler with optimized settings
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{quote_plus(self.POSTGRES_PASSWORD)}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            f"?ssl=require&prepared_statement_cache_size=0"  # Disable prepared statements for pooler
        )

    # Dynamically generated sync DB URL with SSL
    @property
    def SYNC_DB_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{quote_plus(self.POSTGRES_PASSWORD)}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            f"?sslmode=require"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Usage
settings = Settings()
