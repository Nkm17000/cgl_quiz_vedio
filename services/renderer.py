import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config import ASSETS_DIR, VIDEO_HEIGHT, VIDEO_WIDTH

DEVANAGARI_RE = re.compile(r"[\u0900-\u097F\u1CD0-\u1CFF\uA8E0-\uA8FF]")
FONT_EN = ASSETS_DIR / "fonts" / "DejaVuSans.ttf"
FONT_EN_BOLD = ASSETS_DIR / "fonts" / "DejaVuSans-Bold.ttf"
FONT_HI = ASSETS_DIR / "fonts" / "NotoSansDevanagari-Regular.ttf"

_BG_CACHE = {}
_LOGO = None


def _font(size: int, bold: bool = False, hindi: bool = False):
    candidates = []
    if hindi:
        candidates = [FONT_HI, Path("/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.ttf")]
    else:
        candidates = [FONT_EN_BOLD if bold else FONT_EN]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.RAQM)
            except Exception:
                return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


# Each subject has its own visual identity.  Colors are deliberately chosen as
# coordinated pairs/triples so the background, headings, cards and accents stay
# readable on a vertical 720x1280 canvas.
THEMES = {
    "ENGLISH": {
        "name": "ENGLISH",
        "top": (20, 14, 52), "bottom": (74, 32, 105),
        "accent": (255, 122, 89), "accent2": (255, 190, 92),
        "card": (42, 28, 73), "card_outline": (255, 142, 103),
        "text": (255, 250, 244), "muted": (231, 214, 250),
        "question": (255, 255, 255), "footer": (255, 205, 155),
    },
    "GENERAL SCIENCE": {
        "name": "GENERAL SCIENCE",
        "top": (4, 36, 46), "bottom": (8, 105, 94),
        "accent": (55, 224, 184), "accent2": (157, 245, 211),
        "card": (10, 62, 66), "card_outline": (61, 224, 188),
        "text": (239, 255, 251), "muted": (185, 235, 225),
        "question": (250, 255, 253), "footer": (158, 245, 218),
    },
    "GK": {
        "name": "GK",
        "top": (28, 18, 48), "bottom": (91, 48, 24),
        "accent": (255, 194, 61), "accent2": (255, 226, 126),
        "card": (55, 36, 52), "card_outline": (238, 171, 58),
        "text": (255, 250, 232), "muted": (244, 218, 160),
        "question": (255, 252, 240), "footer": (255, 220, 135),
    },
    "MATH": {
        "name": "MATH",
        "top": (10, 24, 64), "bottom": (25, 66, 128),
        "accent": (255, 116, 74), "accent2": (255, 185, 102),
        "card": (20, 48, 91), "card_outline": (255, 126, 82),
        "text": (242, 248, 255), "muted": (190, 215, 250),
        "question": (255, 255, 255), "footer": (255, 188, 120),
    },
    "REASONING": {
        "name": "REASONING",
        "top": (50, 12, 39), "bottom": (113, 34, 75),
        "accent": (62, 224, 210), "accent2": (140, 245, 229),
        "card": (70, 25, 61), "card_outline": (67, 221, 207),
        "text": (255, 245, 250), "muted": (244, 190, 222),
        "question": (255, 255, 255), "footer": (139, 243, 227),
    },
    "ALL SUBJECTS": {
        "name": "ALL SUBJECTS",
        "top": (12, 19, 37), "bottom": (54, 35, 88),
        "accent": (83, 189, 255), "accent2": (196, 116, 255),
        "card": (30, 34, 66), "card_outline": (91, 190, 255),
        "text": (245, 248, 255), "muted": (203, 211, 238),
        "question": (255, 255, 255), "footer": (184, 207, 255),
    },
}

DEFAULT_THEME = THEMES["ALL SUBJECTS"]


def _theme(subject=None):
    key = str(subject or "ALL SUBJECTS").strip().upper()
    return THEMES.get(key, DEFAULT_THEME)


def _background(subject=None):
    key = str(subject or "ALL SUBJECTS").strip().upper()
    if key in _BG_CACHE:
        return _BG_CACHE[key].copy().convert("RGBA")

    theme = _theme(key)
    image = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), theme["top"] + (255,))
    px = image.load()
    top, bottom = theme["top"], theme["bottom"]

    # Smooth vertical gradient.
    for y in range(VIDEO_HEIGHT):
        ratio = y / max(1, VIDEO_HEIGHT - 1)
        color = tuple(int(top[i] * (1 - ratio) + bottom[i] * ratio) for i in range(3)) + (255,)
        for x in range(VIDEO_WIDTH):
            px[x, y] = color

    draw = ImageDraw.Draw(image, "RGBA")
    accent = theme["accent"]
    accent2 = theme["accent2"]

    # Soft corner geometry gives each subject a recognizable visual identity
    # while deliberately staying away from the learner-facing text regions.
    # No diagonal/cross lines and no inner frame are used.
    draw.ellipse((-250, -190, 210, 270), fill=accent + (24,))
    draw.ellipse((VIDEO_WIDTH - 190, -80, VIDEO_WIDTH + 170, 280), fill=accent2 + (20,))
    draw.ellipse((-190, VIDEO_HEIGHT - 190, 150, VIDEO_HEIGHT + 170), fill=accent2 + (16,))
    draw.ellipse((VIDEO_WIDTH - 135, VIDEO_HEIGHT - 165, VIDEO_WIDTH + 120, VIDEO_HEIGHT + 80), fill=accent + (14,))
    _BG_CACHE[key] = image.copy()
    return image.convert("RGBA")

def _logo():
    global _LOGO
    if _LOGO is not None:
        return _LOGO

    source = Image.open(ASSETS_DIR / "logo.png").convert("RGBA")
    # Crop the original white margin before fitting the mark into a circle.
    source = source.crop((90, 25, 380, 315))
    source.thumbnail((204, 204), Image.Resampling.LANCZOS)

    size = 230
    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse((8, 10, size - 2, size - 2), fill=(0, 0, 0, 90))
    badge.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(7)))

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((1, 1, size - 2, size - 2), fill=255)
    white = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    white.putalpha(mask)
    badge.alpha_composite(white)

    x = (size - source.width) // 2
    y = (size - source.height) // 2
    source_mask = Image.new("L", source.size, 0)
    ImageDraw.Draw(source_mask).ellipse((0, 0, source.width - 1, source.height - 1), fill=255)
    source.putalpha(source_mask)
    badge.alpha_composite(source, (x, y))
    _LOGO = badge
    return _LOGO


def _parts(value):
    if isinstance(value, dict):
        return str(value.get("en", "")).strip(), str(value.get("hi", "")).strip()
    return str(value or "").strip(), ""


def _question_parts(q):
    return _parts(q.get("question", ""))


def _option_parts(value):
    """Normalize one option into (English, Hindi).

    Supported dataset shapes:
      1. {"en": "English", "hi": "Hindi"}
      2. "English"
    """
    return _parts(value)


def _normalize_options(value, limit=4):
    """Normalize all supported quiz option shapes to a list of option objects.

    Current question datasets use two schemas:
      - {"en": ["A", "B"], "hi": ["अ", "ब"]}
      - [{"en": "A", "hi": "अ"}, {"en": "B", "hi": "ब"}]

    The renderer should consume either shape without making assumptions about
    the source JSON format.
    """
    if value is None:
        return []

    # Schema: {"en": [...], "hi": [...]}
    if isinstance(value, dict):
        en_values = value.get("en", [])
        hi_values = value.get("hi", [])

        if isinstance(en_values, (list, tuple)):
            en_values = list(en_values)
        else:
            en_values = [en_values] if en_values not in (None, "") else []

        if isinstance(hi_values, (list, tuple)):
            hi_values = list(hi_values)
        else:
            hi_values = [hi_values] if hi_values not in (None, "") else []

        count = max(len(en_values), len(hi_values))
        normalized = []
        for i in range(count):
            normalized.append({
                "en": en_values[i] if i < len(en_values) else "",
                "hi": hi_values[i] if i < len(hi_values) else "",
            })
        return normalized[:limit]

    # Schema: [{"en": "...", "hi": "..."}, ...] or ["...", ...]
    if isinstance(value, (list, tuple)):
        return list(value[:limit])

    # Defensive fallback for malformed data.
    return [value]


def _get_options(q, limit=4):
    if not isinstance(q, dict):
        return []
    return _normalize_options(q.get("options"), limit=limit)


def _is_hindi(text):
    return bool(DEVANAGARI_RE.search(str(text or "")))


def _runs(text):
    """Split text into Unicode-script runs so mixed Hindi + English works.

    Hindi/Devanagari runs use Noto Sans Devanagari, while Latin/number/punctuation
    runs use DejaVu Sans. This must be used for every learner-visible string;
    forcing an entire mixed string through an English-only font creates tofu boxes.
    """
    text = str(text or "").replace("\r", "").strip()
    if not text:
        return []
    result = []
    current = ""
    state = None
    for ch in text:
        if ch.isspace():
            current += ch
            continue
        hindi = _is_hindi(ch)
        if state is None:
            state = hindi
        elif hindi != state:
            if current:
                result.append((current, state))
            current, state = "", hindi
        current += ch
    if current:
        result.append((current, bool(state)))
    return result


def _width(draw, text, size, bold=False, force_hindi=None):
    if force_hindi is not None:
        font = _font(size, bold=bold, hindi=force_hindi)
        box = draw.textbbox((0, 0), text, font=font)
        return box[2] - box[0]
    return sum(draw.textlength(run, font=_font(size, bold=bold, hindi=hindi)) for run, hindi in _runs(text))


def _wrap(draw, text, size, max_width, bold=False, force_hindi=None):
    words = re.findall(r"\S+|\s+", str(text or "").strip())
    lines, line = [], ""
    for token in words:
        if token.isspace():
            if line:
                line += " "
            continue
        candidate = token if not line else f"{line.rstrip()} {token}"
        if _width(draw, candidate, size, bold, force_hindi) <= max_width:
            line = candidate
            continue
        if line.strip():
            lines.append(line.strip())
            line = ""
        if _width(draw, token, size, bold, force_hindi) <= max_width:
            line = token
        else:
            chunk = ""
            for char in token:
                candidate = chunk + char
                if chunk and _width(draw, candidate, size, bold, force_hindi) > max_width:
                    lines.append(chunk)
                    chunk = char
                else:
                    chunk = candidate
            line = chunk
    if line.strip():
        lines.append(line.strip())
    return lines


def _draw_line(draw, text, y, box, size, fill, bold=False, align="center", force_hindi=None):
    left, _, right, _ = box
    runs = [(str(text), force_hindi)] if force_hindi is not None else _runs(text)
    metrics = []
    total = 0
    for run, hindi in runs:
        font = _font(size, bold=bold, hindi=bool(hindi))
        width = draw.textlength(run, font=font)
        bbox = draw.textbbox((0, 0), run, font=font)
        metrics.append((run, font, width, bbox))
        total += width
    if align == "left":
        x = left
    elif align == "right":
        x = right - total
    else:
        x = left + (right - left - total) / 2
    baseline = y + max(item[3][3] for item in metrics)
    for run, font, width, bbox in metrics:
        draw.text((x, baseline - bbox[3]), run, font=font, fill=fill)
        x += width


def _draw_fit(draw, text, box, fill, start, minimum, bold=False, force_hindi=None, gap=5, align="center"):
    left, top, right, bottom = box
    for size in range(start, minimum - 1, -1):
        lines = _wrap(draw, text, size, right - left, bold, force_hindi)
        line_height = max(1, int(size * 1.18))
        needed = len(lines) * line_height + max(0, len(lines) - 1) * gap
        if needed <= bottom - top:
            y = top
            for line in lines:
                _draw_line(draw, line, y, box, size, fill, bold, align, force_hindi)
                y += line_height + gap
            return y
    return top


def _draw_logo(image, y):
    logo = _logo()
    image.alpha_composite(logo, ((VIDEO_WIDTH - logo.width) // 2, y))


def _draw_option(draw, y, index, en, hi, height, theme, correct=False):
    """Draw one option card with a clear gap between marker and text."""
    box = (58, y, VIDEO_WIDTH - 58, y + height)
    if correct:
        fill = theme["accent"] + (242,)
        outline = theme["accent2"] + (255,)
        main_fill = (18, 24, 31, 255)
        hi_fill = (30, 38, 45, 255)
    else:
        fill = theme["card"] + (242,)
        outline = theme["card_outline"] + (235,)
        main_fill = theme["text"] + (255,)
        hi_fill = theme["muted"] + (255,)

    draw.rounded_rectangle(box, radius=22, fill=fill, outline=outline, width=3)

    # The old text x-position (105) overlapped the A/B/C/D marker. Keep a
    # consistent visual gap of ~14 px after the marker on every option.
    marker_left = 76
    marker_size = 40
    marker_cx = marker_left + marker_size // 2
    marker_cy = y + height // 2
    draw.ellipse(
        (marker_left, marker_cy - marker_size // 2,
         marker_left + marker_size, marker_cy + marker_size // 2),
        fill=outline,
    )
    marker_font = _font(19, bold=True)
    draw.text(
        (marker_cx, marker_cy),
        chr(65 + index),
        font=marker_font,
        fill=main_fill,
        anchor="mm",
    )

    text_left = 130
    text_right = VIDEO_WIDTH - 78
    inner_top = y + 9
    inner_bottom = y + height - 8

    # Allocate space based on whether a Hindi line exists. This prevents the
    # English and Hindi lines from touching or clipping on short cards.
    if hi and hi.casefold() != str(en).casefold():
        english_bottom = y + int(height * 0.57)
        _draw_fit(
            draw,
            str(en),
            (text_left, inner_top, text_right, english_bottom),
            main_fill,
            29,
            17,
            bold=correct,
            gap=1,
            align="left",
            force_hindi=None,
        )
        _draw_fit(
            draw,
            str(hi),
            (text_left, english_bottom + 1, text_right, inner_bottom),
            hi_fill,
            21,
            13,
            gap=1,
            align="left",
            force_hindi=None,
        )
    else:
        _draw_fit(
            draw,
            str(en),
            (text_left, inner_top, text_right, inner_bottom),
            main_fill,
            29,
            17,
            bold=correct,
            gap=1,
            align="left",
            force_hindi=None,
        )


def _option_layout(start_y, bottom_y, count=4, preferred_height=108, gap=10, minimum_height=78):
    """Calculate a guaranteed on-screen option layout."""
    if count <= 0:
        return start_y, 0, 0

    available = max(0, bottom_y - start_y)
    if count == 1:
        return start_y, min(preferred_height, available), 0

    max_height = (available - gap * (count - 1)) // count
    height = min(preferred_height, max_height)
    if height < minimum_height:
        height = max(1, max_height)
    return start_y, height, gap


def render_question(q, index, timer, output, subject=None):
    theme = _theme(subject)
    image = _background(subject)
    draw = ImageDraw.Draw(image, "RGBA")
    _draw_logo(image, 70 if timer is None else 85)

    if timer is not None:
        draw.text(
            (VIDEO_WIDTH // 2, 325),
            str(timer),
            font=_font(68, bold=True),
            fill=theme["accent2"],
            anchor="mm",
        )

    en, hi = _question_parts(q)

    # Compact question block leaves a predictable, comfortable region for all
    # four options. No decorative lines or frame are drawn over this area.
    question_top = 385 if timer is None else 405
    question_bottom = 585
    y = _draw_fit(
        draw,
        f"Q{index + 1}. {en}",
        (52, question_top, VIDEO_WIDTH - 52, question_bottom),
        theme["question"],
        45,
        25,
        bold=True,
        gap=5,
        align="center",
        force_hindi=None,
    )

    if hi:
        _draw_fit(
            draw,
            hi,
            (62, min(question_bottom + 6, y + 5), VIDEO_WIDTH - 62, 665),
            theme["muted"],
            28,
            18,
            gap=3,
            align="center",
            force_hindi=None,
        )

    options = _get_options(q, 4)
    option_start = 690
    option_bottom = VIDEO_HEIGHT - 105
    option_start, option_height, option_gap = _option_layout(
        option_start,
        option_bottom,
        count=len(options),
        preferred_height=108,
        gap=11,
        minimum_height=78,
    )

    for i, option in enumerate(options):
        en_opt, hi_opt = _option_parts(option)
        _draw_option(
            draw,
            option_start + i * (option_height + option_gap),
            i,
            en_opt,
            hi_opt,
            option_height,
            theme,
        )

    draw.text(
        (VIDEO_WIDTH // 2, VIDEO_HEIGHT - 42),
        "Comment your answer!",
        font=_font(23, bold=True),
        fill=theme["accent2"],
        anchor="mm",
    )
    image.convert("RGB").save(output, quality=92, optimize=True)


def _draw_explanation(draw, exp_en, exp_hi, top, bottom, theme):
    """Draw a high-contrast explanation panel with enough room for both scripts."""
    if not (exp_en or exp_hi) or bottom <= top + 35:
        return

    # High-contrast panel: use the theme's darkest card tone and a bright
    # accent border, rather than the previous near-black/brown combination.
    panel = tuple(max(0, int(c * 0.70)) for c in theme["card"])
    draw.rounded_rectangle(
        (48, top, VIDEO_WIDTH - 48, bottom),
        radius=20,
        fill=panel + (250,),
        outline=theme["accent2"] + (245,),
        width=3,
    )

    label_y = top + 13
    draw.rounded_rectangle(
        (66, label_y, 215, label_y + 30),
        radius=12,
        fill=theme["accent2"] + (235,),
    )
    draw.text(
        (140, label_y + 15),
        "EXPLANATION",
        font=_font(14, bold=True),
        fill=theme["card"] + (255,),
        anchor="mm",
    )

    content_top = top + 49
    if exp_en and exp_hi:
        split = content_top + int((bottom - content_top) * 0.56)
        _draw_fit(
            draw,
            exp_en,
            (72, content_top, VIDEO_WIDTH - 72, split),
            theme["text"],
            22,
            14,
            bold=True,
            gap=2,
            align="left",
            force_hindi=None,
        )
        _draw_fit(
            draw,
            exp_hi,
            (72, split + 2, VIDEO_WIDTH - 72, bottom - 12),
            theme["muted"],
            19,
            13,
            gap=2,
            align="left",
            force_hindi=None,
        )
    elif exp_en:
        _draw_fit(
            draw,
            exp_en,
            (72, content_top, VIDEO_WIDTH - 72, bottom - 12),
            theme["text"],
            22,
            14,
            bold=True,
            gap=2,
            align="left",
            force_hindi=None,
        )
    else:
        _draw_fit(
            draw,
            exp_hi,
            (72, content_top, VIDEO_WIDTH - 72, bottom - 12),
            theme["muted"],
            20,
            13,
            gap=2,
            align="left",
            force_hindi=None,
        )


def render_answer(q, index, output, subject=None):
    theme = _theme(subject)
    image = _background(subject)
    draw = ImageDraw.Draw(image, "RGBA")
    _draw_logo(image, 45)

    en, hi = _question_parts(q)
    draw.text(
        (VIDEO_WIDTH // 2, 265),
        f"ANSWER — Q{index + 1}",
        font=_font(31, bold=True),
        fill=theme["accent2"],
        anchor="mm",
    )

    y = _draw_fit(
        draw,
        en,
        (48, 300, VIDEO_WIDTH - 48, 445),
        theme["question"],
        38,
        25,
        bold=True,
        gap=4,
        force_hindi=None,
    )
    if hi:
        y = _draw_fit(
            draw,
            hi,
            (58, min(455, y + 4), VIDEO_WIDTH - 58, 510),
            theme["muted"],
            25,
            17,
            gap=3,
            force_hindi=None,
        )

    options = _get_options(q, 4)

    # Reserve the bottom portion for the explanation first. This is the key
    # change: explanation is never allowed to be pushed under the app's lower
    # chrome by the option cards.
    explanation = q.get("explanation", "")
    exp_en, exp_hi = _parts(explanation)
    has_explanation = bool(exp_en or exp_hi)

    footer_y = VIDEO_HEIGHT - 36
    explanation_bottom = 1138 if has_explanation else 1185
    option_start = 535
    option_bottom = 1090 if has_explanation else 1170

    option_start, option_height, option_gap = _option_layout(
        option_start,
        option_bottom,
        count=len(options),
        preferred_height=112,
        gap=10,
        minimum_height=76,
    )

    oy = option_start
    for i, option in enumerate(options):
        en_opt, hi_opt = _option_parts(option)
        _draw_option(
            draw,
            oy,
            i,
            en_opt,
            hi_opt,
            option_height,
            theme,
            correct=(i == q.get("answer_index")),
        )
        oy += option_height + option_gap

    if has_explanation:
        exp_top = min(explanation_bottom - 120, oy + 12)
        # Never allow the panel to collide with the footer.
        exp_bottom = min(explanation_bottom, max(exp_top + 90, 1138))
        if exp_bottom > exp_top + 35:
            _draw_explanation(draw, exp_en, exp_hi, exp_top, exp_bottom, theme)

    draw.text(
        (VIDEO_WIDTH // 2, footer_y),
        "By Nitin Mittal Innovations",
        font=_font(18, bold=True),
        fill=theme["footer"],
        anchor="mm",
    )
    image.convert("RGB").save(output, quality=92, optimize=True)
