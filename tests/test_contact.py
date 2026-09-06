"""The contact endpoint: what it stores, and what it refuses.

It is the only writing door the site has, so the refusals matter more than the
happy path.
"""

from __future__ import annotations

from typing import Any

VALID = {
    "name": "Marina Duarte",
    "email": "marina@example.com",
    "phone": "+54 9 11 5555 5555",
    "service_type": "traslado",
    "message": "Necesito llevar un velero de San Isidro a Piriápolis en marzo.",
}


def _post(client: Any, **overrides: Any) -> Any:
    payload = {**VALID, **overrides}
    return client.post("/contact", json=payload)


def test_a_valid_enquiry_is_stored(client: Any, app_instance: Any) -> None:
    response = _post(client)
    assert response.status_code == 201

    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["email"] == VALID["email"]
    assert body["data"]["service_type"] == "traslado"
    assert body["data"]["created_at"]

    with app_instance.app_context():
        from app.repositories import ContactRepository

        stored = ContactRepository.get_all()
        assert len(stored) == 1
        assert stored[0].message == VALID["message"]
        assert stored[0].phone == VALID["phone"]


def test_the_phone_is_optional(client: Any, app_instance: Any) -> None:
    assert _post(client, phone="").status_code == 201

    with app_instance.app_context():
        from app.repositories import ContactRepository

        # Empty is stored as absent rather than as an empty string, so "has a
        # phone number" is one question and not two.
        assert ContactRepository.get_all()[0].phone is None


def test_missing_fields_are_reported_all_at_once(client: Any) -> None:
    response = client.post("/contact", json={})
    assert response.status_code == 400

    errors = response.get_json()["errors"]
    # Name, email, service and message: a form that reveals one problem per
    # submit is a form people abandon.
    assert len(errors) == 4


def test_a_bad_email_is_refused(client: Any) -> None:
    response = _post(client, email="marina.example.com")
    assert response.status_code == 400
    assert "correo" in " ".join(response.get_json()["errors"]).lower()


def test_a_service_the_captain_does_not_offer_is_refused(client: Any) -> None:
    response = _post(client, service_type="submarino")
    assert response.status_code == 400
    assert "servicio" in " ".join(response.get_json()["errors"]).lower()


def test_an_overlong_field_is_refused_rather_than_truncated(client: Any) -> None:
    response = _post(client, name="a" * 121)
    assert response.status_code == 400


def test_a_body_that_is_not_an_object_is_a_400_and_not_a_500(client: Any) -> None:
    # `get_json(silent=True) or {}` would let a bare literal through and then
    # raise on the first .get — the browser sends whatever it sends.
    response = client.post("/contact", data="1", content_type="application/json")
    assert response.status_code == 400


def test_nothing_is_stored_when_validation_fails(client: Any, app_instance: Any) -> None:
    _post(client, email="")

    with app_instance.app_context():
        from app.repositories import ContactRepository

        assert ContactRepository.get_all() == []
