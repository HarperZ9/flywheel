from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBudget:
    characters: int
    estimated_tokens: int
    max_tokens: int
    ratio: float
    status: str

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "characters": self.characters,
            "estimated_tokens": self.estimated_tokens,
            "max_tokens": self.max_tokens,
            "ratio": self.ratio,
            "status": self.status,
        }


def estimate_context(text: str, max_tokens: int = 8000) -> ContextBudget:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")

    characters = len(text)
    estimated_tokens = max(1, round(characters / 4)) if characters else 0
    ratio = estimated_tokens / max_tokens

    if ratio >= 1:
        status = "over"
    elif ratio >= 0.75:
        status = "warn"
    else:
        status = "fits"

    return ContextBudget(
        characters=characters,
        estimated_tokens=estimated_tokens,
        max_tokens=max_tokens,
        ratio=round(ratio, 4),
        status=status,
    )
