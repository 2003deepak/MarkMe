from pydantic_settings import BaseSettings, SettingsConfigDict

class RabbitMQSettings(BaseSettings):
    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    email_queue: str = "email_queue"
    embedding_queue: str = "embedding_queue"
    face_queue: str = "face_recog_queue"
    session_queue : str = "session_queue"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

settings = RabbitMQSettings()
