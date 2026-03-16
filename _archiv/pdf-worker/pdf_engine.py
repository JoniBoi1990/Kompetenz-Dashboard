"""
PDF Engine — migrated verbatim from app5.py with two targeted bug fixes:

  Fix 1: draw_text_wrapped() now returns y_pos (was missing, caused None y_pos in create_pdf).
  Fix 2: format_chemical_formula() uses regex search with pos parameter instead of str.find(),
         so repeated element tokens (e.g. C6H12O6) are located correctly.

All other logic is unchanged from the original.
"""
import io
import re
from textwrap import wrap

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

LOGO_PATH = "/app/static/logo.png"


def draw_chemical_formula(c, formula, x, y, font="Helvetica", font_size=12):
    """Zeichnet eine chemische Formel mit tiefgestellten Zahlen."""
    c.setFont(font, font_size)

    for part in formula:
        if isinstance(part, str):  # Text (Element)
            c.drawString(x, y, part)
            x += c.stringWidth(part, font, font_size)
        elif isinstance(part, int):  # Zahl (tiefgestellt)
            c.setFont(font, font_size - 2)
            c.drawString(x, y - 3, str(part))
            x += c.stringWidth(str(part), font, font_size - 2)
            c.setFont(font, font_size)

    return x, y


def format_chemical_formula(formula: str) -> list:
    """
    Formatiert chemische Formeln und setzt nur die Atomzahlen tief.

    BUG FIX vs. original app5.py:
    The original used formula.find(element + number) which returns the *first*
    occurrence of that substring, causing mis-positioning for repeated tokens
    (e.g. the second 'C6' in 'C6H12O6').  We now scan with re.search(pattern, formula, pos)
    advancing `pos` after each match so every occurrence is found at its actual position.
    """
    formatted_formula = []
    last_end = 0
    pos = 0

    for match in re.finditer(r'([A-Za-z]+)(\d+)', formula):
        start = match.start()
        element = match.group(1)
        number = int(match.group(2))

        # Text before this match (may include plain element symbols without numbers)
        formatted_formula.append(formula[last_end:start])
        formatted_formula.append(element)
        formatted_formula.append(number)
        last_end = match.end()

    # Remaining text after last match
    formatted_formula.append(formula[last_end:])
    return formatted_formula


def draw_header(c, name, datum, zusatzinfo, logo_path, width, height):
    """Zeichnet die Kopfzeile auf die PDF-Seite."""
    c.drawImage(logo_path, 0, height - 120, width=200, height=100, preserveAspectRatio=True)

    c.setFont("Times-Bold", 10)
    right_x_position = width - 40
    padding = 10

    name_text = f"Name: {name}"
    datum_text = f"Datum: {datum}"
    zusatzinfo_text = f"Zusatzinfo: {zusatzinfo}"

    name_width = c.stringWidth(name_text, "Times-Bold", 10)
    datum_width = c.stringWidth(datum_text, "Times-Bold", 10)
    zusatzinfo_width = c.stringWidth(zusatzinfo_text, "Times-Bold", 10)

    max_width = max(name_width, datum_width, zusatzinfo_width)
    adjusted_x_position = right_x_position - max_width - padding

    c.drawString(adjusted_x_position, height - 50, name_text)
    c.drawString(adjusted_x_position, height - 70, datum_text)
    c.drawString(adjusted_x_position, height - 90, zusatzinfo_text)

    line_y_position = height - 130
    c.setLineWidth(1)
    c.line(20, line_y_position, width - 20, line_y_position)


def draw_text_wrapped(c, text, x, y, max_width, line_height, font="Times-Roman", font_size=12):
    """
    Zeichnet umbrochenen Text, wenn er zu lang für eine Zeile ist.

    BUG FIX vs. original app5.py:
    The original had no return statement, so the function implicitly returned None.
    create_pdf() had to guard against None y_pos.  We now return y_pos explicitly.
    """
    c.setFont(font, font_size)

    wrapped_text = wrap(text, width=100)

    for line in wrapped_text:
        formatted_formula = format_chemical_formula(line)
        x_start = x
        for part in formatted_formula:
            if isinstance(part, str):
                c.drawString(x_start, y, part)
                x_start += c.stringWidth(part, font, font_size)
            elif isinstance(part, int):
                c.setFont(font, font_size - 2)
                c.drawString(x_start, y - 3, str(part))
                x_start += c.stringWidth(str(part), font, font_size - 2)
                c.setFont(font, font_size)
        y -= line_height

    # BUG FIX: return y_pos so caller can track the current vertical position
    return y


def create_pdf(questions: list, name: str, datum: str, zusatzinfo: str) -> bytes:
    """
    Erzeugt eine PDF aus Fragen (Dicts mit kid/text) und Meta-Daten.
    Returns PDF as bytes (BytesIO) instead of saving to disk.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    logo_path = LOGO_PATH

    frage_schriftart = "Times-Roman"
    frage_schriftgroesse = 12
    zeilenhoehe = 16
    max_text_width = width - 80
    questions_per_page = 2

    y_pos = height - 150

    for i, item in enumerate(questions):
        if isinstance(item, dict):
            kid = item.get("kid", "")
            text = item.get("text", "")
            zeile = f"[{kid}] {text}" if kid else text
        else:
            zeile = str(item)

        if i % questions_per_page == 0:
            if i > 0:
                c.showPage()
            draw_header(c, name, datum, zusatzinfo, logo_path, width, height)
            y_pos = height - 150

        y_pos = draw_text_wrapped(
            c, zeile, 40, y_pos, max_text_width, zeilenhoehe,
            font=frage_schriftart, font_size=frage_schriftgroesse,
        )

        # y_pos is now always a valid number (bug fixed above)
        y_pos -= (height - 150) / 2

    c.save()
    buf.seek(0)
    return buf.read()
