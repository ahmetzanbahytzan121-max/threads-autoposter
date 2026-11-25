"""Generate high-contrast 4:5 (1080x1350) promotional graphic cards for Threads."""

from __future__ import annotations

import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from env_utils import load_env


BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
RAW_DIR = ASSETS_DIR / "raw"

FONT_BOLD = Path(r"C:\Windows\Fonts\segoeuib.ttf")
FONT_REG = Path(r"C:\Windows\Fonts\segoeui.ttf")
FONT_SEMI = Path(r"C:\Windows\Fonts\seguisb.ttf")

WIDTH, HEIGHT = 1080, 1350


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    chosen = path if path.exists() else FONT_BOLD
    return ImageFont.truetype(str(chosen), size=size)


def _fit_cover(img: Image.Image, w: int, h: int) -> Image.Image:
    src_w, src_h = img.size
    scale = max(w / src_w, h / src_h)
    nw, nh = int(src_w * scale), int(src_h * scale)
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return resized.crop((left, top, left + w, top + h))


def _gradient_bg(top_rgb: tuple[int, int, int], bot_rgb: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        r = int(top_rgb[0] * (1 - t) + bot_rgb[0] * t)
        g = int(top_rgb[1] * (1 - t) + bot_rgb[1] * t)
        b = int(top_rgb[2] * (1 - t) + bot_rgb[2] * t)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))
    return img


def _draw_pill(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int] | tuple[int, int, int],
    text_fill: tuple[int, int, int],
    pad_x: int = 28,
    pad_y: int = 14,
) -> tuple[int, int, int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x0, y0 = xy
    box = (x0, y0, x0 + tw + pad_x * 2, y0 + th + pad_y * 2)
    draw.rounded_rectangle(box, radius=999, fill=fill)
    draw.text((x0 + pad_x - bbox[0], y0 + pad_y - bbox[1]), text, font=font, fill=text_fill)
    return box


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        cur = ""
        for word in words:
            candidate = f"{cur} {word}".strip() if cur else word
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if bbox[2] - bbox[0] <= max_w:
                cur = candidate
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
    return lines


def build_card_10k_to_6k(promo: str) -> Path:
    bg_src = RAW_DIR / "bag_editorial.jpg"
    img = _fit_cover(Image.open(bg_src).convert("RGB"), WIDTH, HEIGHT)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    # Soft top readability wash matching the studio mint background.
    for y in range(470):
        alpha = int(205 * (1 - y / 470) ** 1.3)
        odraw.line([(0, y), (WIDTH, y)], fill=(232, 248, 240, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    f_pill = _font(FONT_BOLD, 28)
    f_h1 = _font(FONT_BOLD, 74)
    f_sub = _font(FONT_SEMI if FONT_SEMI.exists() else FONT_REG, 34)

    _draw_pill(draw, (64, 58), "АЛМАТЫ И АСТАНА", f_pill, (12, 92, 58), (255, 255, 255))
    draw.text((64, 146), "Продукты на 10 000 ₸", font=f_h1, fill=(14, 34, 25))
    draw.text((64, 236), "всего за 6 000 ₸", font=f_h1, fill=(10, 128, 72))
    draw.text(
        (64, 340),
        f"Кешбэк 4 000 ₸ на первый заказ • Код: {promo}",
        font=f_sub,
        fill=(32, 60, 47),
    )

    out = ASSETS_DIR / "card-10k-to-6k.jpg"
    img.save(out, quality=92)
    return out


def build_card_lifestyle(promo: str) -> Path:
    bg_src = RAW_DIR / "countertop_editorial.jpg"
    img = _fit_cover(Image.open(bg_src).convert("RGB"), WIDTH, HEIGHT)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for y in range(520):
        alpha = int(215 * (1 - y / 520) ** 1.15)
        odraw.line([(0, y), (WIDTH, y)], fill=(10, 26, 19, alpha))
    for y in range(HEIGHT - 220, HEIGHT):
        alpha = int(210 * ((y - (HEIGHT - 220)) / 220))
        odraw.line([(0, y), (WIDTH, y)], fill=(10, 26, 19, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    f_pill = _font(FONT_BOLD, 28)
    f_h1 = _font(FONT_BOLD, 68)
    f_sub = _font(FONT_SEMI if FONT_SEMI.exists() else FONT_REG, 34)

    _draw_pill(draw, (64, 58), "КЕШБЭК +4 000 ₸", f_pill, (186, 255, 62), (10, 32, 20))
    draw.text((64, 146), "Закуп на неделю", font=f_h1, fill=(255, 255, 255))
    draw.text((64, 230), "на 40% дешевле", font=f_h1, fill=(186, 255, 62))
    draw.text(
        (64, 330),
        "Через Freedom SuperApp → Продукты (Arbuz)",
        font=f_sub,
        fill=(228, 240, 234),
    )
    _draw_pill(
        draw,
        (64, HEIGHT - 122),
        f"Алматы и Астана • Промокод: {promo}",
        _font(FONT_BOLD, 30),
        (14, 118, 72),
        (255, 255, 255),
    )

    out = ASSETS_DIR / "card-lifestyle-breakfast.jpg"
    img.save(out, quality=92)
    return out


def build_card_checklist(promo: str) -> Path:
    img = _gradient_bg((8, 44, 30), (13, 74, 49))
    draw = ImageDraw.Draw(img)

    f_pill = _font(FONT_BOLD, 26)
    f_h1 = _font(FONT_BOLD, 66)
    f_step_num = _font(FONT_BOLD, 34)
    f_step_title = _font(FONT_BOLD, 36)
    f_step_desc = _font(FONT_REG, 28)

    _draw_pill(draw, (64, 62), "ШПАРГАЛКА • АЛМАТЫ И АСТАНА", f_pill, (186, 255, 62), (10, 32, 20))
    draw.text((64, 142), "Как забрать 4 000 ₸", font=f_h1, fill=(255, 255, 255))
    draw.text((64, 222), "за первый заказ еды", font=f_h1, fill=(186, 255, 62))

    steps = [
        ("1", "Freedom SuperApp → Продукты", "Заходите через раздел «Сервисы», не напрямую на сайт."),
        ("2", "Корзина от 10 500 ₸ с запасом", "После сборки чек не должен упасть ниже 10 000 ₸."),
        ("3", "Включите «Заменять товар»", "Страховка, если какой-то позиции нет на складе."),
        ("4", f"Промокод {promo} + карта Freedom", "4 000 ₸ кешбэком придут после получения заказа."),
    ]

    y = 355
    for num, title, desc in steps:
        draw.rounded_rectangle((64, y, WIDTH - 64, y + 188), radius=28, fill=(18, 92, 62), outline=(45, 148, 102), width=2)
        draw.ellipse((94, y + 54, 174, y + 134), fill=(186, 255, 62))
        bbox = draw.textbbox((0, 0), num, font=f_step_num)
        nw, nh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((134 - nw // 2 - bbox[0], y + 94 - nh // 2 - bbox[1]), num, font=f_step_num, fill=(10, 32, 20))

        draw.text((206, y + 34), title, font=f_step_title, fill=(255, 255, 255))
        lines = _wrap_text(draw, desc, f_step_desc, WIDTH - 290)
        ly = y + 88
        for line in lines[:2]:
            draw.text((206, ly), line, font=f_step_desc, fill=(205, 232, 219))
            ly += 36
        y += 216

    draw.text(
        (64, HEIGHT - 90),
        "Только для новых пользователей Arbuz • Оплата картой Freedom",
        font=_font(FONT_REG, 27),
        fill=(182, 219, 201),
    )

    out = ASSETS_DIR / "card-checklist.jpg"
    img.save(out, quality=92)
    return out


def build_card_3_mistakes(promo: str) -> Path:
    img = _gradient_bg((26, 22, 25), (42, 25, 30))
    draw = ImageDraw.Draw(img)

    f_pill = _font(FONT_BOLD, 26)
    f_h1 = _font(FONT_BOLD, 64)
    f_title = _font(FONT_BOLD, 35)
    f_desc = _font(FONT_REG, 28)

    _draw_pill(draw, (64, 62), "НЕ ПОТЕРЯЙТЕ БОНУС", f_pill, (255, 193, 7), (25, 20, 15))
    draw.text((64, 142), "3 ошибки, из-за которых", font=f_h1, fill=(255, 255, 255))
    draw.text((64, 222), "не дают 4 000 ₸", font=f_h1, fill=(255, 107, 107))

    mistakes = [
        ("Уже был заказ на Arbuz.kz", "Акция работает только на первый заказ нового клиента в системе Arbuz."),
        ("Оплата картой другого банка", "Чтобы сработал кешбэк, оплачивать нужно строго картой Freedom."),
        ("Чек упал ниже 10 000 ₸ на сборке", "Нет товара -> сумма 9 700 ₸ -> бонус сгорает. Берите 10 500–11 000 ₸."),
    ]

    y = 360
    for idx, (title, desc) in enumerate(mistakes, start=1):
        draw.rounded_rectangle((64, y, WIDTH - 64, y + 230), radius=28, fill=(52, 34, 39), outline=(140, 66, 74), width=2)
        draw.ellipse((94, y + 75, 166, y + 147), fill=(255, 92, 92))
        draw.text((117, y + 86), "!", font=_font(FONT_BOLD, 42), fill=(255, 255, 255))
        draw.text((198, y + 40), f"{idx}. {title}", font=f_title, fill=(255, 255, 255))
        ly = y + 98
        for line in _wrap_text(draw, desc, f_desc, WIDTH - 290)[:3]:
            draw.text((198, ly), line, font=f_desc, fill=(228, 210, 214))
            ly += 38
        y += 260

    _draw_pill(
        draw,
        (64, HEIGHT - 134),
        f"Рабочий промокод для 1-го заказа: {promo}",
        _font(FONT_BOLD, 30),
        (16, 132, 82),
        (255, 255, 255),
    )

    out = ASSETS_DIR / "card-3-mistakes.jpg"
    img.save(out, quality=92)
    return out


def build_card_math_comparison(promo: str) -> Path:
    img = _gradient_bg((243, 247, 244), (225, 238, 230))
    draw = ImageDraw.Draw(img)

    f_pill = _font(FONT_BOLD, 26)
    f_h1 = _font(FONT_BOLD, 66)
    f_card_h = _font(FONT_BOLD, 36)
    f_big_num = _font(FONT_BOLD, 62)
    f_item = _font(FONT_REG, 30)

    _draw_pill(draw, (64, 62), "ПРОСТАЯ МАТЕМАТИКА КЗ", f_pill, (12, 92, 58), (255, 255, 255))
    draw.text((64, 142), "Один и тот же пакет", font=f_h1, fill=(14, 34, 25))
    draw.text((64, 222), "продуктов — две цены", font=f_h1, fill=(10, 128, 72))

    # Left card: Regular supermarket
    draw.rounded_rectangle((64, 360, 514, 1080), radius=34, fill=(255, 255, 255), outline=(212, 220, 216), width=3)
    draw.text((100, 412), "Магазин у дома", font=f_card_h, fill=(85, 95, 90))
    draw.text((100, 480), "10 500 ₸", font=f_big_num, fill=(45, 50, 48))
    draw.line([(100, 582), (478, 582)], fill=(230, 234, 232), width=2)
    for idx, line in enumerate(["Тащить пакеты самому", "Тратить время в очереди", "Кешбэк: ~100 ₸", "Итого: 10 400 ₸"]):
        draw.text((100, 626 + idx * 78), f"•  {line}", font=f_item, fill=(95, 102, 98))

    # Right card: Freedom Products
    draw.rounded_rectangle((566, 360, WIDTH - 64, 1080), radius=34, fill=(11, 78, 51), outline=(186, 255, 62), width=4)
    draw.text((602, 412), "Freedom Продукты", font=f_card_h, fill=(186, 255, 62))
    draw.text((602, 480), "6 500 ₸", font=f_big_num, fill=(255, 255, 255))
    draw.line([(602, 582), (WIDTH - 100, 582)], fill=(38, 122, 86), width=2)
    for idx, line in enumerate(["Доставка до двери", "Чек от 10 500 ₸", "Кешбэк: -4 000 ₸", "Итого: 6 500 ₸"]):
        color = (186, 255, 62) if idx >= 2 else (225, 244, 235)
        cy = 626 + idx * 78
        draw.ellipse((602, cy + 12, 620, cy + 30), fill=(186, 255, 62))
        draw.text((634, cy), line, font=f_item, fill=color)

    _draw_pill(
        draw,
        (64, 1148),
        f"Алматы и Астана • Промокод на 1-й заказ: {promo}",
        _font(FONT_BOLD, 30),
        (12, 92, 58),
        (255, 255, 255),
    )

    out = ASSETS_DIR / "card-math-comparison.jpg"
    img.save(out, quality=92)
    return out


def build_card_almaty_astana(promo: str) -> Path:
    img = _gradient_bg((7, 36, 25), (16, 104, 68))
    draw = ImageDraw.Draw(img)

    # Subtle decorative rings
    draw.ellipse((620, -140, 1220, 460), outline=(28, 138, 92), width=3)
    draw.ellipse((680, -80, 1160, 400), outline=(44, 166, 114), width=2)

    _draw_pill(draw, (64, 72), "АЛМАТЫ И АСТАНА", _font(FONT_BOLD, 28), (186, 255, 62), (10, 32, 20))
    draw.text((64, 178), "Кешбэк 4 000 ₸", font=_font(FONT_BOLD, 88), fill=(255, 255, 255))
    draw.text((64, 286), "на первый заказ", font=_font(FONT_BOLD, 74), fill=(186, 255, 62))
    draw.text((64, 376), "продуктов домой", font=_font(FONT_BOLD, 74), fill=(186, 255, 62))

    # Big center promo box
    draw.rounded_rectangle((64, 540, WIDTH - 64, 830), radius=36, fill=(11, 56, 38), outline=(186, 255, 62), width=4)
    draw.text((112, 584), "ПРОМОКОД В FREEDOM «ПРОДУКТЫ»:", font=_font(FONT_BOLD, 28), fill=(176, 224, 198))
    draw.text((112, 646), promo, font=_font(FONT_BOLD, 108), fill=(255, 255, 255))

    lines = [
        "1. Зайдите во Freedom SuperApp → Сервисы → Продукты",
        "2. Соберите корзину от 10 500 ₸ (с запасом)",
        "3. Примените код и оплатите картой Freedom",
    ]
    y = 920
    for line in lines:
        draw.text((64, y), line, font=_font(FONT_SEMI if FONT_SEMI.exists() else FONT_REG, 33), fill=(224, 245, 235))
        y += 68

    draw.text(
        (64, HEIGHT - 96),
        "Только для новых пользователей сервиса Arbuz",
        font=_font(FONT_REG, 28),
        fill=(165, 210, 188),
    )

    out = ASSETS_DIR / "card-almaty-astana.jpg"
    img.save(out, quality=92)
    return out


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    env = load_env(BASE_DIR / ".env")
    promo = env.get("PROMO_CODE", "CQACJ7LN").strip() or "CQACJ7LN"
    outputs = [
        build_card_10k_to_6k(promo),
        build_card_lifestyle(promo),
        build_card_checklist(promo),
        build_card_3_mistakes(promo),
        build_card_math_comparison(promo),
        build_card_almaty_astana(promo),
    ]
    for path in outputs:
        print(f"Generated: {path}")


if __name__ == "__main__":
    main()
