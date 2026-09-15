from io import BytesIO
from reportlab.lib.pagesizes import LETTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

def notice_pdf(title: str, body: str) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, rightMargin=.75*inch, leftMargin=.75*inch, topMargin=.75*inch, bottomMargin=.75*inch)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    for block in body.split("\n"):
        story.append(Paragraph(block.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") or "&nbsp;", styles["BodyText"]))
        story.append(Spacer(1, 6))
    doc.build(story)
    return buf.getvalue()
