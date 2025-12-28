from .teacher import Teacher
from .subject import Subject
from .session import Session
from .exception_session import ExceptionSession
from .swap_approval import SwapApproval

Teacher.model_rebuild()
Subject.model_rebuild()
Session.model_rebuild()
ExceptionSession.model_rebuild()
SwapApproval.model_rebuild()
