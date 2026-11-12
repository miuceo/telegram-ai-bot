import logging
import httpx
from lxml import html

logger = logging.getLogger(__name__)

SEARCH_KEYWORDS = [
    "bugun", "kecha", "ertaga", "hozir", "ob-havo", "kurs", "dollar", "valyuta",
    "yangilik", "narx", "narxi", "qachon", "qayerda", "kim", "internet", "qidir",
    "so'nggi", "oxirgi", "prezident", "futbol", "match", "natija", "2024", "2025", "2026"
]


def needs_web_search(prompt: str) -> bool:
    """Foydalanuvchi savoli internetdan yangi ma'lumot qidirishni talab qiladimi-yo'qligini aniqlaydi."""
    lower_text = prompt.lower()
    for kw in SEARCH_KEYWORDS:
        if kw in lower_text:
            return True
    return False


async def search_internet(query: str, max_results: int = 4) -> str:
    """DuckDuckGo Lite orqali internetdan real vaqtda ma'lumot qidiradi."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            resp = await client.post(
                "https://lite.duckduckgo.com/lite/",
                data={"q": query},
                headers=headers,
            )

            if resp.status_code != 200:
                logger.warning(f"Qidiruv xizmati kodi: {resp.status_code}")
                return ""

            tree = html.fromstring(resp.text)
            links = tree.xpath("//a[@class='result-link']")
            snippets = tree.xpath("//td[@class='result-snippet']")

            results = []
            for l, s in zip(links[:max_results], snippets[:max_results]):
                title = "".join(l.xpath(".//text()")).strip()
                snippet = "".join(s.xpath(".//text()")).strip()
                if title and snippet:
                    results.append(f"• {title}: {snippet}")

            if not results:
                return ""

            return "\n".join(results)

    except Exception as e:
        logger.warning(f"Internet qidiruvida xatolik: {e}")
        return ""
