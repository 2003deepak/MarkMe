from .teacher import Teacher
from .subject import Subject

# Rebuild models to resolve circular references
Teacher.model_rebuild()
Subject.model_rebuild()