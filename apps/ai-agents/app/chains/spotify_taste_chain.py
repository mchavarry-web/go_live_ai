"""Spotify music-taste chain. Distills the user's top artists / top tracks
/ recently-played lists into a stable 'taste profile' (genre palette,
energy / valence preferences, and era affinity).
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TasteInsight(BaseModel):
    axis: str = Field(
        ...,
        description=(
            "genres | energy_preference | valence_preference | era_affinity | "
            "artist_loyalty"
        ),
    )
    value: str = Field(..., max_length=200)
    confidence: float = Field(..., ge=0.0, le=1.0)


class SpotifyTaste(BaseModel):
    taste: list[TasteInsight] = Field(default_factory=list)
    top_genres: list[str] = Field(default_factory=list)
    summary: str = Field(default="", max_length=500)


_SPOTIFY_TASTE_PROMPT = """\
Analiza la actividad musical del usuario en Spotify (top artists, top
tracks, recently played, playlists propias). Extrae un perfil de gusto
estable, no una lista de canciones.

Datos:
{payload}

Reglas:
- "top_genres": hasta 8 géneros dominantes por masa de escuchas.
- "taste": 4-8 observaciones por ejes (energía: high/low; valence:
  positiva/negativa; era: nuevo/clásico; lealtad de artistas).
- "summary": 2-3 frases que capturen el ánimo musical del usuario.

{format_instructions}
"""


class SpotifyTasteChain:
    def __init__(self, llm: BaseChatModel) -> None:
        self._parser = PydanticOutputParser(pydantic_object=SpotifyTaste)
        prompt = ChatPromptTemplate.from_template(
            _SPOTIFY_TASTE_PROMPT,
            partial_variables={"format_instructions": self._parser.get_format_instructions()},
        )
        self._chain = prompt | llm | self._parser

    @traceable(name="spotify_taste_chain.extract")
    async def extract(self, payload: dict[str, object]) -> SpotifyTaste:
        return await self._chain.ainvoke({"payload": payload})
