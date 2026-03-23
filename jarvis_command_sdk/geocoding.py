"""GeocodingHelper — resolve fuzzy location strings to coordinates.

Provides a simple interface for commands that need geocoding (weather,
local search, navigation, etc.). Uses OpenStreetMap Nominatim by default
(no API key required). Supports optional Google Maps backend.

Usage:
    from jarvis_command_sdk import GeocodingHelper

    geo = GeocodingHelper()
    result = await geo.resolve("downtown Seattle")
    # → GeocodingResult(lat=47.6062, lon=-122.3321, display_name="Downtown, Seattle, WA")

    # With Google Maps backend
    geo = GeocodingHelper(provider="google", api_key="...")
    result = await geo.resolve("near the Space Needle")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GeocodingResult:
    """A resolved location with coordinates and display name."""

    lat: float
    lon: float
    display_name: str
    raw: dict[str, Any] | None = None

    @property
    def coords(self) -> tuple[float, float]:
        """Return (latitude, longitude) tuple."""
        return (self.lat, self.lon)


class GeocodingHelper:
    """Resolve fuzzy location strings to coordinates.

    Args:
        provider: "nominatim" (default, no API key) or "google" (requires api_key).
        api_key: API key for Google Maps Geocoding API (ignored for nominatim).
        user_agent: User-Agent for Nominatim requests (required by their ToS).
        default_region: Optional region bias (e.g., "us", "gb") for better results.
    """

    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    GOOGLE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

    def __init__(
        self,
        provider: str = "nominatim",
        api_key: str | None = None,
        user_agent: str = "jarvis-assistant/1.0",
        default_region: str | None = None,
    ) -> None:
        self._provider = provider
        self._api_key = api_key
        self._user_agent = user_agent
        self._default_region = default_region

    async def resolve(self, query: str) -> GeocodingResult | None:
        """Resolve a location string to coordinates.

        Args:
            query: Fuzzy location string (e.g., "downtown", "near the park",
                   "123 Main St", "Paris, France").

        Returns:
            GeocodingResult with lat/lon/display_name, or None if not found.
        """
        if not query or not query.strip():
            return None

        if self._provider == "google" and self._api_key:
            return await self._resolve_google(query)
        return await self._resolve_nominatim(query)

    async def resolve_batch(self, queries: list[str]) -> list[GeocodingResult | None]:
        """Resolve multiple locations. Returns results in same order as queries."""
        import asyncio
        return await asyncio.gather(*(self.resolve(q) for q in queries))

    async def _resolve_nominatim(self, query: str) -> GeocodingResult | None:
        """Resolve via OpenStreetMap Nominatim (free, no API key)."""
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx is required for geocoding. Install: pip install httpx")

        params: dict[str, str] = {
            "q": query,
            "format": "json",
            "limit": "1",
            "addressdetails": "1",
        }
        if self._default_region:
            params["countrycodes"] = self._default_region

        headers = {"User-Agent": self._user_agent}

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(self.NOMINATIM_URL, params=params, headers=headers)
            resp.raise_for_status()
            results = resp.json()

        if not results:
            return None

        hit = results[0]
        return GeocodingResult(
            lat=float(hit["lat"]),
            lon=float(hit["lon"]),
            display_name=hit.get("display_name", query),
            raw=hit,
        )

    async def _resolve_google(self, query: str) -> GeocodingResult | None:
        """Resolve via Google Maps Geocoding API."""
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx is required for geocoding. Install: pip install httpx")

        params: dict[str, str] = {
            "address": query,
            "key": self._api_key or "",
        }
        if self._default_region:
            params["region"] = self._default_region

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(self.GOOGLE_URL, params=params)
            resp.raise_for_status()
            body = resp.json()

        results = body.get("results", [])
        if not results:
            return None

        hit = results[0]
        location = hit["geometry"]["location"]
        return GeocodingResult(
            lat=float(location["lat"]),
            lon=float(location["lng"]),
            display_name=hit.get("formatted_address", query),
            raw=hit,
        )
