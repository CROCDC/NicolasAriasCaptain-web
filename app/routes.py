"""Route definitions for the Capitán Nicolás Arias application."""

from flask import (
    Flask,
    Response,
    render_template,
    request,
    jsonify,
    send_from_directory,
    url_for,
)
from app.repositories.contact_repository import ContactRepository

#: The services the contact form may ask about. Kept in step with the enum on
#: ContactMessage and with the <select> in the template — a value outside this
#: set is rejected rather than stored as "otro", because a request the captain
#: never offered is a bug worth seeing.
VALID_SERVICE_TYPES: set[str] = {"patron", "traslado", "salida", "otro"}

#: Field limits, mirroring the column widths so a value that would be silently
#: truncated on the way into the database is refused at the door instead.
MAX_NAME = 120
MAX_EMAIL = 254
MAX_PHONE = 40
MAX_MESSAGE = 5000


def json_object() -> dict:
    """The request body as an object, or an empty one.

    ``get_json(silent=True) or {}`` looks like it does this and does not: a bare
    ``1`` parses fine, is truthy, and then blows up on the first ``.get``. The
    body comes from a browser, so it is whatever arrives.
    """
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def register_routes(app: Flask) -> None:
    """Attach all URL rules to the given Flask application instance."""

    @app.route("/favicon.ico")
    def favicon() -> object:
        """Serve favicon.ico so browsers that request it directly get an icon."""
        return send_from_directory(
            app.static_folder + "/assets",
            "favicon.svg",
            mimetype="image/svg+xml",
        )

    @app.route("/", methods=["GET"])
    def index() -> str:
        """Render the single-page landing site."""
        return render_template(
            "index.html",
            critical_css=app.config.get("CRITICAL_CSS", ""),
        )

    @app.route("/health", methods=["GET"])
    def health() -> object:
        """Liveness probe for the proxy and the deploy pipeline."""
        return jsonify({"status": "ok"})

    @app.route("/robots.txt", methods=["GET"])
    def robots() -> Response:
        """Allow everything, and point crawlers at the sitemap."""
        sitemap = f"{app.config['SITE']['url'].rstrip('/')}/sitemap.xml"
        body = f"User-agent: *\nAllow: /\n\nSitemap: {sitemap}\n"
        return Response(body, mimetype="text/plain")

    @app.route("/sitemap.xml", methods=["GET"])
    def sitemap() -> Response:
        """One page, but a crawler should not have to guess that."""
        home = app.config["SITE"]["url"].rstrip("/") + url_for("index")
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"  <url><loc>{home}</loc><changefreq>monthly</changefreq></url>\n"
            "</urlset>\n"
        )
        return Response(body, mimetype="application/xml")

    @app.route("/contact", methods=["POST"])
    def contact() -> object:
        """Accept a JSON contact form submission, persist it, and return JSON.

        Expected JSON body:
            name (str): Sender's full name.
            email (str): Sender's email address.
            phone (str): Optional phone number.
            service_type (str): One of patron / traslado / salida / otro.
            message (str): The body of the inquiry.

        Returns:
            JSON response with a 'success' flag and either the stored message
            or the list of validation errors.
        """
        data = json_object()

        name: str = str(data.get("name", "")).strip()
        email: str = str(data.get("email", "")).strip()
        phone: str = str(data.get("phone", "")).strip()
        # No default: the form always sends one, and a request that does not
        # is not "otra consulta", it is a request nobody chose a service for.
        service_type: str = str(data.get("service_type", "")).strip().lower()
        message: str = str(data.get("message", "")).strip()

        # --- Validation ---
        errors: list[str] = []

        if not name:
            errors.append("El nombre es obligatorio.")
        elif len(name) > MAX_NAME:
            errors.append(f"El nombre no puede superar los {MAX_NAME} caracteres.")

        if not email:
            errors.append("El correo electrónico es obligatorio.")
        elif "@" not in email or len(email) > MAX_EMAIL:
            errors.append("El correo electrónico no es válido.")

        if len(phone) > MAX_PHONE:
            errors.append("El teléfono no es válido.")

        if not service_type:
            errors.append("Elegí qué tipo de servicio necesitás.")
        elif service_type not in VALID_SERVICE_TYPES:
            errors.append("El tipo de servicio seleccionado no es válido.")

        if not message:
            errors.append("El mensaje es obligatorio.")
        elif len(message) > MAX_MESSAGE:
            errors.append(f"El mensaje no puede superar los {MAX_MESSAGE} caracteres.")

        if errors:
            return jsonify({"success": False, "errors": errors}), 400

        # --- Persistence ---
        contact_msg = ContactRepository.save(
            name=name,
            email=email,
            phone=phone,
            service_type=service_type,
            message=message,
        )

        return jsonify({
            "success": True,
            "message": "¡Gracias! Recibí tu mensaje. Te respondo a la brevedad.",
            "data": contact_msg.to_dict(),
        }), 201

    @app.errorhandler(404)
    def not_found(_error: object) -> tuple[str, int]:
        """A wrong turn still lands on something that looks like the site."""
        return render_template(
            "404.html",
            critical_css=app.config.get("CRITICAL_CSS", ""),
        ), 404
