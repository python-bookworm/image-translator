from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TextRegion:
    id: str
    polygon: np.ndarray
    text: str
    score: float


@dataclass(frozen=True)
class TranslatedRegion:
    source: TextRegion
    translated_text: str

