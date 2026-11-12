import logging
import openpyxl
import docx

logger = logging.getLogger(__name__)


def extract_text_from_docx(file_path: str) -> str:
    """DOCX faylidan barcha matn va jadvallarni ajratib oladi."""
    doc = docx.Document(file_path)
    lines = []

    # Paragraflarni olish
    for p in doc.paragraphs:
        t = p.text.strip()
        if t:
            lines.append(t)

    # Jadvallarni olish
    for table in doc.tables:
        lines.append("\n[Jadval]:")
        for row in table.rows:
            row_text = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            lines.append(" | ".join(row_text))

    return "\n\n".join(lines)


def extract_text_from_excel(file_path: str) -> str:
    """Excel (XLSX) faylidan sahifalar va kataklar ma'lumotlarini matn shaklida oladi."""
    wb = openpyxl.load_workbook(file_path, data_only=True)
    lines = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        lines.append(f"\n--- Sahifa: {sheet_name} ---")

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue

        for row in rows:
            # Bo'sh bo'lmagan qatorlarni formatlaymiz
            non_empty = [str(cell).strip() if cell is not None else "" for cell in row]
            if any(non_empty):
                lines.append(" | ".join(non_empty))

    return "\n".join(lines)


def extract_text_from_plain_text(file_path: str) -> str:
    """TXT, CSV, JSON va boshqa matnli fayllarni o'qish."""
    encodings = ["utf-8", "utf-16", "windows-1251", "latin-1"]
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise ValueError("Matnli fayl kodirovkasini aniqlab bo'lmadi.")
