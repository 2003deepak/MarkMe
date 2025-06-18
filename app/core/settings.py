from pydantic import BaseSettings

class Settings(BaseSettings):
    MONGO_URI: str
    MONGO_DB_NAME: str
    SECRET_KEY: str
    REDIS_HOST: str
    REDIS_PORT: int
    ENVIRONMENT: str = "development"

    class Config:
        env_file = ".env"  

settings = Settings()
