"""Flask application factory for the Capitán Nicolás Arias site."""

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from flask import Flask, url_for
from markupsafe import Markup
from sitecopy import LocalFileStore, SiteCopy
from flask_compress import Compress
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv

# Load environment variables before anything else
load_dotenv()

# Extensions instantiated outside create_app so they can be imported by models
db: SQLAlchemy = SQLAlchemy()
migrate: Migrate = Migrate()
compress: Compress = Compress()

_STATIC_CACHE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year in seconds

# Both JavaScript spellings: Python's mimetypes returns "text/javascript" for
# .js on current versions, so a list with only the application/ spelling silently
# leaves every script uncached.
_STATIC_MIME_PREFIXES = (
    "text/css", "text/javascript", "application/javascript", "image/", "font/",
)


def _load_site_config(base_dir: str) -> dict:
    """Read app/data/site.json — every name, number and address the site shows.

    One file rather than a dozen templates: the phone number, the email and the
    Instagram handle appear in the navbar, the contact block, the footer, the
    floating button and the social card, and a site whose owner has to find all
    five to change a digit is a site that ends up showing two numbers.
    """
    path = os.path.join(base_dir, "data", "site.json")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def create_app() -> Flask:
    """Create and configure the Flask application instance."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # Behind the nginx-proxy (one hop): trust its X-Forwarded-* headers so
    # request.remote_addr is the real client IP, not the proxy's.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(
        app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1
    )

    # --- Configuration ---
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "sqlite:///arias.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    # SQLite serialises writers and this app runs two gunicorn workers. Five
    # seconds is pysqlite's default before it gives up with "database is
    # locked", which turns a request that only had to wait its turn into a 500.
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"timeout": 30},
        }
    # Public identifier: it is rendered into the page, so it is configuration
    # rather than a secret. Unset means the tracking script is simply not emitted.
    app.config["UMAMI_WEBSITE_ID"] = os.getenv("UMAMI_WEBSITE_ID")
    app.config["COMPRESS_ALGORITHM"] = "gzip"
    app.config["COMPRESS_MIN_SIZE"] = 500

    # --- Initialize extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    compress.init_app(app)

    # --- Cache-Control headers ---
    @app.after_request
    def set_cache_headers(response):
        ct = response.content_type or ""
        if any(ct.startswith(prefix) for prefix in _STATIC_MIME_PREFIXES):
            # Flask marks static files no-cache so the browser revalidates
            # against the etag. Left in place it outranks max-age and every
            # asset is re-checked on every load; the ?v= digest already makes a
            # changed file a different URL, so the year-long cache is safe and
            # immutable says so.
            response.cache_control.no_cache = None
            response.cache_control.max_age = _STATIC_CACHE_MAX_AGE
            response.cache_control.public = True
            response.cache_control.immutable = True
        return response

    # --- Load critical CSS once at startup ---
    # The @font-face rules go in front of it, inlined rather than linked: they
    # are 3KB, and a separate stylesheet for them would be one more blocking
    # request between the browser and the first styled letter. Their url()s are
    # written relative to /static/css/, so they have to be repointed at the
    # document root now that they are being served from inside the HTML.
    css_dir = os.path.join(app.static_folder, "css")
    with open(os.path.join(css_dir, "fonts.css"), "r", encoding="utf-8") as handle:
        fonts_css = handle.read().replace("url('../", "url('/static/")
    with open(os.path.join(css_dir, "critical.css"), "r", encoding="utf-8") as handle:
        # Markup, not a plain string: this lands inside <style>, where HTML
        # entities are not decoded — an escaped quote in a url() would be a
        # dead font reference rather than a quote.
        app.config["CRITICAL_CSS"] = Markup(fonts_css + handle.read())

    # --- Site copy and contact details ---
    app.config["SITE"] = _load_site_config(os.path.dirname(__file__))
    app.jinja_env.globals["site"] = app.config["SITE"]

    # --- Editable copy ---
    # The overrides live in two JSON documents, not in the database: every page
    # reads them, and a hosted database bills for every read that wakes it. Each
    # process keeps its copy in memory and re-checks it at most every
    # CONTENT_REFRESH_SECONDS — see app/services/json_store.py. Where they live
    # is a directory (CONTENT_DIR, the instance folder by default) or Vercel Blob
    # when BLOB_READ_WRITE_TOKEN is set. The database keeps the contact form.
    #
    # The panel reads ADMIN_PASSWORD from the environment, and an unset one
    # refuses every password — a deployment that forgot it is locked, not open.
    # Every default lives in app/content.py, so an empty document renders the site
    # exactly as the templates always did.
    from app.content import REGISTRY
    from app.services.json_store import stores_from_env
    text_store, media_history = stores_from_env(app)
    app.extensions["content_stores"] = (text_store, media_history)
    SiteCopy(
        app,
        registry=REGISTRY,
        store=text_store,
        password=os.getenv("ADMIN_PASSWORD", ""),
        brand=app.config["SITE"]["brand"],
        site_url=app.config["SITE"]["url"],
        # Let the editor resize a text. The scale is in em, so a step means the
        # same thing on a headline and on a button and the site's own type scale
        # keeps deciding the absolute size — which is what makes it safe to hand
        # over on a layout this typographic.
        text_sizes=True,
        # Uploads land in the static folder, so they are served and cached like
        # any other asset. See app/content.py for what a replaced photograph
        # does and does not keep.
        #
        # `files=`, not `media_store=`: the latter is sitecopy's version-history
        # store. Passed there, this store was never used for uploads — they fell
        # back to static/sitecopy-uploads, outside the arias_uploads volume, and
        # vanished on the next deploy — and every photo publish 500'd calling
        # .record() on it. The version history is the JSON one, passed below.
        files=LocalFileStore(
            directory=os.path.join(app.static_folder, "assets", "subidas"),
            base_url=f"{app.static_url_path}/assets/subidas",
        ),
        media_store=media_history,
    )

    # --- Cache-busting for static assets ---
    # Static files are served with a one-year cache, so a URL like
    # ``main.js?v=<content-hash>`` is needed for a changed file to reach
    # returning visitors. The hash is computed once per file per process.
    _asset_versions: dict[str, str] = {}

    def asset(filename: str) -> str:
        version = _asset_versions.get(filename)
        if version is None:
            full_path = os.path.join(app.static_folder, filename)
            try:
                with open(full_path, "rb") as fh:
                    version = hashlib.md5(fh.read()).hexdigest()[:10]
            except OSError:
                version = "0"
            _asset_versions[filename] = version
        return f"{url_for('static', filename=filename)}?v={version}"

    app.jinja_env.globals["asset"] = asset

    # The photographs, and which of them have actually arrived. The site is
    # built before the captain's own photos exist, so a slot with no file behind
    # it renders as a framed placeholder rather than a broken image — see
    # app/services/media.py.
    from app.services import media
    app.jinja_env.globals["photos"] = lambda kind: media.photos(app, kind)
    app.jinja_env.globals["photo"] = lambda slot_id: media.photo(app, slot_id)

    # The geometry the emblem motifs are drawn from: the graduated ring, the
    # arc the lettering is set on, the gauge the figures are read off. Computed
    # in Python because trigonometry in a template is unreadable and untestable.
    from app.services import emblem
    app.jinja_env.globals["bezel_ticks"] = emblem.bezel_ticks
    app.jinja_env.globals["arc_path"] = emblem.arc_path
    app.jinja_env.globals["gauge"] = emblem.gauge
    app.jinja_env.globals["gauge_stops"] = emblem.gauge_stops

    # --- Register routes inside app context ---
    with app.app_context():
        # Import models so SQLAlchemy is aware of them
        from app.models import ContactMessage  # noqa: F401

        with _schema_lock():
            # Create all tables (only creates missing ones)
            _create_tables()

            # Apply one-time recorded schema migrations (see _run_migrations).
            _run_migrations(app)

        from app.routes import register_routes
        register_routes(app)

    return app


@contextmanager
def _schema_lock():
    """Hold an exclusive file lock next to the SQLite file while the schema is set up.

    Gunicorn workers boot side by side and each one inspects the schema and then
    writes to it. Two connections that both read and then both try to write are
    a deadlock to SQLite, and it answers the loser at once with "database is
    locked" — the busy timeout never applies — which kills that worker and, with
    it, the container. Taking turns here makes the second worker find the
    schema already built.
    """
    url = db.engine.url
    if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
        yield
        return
    os.makedirs(os.path.dirname(os.path.abspath(url.database)), exist_ok=True)
    with open(f"{url.database}.schema-lock", "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _create_tables() -> None:
    """``db.create_all()``, tolerant of another worker creating the same table.

    Gunicorn boots its workers side by side, and each one builds the app. When
    a deploy brings a new table, both see it missing and both CREATE it; the
    loser died on "table already exists", which took gunicorn and the container
    down with it. A second pass finds the table and skips it.
    """
    from sqlalchemy.exc import OperationalError

    try:
        db.create_all()
    except OperationalError as error:
        if "already exists" not in str(error.orig):
            raise
        db.session.rollback()
        db.create_all()


def _add_columns_if_missing(engine, table: str, columns: dict[str, str]) -> list[str]:
    """ADD COLUMN for each column absent from an existing table.

    Guarded so it is safe on a fresh database where ``create_all`` already
    built the table with these columns. Returns the names actually added.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return []

    present = {col["name"] for col in inspector.get_columns(table)}
    added: list[str] = []
    with engine.begin() as conn:
        for name, sql_type in columns.items():
            if name in present:
                continue
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {name} {sql_type}'))
            added.append(name)
    return added


# Ordered list of one-time migrations. Each runs at most once; append new
# entries here, never edit or reorder applied ones. Empty while the schema is
# still the one create_all builds — the runner is here so the first column
# added to a table that already exists in production has somewhere to go.
_MIGRATIONS: list[tuple[str, object]] = []


def _run_migrations(app: Flask) -> None:
    """Run any not-yet-applied migrations from ``_MIGRATIONS`` exactly once.

    Applied migration names are recorded in the ``schema_migrations`` table, so
    each migration runs a single time and never again on later boots. The
    migrations themselves are additive and guarded, so a fresh database (where
    ``create_all`` already produced the current schema) simply records them as
    applied without changing anything.
    """
    from sqlalchemy import text

    engine = db.engine
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "name VARCHAR(255) PRIMARY KEY, "
            "applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        ))
        applied = {row[0] for row in conn.execute(text("SELECT name FROM schema_migrations"))}

    for name, run in _MIGRATIONS:
        if name in applied:
            continue
        try:
            run(engine)
            with engine.begin() as conn:
                conn.execute(
                    text("INSERT INTO schema_migrations (name) VALUES (:name)"),
                    {"name": name},
                )
            app.logger.warning("Applied migration %s", name)
        except Exception as exc:  # pragma: no cover - defensive, never fatal
            app.logger.error("Migration %s failed: %s", name, exc)
