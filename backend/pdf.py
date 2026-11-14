import os
from io import BytesIO
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor, white

def register_fonts():
    if 'Destination' in pdfmetrics.getRegisteredFontNames():
        return
    directories = [Path(os.getenv('FONT_DIR') or 'assets/fonts'), Path('C:/Windows/Fonts'), Path('/usr/share/fonts/truetype/dejavu')]
    for directory in directories:
        for regular, bold in [('DejaVuSans.ttf', 'DejaVuSans-Bold.ttf'), ('arial.ttf', 'arialbd.ttf')]:
            if (directory / regular).exists() and (directory / bold).exists():
                pdfmetrics.registerFont(TTFont('Destination', str(directory / regular)))
                pdfmetrics.registerFont(TTFont('DestinationBold', str(directory / bold)))
                return
    raise RuntimeError('Не найден Unicode-шрифт. Установите DejaVu Sans или настройте FONT_DIR.')

def pdf_bytes(tickets):
    register_fonts()
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=(900, 440), invariant=1)
    c.setTitle('Destination — именные билеты')
    navy, red = HexColor('#142c50'), HexColor('#e84347')
    def text(x, y, value, size=14, color=navy, bold=False, width=800):
        font = 'DestinationBold' if bold else 'Destination'
        while pdfmetrics.stringWidth(str(value), font, size) > width and size > 5:
            size -= .5
        c.setFillColor(color)
        c.setFont(font, size)
        c.drawString(x, y, str(value))
    for t in tickets:
        e = t.snapshot
        c.setFillColor(white); c.rect(0, 0, 900, 440, fill=1, stroke=0)
        c.setFillColor(navy); c.rect(0, 422, 900, 18, fill=1, stroke=0)
        text(36, 379, 'destination', 27, bold=True)
        text(37, 357, 'ОБРАЗОВАНИЕ БЕЗ ГРАНИЦ', 9)
        # Vector country flags: France, Germany, Italy, Poland, Netherlands.
        for i, colors in enumerate([['#0055a4','#ffffff','#ef4135'],['#151515','#dd0000','#ffce00'],['#009246','#ffffff','#ce2b37']]):
            for j, color in enumerate(colors):
                c.setFillColor(HexColor(color)); c.rect(616+i*64+j*16,376,16,28,fill=1,stroke=0)
        text(36, 302, 'ПРЕЗЕНТАЦИЯ', 34, bold=True)
        text(36, 270, 'ВЫСШЕЕ ОБРАЗОВАНИЕ ЗА РУБЕЖОМ', 18, red, True, 600)
        text(36, 226, t.name.upper(), 26, bold=True, width=580)
        text(36, 182, f"{e['city']} · {e['date']} · {e['time']}", 17, bold=True, width=585)
        text(36, 154, e['venue'], 14, width=585)
        text(36, 129, e['address'], 13, width=585)
        text(36, 86, 'СПИКЕР', 9, red, True)
        text(36, 64, e['speaker'], 15, bold=True, width=585)
        c.setStrokeColor(HexColor('#cbd5e1')); c.setDash(4, 5); c.line(648, 45, 648, 337); c.setDash()
        text(681, 297, 'ВАШ БИЛЕТ', 11, bold=True)
        text(677, 231, f'{t.number:04d}', 46, red, True, 187)
        text(681, 194, f"Мероприятие #{t.event_id}", 10)
        text(681, 155, 'ВХОД БЕСПЛАТНЫЙ', 10, bold=True)
        if t.cancelled:
            text(681, 117, 'ОТМЕНЁН', 20, red, True)
        text(36, 25, 'Билет участвует в розыгрыше призов при личном присутствии', 10)
        c.showPage()
    c.save()
    return output.getvalue()
