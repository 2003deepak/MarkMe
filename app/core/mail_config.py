from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr
from app.core.config import settings

conf = ConnectionConfig(
    MAIL_USERNAME = settings.MAIL_USERNAME,
    MAIL_PASSWORD = settings.MAIL_PASSWORD,
    MAIL_FROM = settings.MAIL_FROM,
    MAIL_PORT = settings.MAIL_PORT,
    MAIL_SERVER = settings.MAIL_SERVER,
    MAIL_STARTTLS = True,     
    MAIL_SSL_TLS = False, 
    USE_CREDENTIALS = True,
    VALIDATE_CERTS = True
)
