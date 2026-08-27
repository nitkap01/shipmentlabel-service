"""PNG -> PDF conversion (D6). One label PNG, one PDF page, physical size preserved."""

import io

from PIL import Image

from app.config import settings


def png_bytes_to_pdf_bytes(png_bytes: bytes) -> bytes:
    with Image.open(io.BytesIO(png_bytes)) as img:
        img.load()
        dpi = img.info.get("dpi")
        if not dpi or not dpi[0]:
            dpi = (settings.label_pdf_dpi_fallback, settings.label_pdf_dpi_fallback)

        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        out = io.BytesIO()
        img.save(out, format="PDF", resolution=dpi[0])
        return out.getvalue()
