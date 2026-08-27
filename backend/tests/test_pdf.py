import io
import re

from PIL import Image

from app.pdf import png_bytes_to_pdf_bytes

POINTS_PER_INCH = 72


def _media_box(pdf_bytes: bytes) -> tuple[float, float]:
    match = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", pdf_bytes)
    assert match, "MediaBox not found in generated PDF"
    return float(match.group(1)), float(match.group(2))


def _png_bytes(size_px: tuple[int, int], dpi: tuple[int, int] | None) -> bytes:
    img = Image.new("RGB", size_px, color="white")
    out = io.BytesIO()
    if dpi:
        img.save(out, format="PNG", dpi=dpi)
    else:
        img.save(out, format="PNG")
    return out.getvalue()


def test_4x6_label_at_203_dpi_produces_4x6_inch_pdf():
    png = _png_bytes((812, 1218), dpi=(203, 203))
    pdf = png_bytes_to_pdf_bytes(png)
    width_pt, height_pt = _media_box(pdf)
    assert abs(width_pt - 4 * POINTS_PER_INCH) < 1
    assert abs(height_pt - 6 * POINTS_PER_INCH) < 1


def test_uses_dpi_fallback_when_png_has_no_dpi_metadata(monkeypatch):
    monkeypatch.setattr("app.pdf.settings.label_pdf_dpi_fallback", 203)
    png = _png_bytes((812, 1218), dpi=None)
    pdf = png_bytes_to_pdf_bytes(png)
    width_pt, height_pt = _media_box(pdf)
    assert abs(width_pt - 4 * POINTS_PER_INCH) < 1
    assert abs(height_pt - 6 * POINTS_PER_INCH) < 1


def test_output_is_valid_single_page_pdf():
    png = _png_bytes((400, 600), dpi=(200, 200))
    pdf = png_bytes_to_pdf_bytes(png)
    assert pdf.startswith(b"%PDF")
    page_objects = re.findall(rb"/Type\s*/Page(?!s)", pdf)
    assert len(page_objects) == 1
