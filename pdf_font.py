"""Use an explicitly configured Unicode font or a ReportLab Korean CID font."""
import os
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
def register(name):
 if name in pdfmetrics.getRegisteredFontNames():return
 path=Path(os.environ.get('AIRI_PDF_FONT','/Library/Fonts/Arial Unicode.ttf'))
 if path.is_file():pdfmetrics.registerFont(TTFont(name,str(path)))
 else:
  font=UnicodeCIDFont('HYSMyeongJo-Medium');font.fontName=name;pdfmetrics.registerFont(font)
