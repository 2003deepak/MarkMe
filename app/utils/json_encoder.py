import json
import datetime
from bson import ObjectId
from decimal import Decimal
from uuid import UUID
from enum import Enum


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        # Mongo
        if isinstance(obj, ObjectId):
            return str(obj)

        # Date & Time
        if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
            return obj.isoformat()

        # Bytes
        if isinstance(obj, bytes):
            return obj.decode("utf-8")

        # Decimal
        if isinstance(obj, Decimal):
            return float(obj)

        # UUID
        if isinstance(obj, UUID):
            return str(obj)

        # Enum
        if isinstance(obj, Enum):
            return obj.value

        # Set → list
        if isinstance(obj, set):
            return list(obj)

        return super().default(obj)