"""
Base model classes for the application.
All models should inherit from BaseModel to get consistent UUID and timestamp fields.
"""

import uuid
from django.db import models

class BaseModel(models.Model):
    """
    Abstract base model that provides:
    - UUID primary key
    - Created and updated timestamps
    - Soft delete capability (if needed in future)
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier"
    )
    created_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the record was last updated"
    )
    class Meta:
        abstract = True
        ordering = ['_created_at']
        
    def __str__(self):
        return f"{self.__class__.__name__}{self.id}"