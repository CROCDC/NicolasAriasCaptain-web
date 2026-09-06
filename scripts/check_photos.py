#!/usr/bin/env python3
"""Print the photographs the site declares and does not yet have.

Every name listed here is a slot currently rendering as a placeholder. Drop the
file into app/static/assets/photos/ under exactly that name and it becomes the
photograph — no template, no code.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
from app.services import media  # noqa: E402


def main() -> int:
    with app.app_context():
        slots = media.load_manifest(app)
        pending = media.missing(app)

    print()
    print(f"  Fotos declaradas: {len(slots)}")
    print(f"  Ya cargadas:      {len(slots) - len(pending)}")
    print(f"  Faltan:           {len(pending)}")
    print()

    if not pending:
        print("  No falta ninguna. \n")
        return 0

    by_file = {slot["file"]: slot for slot in slots}
    for filename in pending:
        slot = by_file[filename]
        print(f"  · {filename}")
        print(f"      {slot.get('caption') or slot['alt']}")
        if slot.get("notes"):
            print(f"      {slot['notes']}")
    print()
    print("  Van en app/static/assets/photos/ (ver el README de esa carpeta).")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
