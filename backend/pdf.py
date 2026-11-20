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
    c = canvas.Canvas(output, pagesize=(1264, 669), invariant=1)
    c.setTitle('Destination — именные билеты')
    navy, red = HexColor('#062b53'), HexColor('#f20b3e')
    def centered(x, baseline, value, size, font='DestinationBold', color=navy, width=800):
        value = str(value)
        while pdfmetrics.stringWidth(value, font, size) > width: size -= .25
        c.setFillColor(color); c.setFont(font, size)
        c.drawCentredString(x, 669-baseline, value)
    months = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря']
    weekdays = ['пн','вт','ср','чт','пт','сб','вс']
    countries = ['АНГЛИЯ','США','КАНАДА','ЧЕХИЯ','ВЕНГРИЯ','ГЕРМАНИЯ','ИТАЛИЯ','КИТАЙ','КОРЕЯ','МАЛАЙЗИЯ']
    for t in tickets:
        e = t.snapshot
        c.setFillColor(white); c.rect(0, 0, 1264, 669, fill=1, stroke=0)
        for i, (x, country) in enumerate(zip([62,190,314,444,568,696,824,952,1080,1214], countries)):
            centered(x, 20, country, 15, 'Destination', HexColor('#111111'), 112)
            c.drawImage(str(ASSETS / f'flag-{i}.png'), x-28, 669-89, 57, 60)
        centered(435, 168, 'ПРЕЗЕНТАЦИЯ', 48, width=790)
        centered(425, 210, 'ВЫСШЕЕ ОБРАЗОВАНИЕ ЗА РУБЕЖОМ', 34, color=red, width=770)
        centered(444, 324, f'БИЛЕТ № {t.number}', 40, 'DestinationBI', HexColor('#004878'), 730)
        name_size = 36
        name_lines = [t.name]
        if pdfmetrics.stringWidth(t.name, 'DestinationBI', name_size) > 740:
            name_size = 30
            while True:
                name_lines, line = [], ''
                # Character-based fitting also handles a long unbroken surname.
                words = t.name.split()
                for word in words:
                    if pdfmetrics.stringWidth((line+' '+word).strip(), 'DestinationBI', name_size) <= 740:
                        line = (line+' '+word).strip()
                    else:
                        if line: name_lines.append(line)
                        line = ''
                        for char in word:
                            if pdfmetrics.stringWidth(line+char, 'DestinationBI', name_size) > 740:
                                name_lines.append(line); line = ''
                            line += char
                if line: name_lines.append(line)
                if len(name_lines) <= 3: break
                name_size -= 1
        for i, line in enumerate(name_lines):
            centered(432, 415-(len(name_lines)-1-i)*(name_size+3), line, name_size, 'DestinationBI', HexColor('#26333e'), 740)
        c.setStrokeColor(HexColor('#004878')); c.setLineWidth(1.5)
        c.line(186, 669-428, 675, 669-428)
        d = date.fromisoformat(e['date'])
        when = f'{d.day} {months[d.month-1]} ({weekdays[d.weekday()]}) начало {e["time"]}'
        centered(432, 533, when, 34, color=red, width=785)
        centered(432, 576, e['venue'], 32, width=780)
        centered(432, 607, f'{e["city"]}, {e["address"]}', 18, 'Destination', width=790)
        c.drawImage(str(ASSETS / 'speaker.png'), 869, 669-486, 321, 361)
        centered(1025, 527, e['speaker'].upper(), 35, color=HexColor('#20252b'), width=340)
        for baseline, line in [(552,'международный эксперт'), (575,'по образованию за рубежом'), (598,'с опытом более 20 лет')]:
            centered(1025, baseline, line, 20, 'DestinationItalic', HexColor('#26333e'), 340)
        centered(632, 651, 'Билет участвует в розыгрыше призов при личном присутствии', 11, 'Destination', HexColor('#68717a'), 1160)
        if t.cancelled: centered(432, 470, 'ОТМЕНЁН', 28, color=red, width=730)
        c.showPage()
    c.save()
    return output.getvalue()
