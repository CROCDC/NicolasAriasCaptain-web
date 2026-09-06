"""Repository layer for ContactMessage persistence."""

from app.factory import db
from app.models.contact import ContactMessage


class ContactRepository:
    """Provides static data-access methods for ContactMessage entities."""

    @staticmethod
    def save(
        name: str,
        email: str,
        service_type: str,
        message: str,
        phone: str | None = None,
    ) -> ContactMessage:
        """Persist a new contact message and return the saved instance.

        Args:
            name: Full name of the sender.
            email: Email address of the sender.
            service_type: One of 'patron', 'traslado', 'salida', 'otro'.
            message: Body text of the inquiry.
            phone: Optional phone number the sender prefers to be reached on.

        Returns:
            The newly created and committed ContactMessage instance.
        """
        contact = ContactMessage(
            name=name,
            email=email,
            phone=phone or None,
            service_type=service_type,
            message=message,
        )
        db.session.add(contact)
        db.session.commit()
        return contact

    @staticmethod
    def get_all() -> list[ContactMessage]:
        """Return all stored contact messages, newest first."""
        return ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
