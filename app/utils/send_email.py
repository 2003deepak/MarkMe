from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr
from app.core.config import settings
from app.core.mail_config import conf

async def send_email(subject: str, email_to: EmailStr, body: str):
    message = MessageSchema(
        subject=subject,
        recipients=[email_to],
        body=body,
        subtype="html"
    )
    fm = FastMail(conf)
    await fm.send_message(message)
