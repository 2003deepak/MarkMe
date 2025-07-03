from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    # MongoDB settings
    MONGO_URI: str 
    MONGO_DB_NAME: str

    # JWT settings
    SECRET_KEY: str  
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Redis settings
    REDIS_HOST: str 
    REDIS_PORT: int 

    # Mail settings    
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_PORT: int
    MAIL_SERVER: str

    # RabbitMQ settings
    RABBITMQ_URL: str

    #ImageKitIO Settings
    IMAGEKIT_PUBLIC_KEY: str
    IMAGEKIT_PRIVATE_KEY: str
    IMAGEKIT_URL_ENDPOINT: str 

    # Project settings
    PROJECT_NAME: str = "Your FastAPI Project"
    API_V1_STR: str = "/api/v1"

    # Environment (development, production, testing)
    ENVIRONMENT: str 

    # Load environment variables from .env file
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Instantiate settings
settings = Settings()