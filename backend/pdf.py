import os
import threading
from datetime import date
from io import BytesIO
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor, white

ASSETS = Path(__file__).resolve().parents[1] / 'assets' / 'ticket'
QR_IMAGE = ASSETS.parents[1] / 'data' / 'ticket-qr.png'
FONT_LOCK = threading.Lock()

def register_fonts():
    with FONT_LOCK:
        if 'DestinationBI' in pdfmetrics.getRegisteredFontNames(): return
        directories = [Path(os.getenv('FONT_DIR') or 'assets/fonts'), Path('C:/Windows/Fonts'), Path('/usr/share/fonts/truetype/dejavu')]
        for directory in directories:
            for files in [('DejaVuSans.ttf','DejaVuSans-Bold.ttf','DejaVuSans-Oblique.ttf','DejaVuSans-BoldOblique.ttf'), ('arial.ttf','arialbd.ttf','ariali.ttf','arialbi.ttf')]:
                if all((directory / f).exists() for f in files):
                    for name, file in zip(['Destination','DestinationBold','DestinationItalic','DestinationBI'], files):
                        pdfmetrics.registerFont(TTFont(name, str(directory / file)))
                    return
        raise RuntimeError('Не найдены Unicode-шрифты. Установите DejaVu Sans (обычный, жирный, курсив, жирный курсив) или настройте FONT_DIR.')

def pdf_bytes(tickets):
    register_fonts()
    output = BytesIO()
    page_width, page_height = 1254, 705.75
    layout_width, layout_height = 850, 478
    c = canvas.Canvas(output, pagesize=(page_width, page_height), invariant=1)
    c.setTitle('Destination — именные билеты')
    navy, red = HexColor('#0a2446'), HexColor('#ab1234')

    def draw_text(x, baseline, value, size, width, *, font='DestinationBold', color=navy, align='center'):
        text_width = pdfmetrics.stringWidth(value, font, size)
        if text_width > width:
            size *= width / text_width
        c.setFillColor(color)
        c.setFont(font, size)
        draw = c.drawCentredString if align == 'center' else c.drawString
        draw(x, layout_height - baseline, value)

    def wrap_text(value, size, width, font):
        measure = lambda line: pdfmetrics.stringWidth(line, font, size)
        words = value.split()
        if len(words) < 2 or measure(value) <= width:
            return [value]
        pairs = [(' '.join(words[:i]), ' '.join(words[i:])) for i in range(1, len(words))]
        return min(pairs, key=lambda pair: max(map(measure, pair)))

    months = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря']
    weekdays = ['пн','вт','ср','чт','пт','сб','вс']
    for t in tickets:
        e = t.snapshot
        d = date.fromisoformat(e['date'])
        when = f'{d.day} {months[d.month-1]} ({weekdays[d.weekday()]}) {e["time"]}'
        c.scale(page_width / layout_width, page_height / layout_height)
        c.drawImage(str(ASSETS / 'final-ticket.png'), 0, 0, layout_width, layout_height)
        draw_text(349, 236, f'БИЛЕТ № {t.number}', 29, 320)
        name_lines = wrap_text(t.name, 23, 315, 'DestinationBI')
        for i, line in enumerate(name_lines):
            draw_text(349, 282 - (len(name_lines) - 1 - i) * 22, line, 23, 315, font='DestinationBI')
        draw_text(260, 343, when, 23, 232, color=red, align='left')
        draw_text(264, 369, e['venue'], 21, 236, align='left')
        address = f'{e["city"]}, {e["address"]}'
        address_lines = wrap_text(address, 14, 236, 'Destination')
        for i, line in enumerate(address_lines):
            baseline = 389 if len(address_lines) == 1 else 383 + i * 14
            draw_text(264, baseline, line, 14, 236, font='Destination', align='left')
        draw_text(715, 359, e['speaker'].upper(), 23, 224)
        if t.cancelled:
            draw_text(350, 422, 'ОТМЕНЁН', 22, 320, color=red)
        c.showPage()
        c.setFillColor(HexColor('#f5f7fa'))
        c.rect(0, 0, page_width, page_height, fill=1, stroke=0)
        c.setFillColor(red)
        c.rect(page_width / 2 - 40, page_height - 95, 80, 4, fill=1, stroke=0)
        c.setFillColor(navy)
        c.setFont('DestinationBold', 34)
        c.drawCentredString(page_width / 2, page_height - 150, 'QR-код')
        c.setFillColor(white)
        c.setStrokeColor(navy)
        c.setLineWidth(1.75)
        c.roundRect(page_width / 2 - 170, 105, 340, 340, 14, fill=1, stroke=1)
        if QR_IMAGE.is_file():
            c.drawImage(str(QR_IMAGE), page_width / 2 - 145, 130, 290, 290,
                        preserveAspectRatio=True, anchor='c', mask='auto')
        c.showPage()
    c.save()
    return output.getvalue()
