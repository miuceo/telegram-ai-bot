from dataclasses import dataclass, field
from google.genai import types

MIN_MEMORY_LIMIT = 20
MAX_MEMORY_LIMIT = 50


@dataclass
class ChatTurn:
    role: str  # "user" yoki "model"
    text: str


class MemoryManager:
    """Foydalanuvchilarning muloqot xotirasini boshqaruvchi tizim.
    
    Har bir foydalanuvchi uchun xabarlarni saqlaydi (eng kami 20 ta, eng ko'pi 50 ta).
    Xotira 50 tadan oshganda, eng eski xabarlar ketma-ketlik buzilmagan holda tozalanadi.
    """

    def __init__(
        self,
        min_limit: int = MIN_MEMORY_LIMIT,
        max_limit: int = MAX_MEMORY_LIMIT,
    ):
        self.min_limit = min_limit
        self.max_limit = max_limit
        # user_id -> list[ChatTurn]
        self._storage: dict[int, list[ChatTurn]] = {}

    def get_user_turns(self, user_id: int) -> list[ChatTurn]:
        return self._storage.setdefault(user_id, [])

    def add_user_message(self, user_id: int, text: str):
        turns = self.get_user_turns(user_id)
        turns.append(ChatTurn(role="user", text=text))
        self._prune(user_id)

    def add_model_message(self, user_id: int, text: str):
        turns = self.get_user_turns(user_id)
        turns.append(ChatTurn(role="model", text=text))
        self._prune(user_id)

    def _prune(self, user_id: int):
        """Xotira hajmi max_limit dan oshsa, eng eski xabarlarni tozalaydi."""
        turns = self.get_user_turns(user_id)
        if len(turns) > self.max_limit:
            # Eng so'nggi max_limit ta xabarni qoldiramiz
            turns = turns[-self.max_limit :]

            # Gemini API da xabarlar tarixi doimo "user" roli bilan boshlanishi shart!
            while turns and turns[0].role != "user":
                turns.pop(0)

            self._storage[user_id] = turns

    def get_contents_for_gemini(self, user_id: int) -> list[types.Content]:
        """Gemini API ga uzatish uchun types.Content ro'yxatini shakllantiradi."""
        turns = self.get_user_turns(user_id)
        contents: list[types.Content] = []
        for turn in turns:
            contents.append(
                types.Content(
                    role=turn.role,
                    parts=[types.Part.from_text(text=turn.text)],
                )
            )
        return contents

    def clear_memory(self, user_id: int):
        """Foydalanuvchining barcha xabarlar tarixini tozalaydi."""
        self._storage[user_id] = []

    def get_memory_status(self, user_id: int) -> dict:
        """Xotira to'lganlik holati haqida batafsil ma'lumot beradi."""
        turns = self.get_user_turns(user_id)
        total = len(turns)
        user_msgs = sum(1 for t in turns if t.role == "user")
        model_msgs = sum(1 for t in turns if t.role == "model")
        percentage = round((total / self.max_limit) * 100, 1) if self.max_limit > 0 else 0

        # Vizual progress bar (masalan: [██████░░░░])
        filled_slots = int(total / self.max_limit * 10)
        empty_slots = 10 - filled_slots
        progress_bar = "█" * filled_slots + "░" * empty_slots

        return {
            "total": total,
            "min_limit": self.min_limit,
            "max_limit": self.max_limit,
            "user_msgs": user_msgs,
            "model_msgs": model_msgs,
            "percentage": percentage,
            "is_full": total >= self.max_limit,
            "progress_bar": f"[{progress_bar}] {percentage}%",
        }
