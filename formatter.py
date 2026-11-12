import html
import re


def markdown_to_telegram_html(text: str) -> str:
    """Gemini qaytargan Markdown matnini Telegram uchun chiroyli va xavfsiz HTML formatga o'tkazadi."""
    if not text:
        return ""

    # 1. Ko'p qatorli kod bloklarini (```...```) ajratib olamiz
    code_blocks = []

    def replace_code_block(match):
        code = match.group(1)
        # Kod ichidagi <, >, & belgilarni HTML escape qilamiz
        escaped_code = html.escape(code.strip("\n"), quote=False)
        idx = len(code_blocks)
        code_blocks.append(f"<pre><code>{escaped_code}</code></pre>")
        return f"%%TG_CODE_BLOCK_{idx}%%"

    text = re.sub(
        r"```(?:[a-zA-Z0-9_\-\+]+)?\n?(.*?)```",
        replace_code_block,
        text,
        flags=re.DOTALL,
    )

    # 2. Qator ichidagi kodlarni (`code`) ajratib olamiz
    inline_codes = []

    def replace_inline_code(match):
        code = match.group(1)
        escaped_code = html.escape(code, quote=False)
        idx = len(inline_codes)
        inline_codes.append(f"<code>{escaped_code}</code>")
        return f"%%TG_INLINE_CODE_{idx}%%"

    text = re.sub(r"`([^`\n]+)`", replace_inline_code, text)

    # 3. Asosiy matndagi HTML belgilarni xavfsiz holatga keltiramiz (&, <, >)
    # quote=False o'zbek tilidagi tutuq belgilari (o'zbek, bo'lsa) saqlanib qolishi uchun
    text = html.escape(text, quote=False)

    # 4. Sarlavhalarni qalin matnga aylantirish (# Sarlavha -> <b>Sarlavha</b>)
    text = re.sub(r"(?m)^#{1,6}\s+(.+)$", r"<b>\1</b>", text)

    # 5. Qalin va kursiv (***matn***) -> <b><i>matn</i></b>
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", text)

    # 6. Qalin (**matn**) -> <b>matn</b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # 7. Kursiv (*matn* yoki _matn_) -> <i>matn</i>
    text = re.sub(r"(?<!\w)\*([^\*\n]+?)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"<i>\1</i>", text)

    # 8. Ro'yxat belgilari (* element yoki - element -> • element)
    text = re.sub(r"(?m)^[\*\-]\s+(.+)$", r"• \1", text)

    # 9. Adashgan, yopilmagan yoki 2 tadan ko'p ortiqcha yulduzchalarni tozalash (*** yoki **** kabi)
    text = re.sub(r"\*{2,}", "", text)

    # 10. Saqlangan kod bloklarini o'z joyiga qaytaramiz
    for idx, block in enumerate(code_blocks):
        text = text.replace(f"%%TG_CODE_BLOCK_{idx}%%", block)

    for idx, inline in enumerate(inline_codes):
        text = text.replace(f"%%TG_INLINE_CODE_{idx}%%", inline)

    return text.strip()


def strip_html_tags(text: str) -> str:
    """Xatolik yuz berganda barcha HTML teglarni tozalab, sof xavfsiz matn qaytaradi."""
    clean = re.sub(r"<[^>]+>", "", text)
    return html.unescape(clean)
