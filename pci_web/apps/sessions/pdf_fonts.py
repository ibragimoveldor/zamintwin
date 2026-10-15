"""
Unicode fonts for ReportLab PDFs.
The built-in Helvetica has no Cyrillic glyphs, so localized reports embed DejaVu Sans.
"""
from pathlib import Path

from django.conf import settings
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

REGULAR_FONT = "DejaVuSans"
BOLD_FONT = "DejaVuSans-Bold"

FONT_DIR = Path(settings.BASE_DIR) / "static" / "fonts" / "dejavu"


def register_unicode_fonts():
    if REGULAR_FONT in pdfmetrics.getRegisteredFontNames():
        return
    pdfmetrics.registerFont(TTFont(REGULAR_FONT, str(FONT_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(BOLD_FONT, str(FONT_DIR / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily(
        REGULAR_FONT, normal=REGULAR_FONT, bold=BOLD_FONT, italic=REGULAR_FONT, boldItalic=BOLD_FONT,
    )


def unicode_stylesheet():
    register_unicode_fonts()
    styles = getSampleStyleSheet()
    paragraph_styles = [style for style in styles.byName.values() if isinstance(style, ParagraphStyle)]
    for style in paragraph_styles:
        style.fontName = BOLD_FONT if "Bold" in style.fontName else REGULAR_FONT
        style.bulletFontName = REGULAR_FONT
    return styles
