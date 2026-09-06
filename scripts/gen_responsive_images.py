"""Write the smaller widths of every photograph the site declares.

The site ships one file per slot at the size the crop produced — around 1000px
wide. Nothing displays that big: the portada medallion is 285 CSS px, a service
medallion 219, a gallery frame 340. Even at a 3x screen the largest of those
wants ~1020px, and a phone at 1.75x wants 380. Sending the original to every
one of them is most of a megabyte nobody sees.

So each photograph gets a couple of narrower siblings and the template offers
all of them through ``srcset``; the browser takes the one its screen actually
needs. Run after adding or replacing a photograph:

    venv/bin/python scripts/gen_responsive_images.py

Idempotent, and it never writes a variant wider than the original — upscaling
would add bytes and no detail.
"""

from __future__ import annotations

import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTO_DIR = os.path.join(ROOT, "app", "static", "assets", "photos")

#: The widths worth having. 400 covers a phone, 700 a laptop or a phone at 3x;
#: above that the original is already the right answer.
WIDTHS = (400, 700)

#: Quality matched to how the originals were written, so a variant does not
#: look softer than the file it came from.
QUALITY = 82


def variants(name: str) -> list[str]:
    """Every file written for one photograph, newest first out of the loop."""
    base, extension = os.path.splitext(name)
    if extension.lower() != ".webp":
        return []

    source = os.path.join(PHOTO_DIR, name)
    written = []
    with Image.open(source) as image:
        original_width, original_height = image.size
        for width in WIDTHS:
            if width >= original_width:
                continue
            height = round(original_height * width / original_width)
            target = os.path.join(PHOTO_DIR, f"{base}-{width}.webp")
            resized = image.resize((width, height), Image.LANCZOS)
            resized.save(target, "WEBP", quality=QUALITY, method=6)
            written.append(f"{base}-{width}.webp")
    return written


def main() -> int:
    if not os.path.isdir(PHOTO_DIR):
        print(f"no photo directory at {PHOTO_DIR}")
        return 1

    originals = sorted(
        name for name in os.listdir(PHOTO_DIR)
        if name.endswith(".webp") and "-" not in os.path.splitext(name)[0].rsplit("-", 1)[-1][:1]
        and not any(name.endswith(f"-{width}.webp") for width in WIDTHS)
    )

    total = 0
    for name in originals:
        written = variants(name)
        for target in written:
            size = os.path.getsize(os.path.join(PHOTO_DIR, target)) / 1024
            print(f"  {target:34s} {size:6.1f} KB")
            total += 1
    print(f"\n{total} variants written for {len(originals)} photographs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
