"""ContactMessage model for storing inquiries submitted via the contact form."""

from datetime import datetime, timezone
from typing import Any
from app.factory import db


class ContactMessage(db.Model):
    """Represents a contact form submission from a prospective client."""

    __tablename__ = "contact_messages"

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(120), nullable=False)
    email: str = db.Column(db.String(254), nullable=False)
    phone: str = db.Column(db.String(40), nullable=True)
    service_type: str = db.Column(
        db.Enum("patron", "traslado", "salida", "otro", name="service_type_enum"),
        nullable=False,
        default="otro",
    )
    message: str = db.Column(db.Text, nullable=False)
    created_at: datetime = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<ContactMessage id={self.id} from={self.email}>"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "service_type": self.service_type,
            "message": self.message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
