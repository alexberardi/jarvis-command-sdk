"""Tests for jarvis_command_sdk.geocoding (GeocodingResult + GeocodingHelper).

httpx is an optional dependency and is NOT installed in the test venv, so the
``import httpx`` statements inside the helper methods are exercised by injecting
a fake ``httpx`` module into ``sys.modules``. The async methods are driven via
``asyncio.run(...)`` because pytest-asyncio is not available.
"""

from __future__ import annotations

import asyncio
import sys
import types
from typing import Any

import pytest

from jarvis_command_sdk import GeocodingHelper, GeocodingResult


# ---------------------------------------------------------------------------
# Fake httpx scaffolding
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Stand-in for httpx.Response with the bits the helper touches."""

    def __init__(self, json_data: Any, raise_exc: Exception | None = None) -> None:
        self._json_data = json_data
        self._raise_exc = raise_exc

    def raise_for_status(self) -> None:
        if self._raise_exc is not None:
            raise self._raise_exc

    def json(self) -> Any:
        return self._json_data


class _FakeAsyncClient:
    """Async context manager mimicking httpx.AsyncClient.

    Records the constructor kwargs and the last get() call so tests can assert
    on the request that was built (params/headers/url).
    """

    # Class-level capture so a test can inspect calls without holding the instance.
    last_init_kwargs: dict[str, Any] = {}
    last_get: dict[str, Any] = {}

    # Configured per-test: the response to hand back from get().
    response: _FakeResponse | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _FakeAsyncClient.last_init_kwargs = kwargs

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        _FakeAsyncClient.last_get = {"url": url, **kwargs}
        assert _FakeAsyncClient.response is not None
        return _FakeAsyncClient.response


def _install_fake_httpx(response: _FakeResponse) -> types.ModuleType:
    """Insert a fake httpx module into sys.modules and return it."""
    mod = types.ModuleType("httpx")
    _FakeAsyncClient.response = response
    _FakeAsyncClient.last_init_kwargs = {}
    _FakeAsyncClient.last_get = {}
    mod.AsyncClient = _FakeAsyncClient  # type: ignore[attr-defined]
    sys.modules["httpx"] = mod
    return mod


@pytest.fixture(autouse=True)
def _clean_httpx() -> Any:
    """Ensure each test starts and ends with no httpx in sys.modules."""
    sys.modules.pop("httpx", None)
    yield
    sys.modules.pop("httpx", None)


# ---------------------------------------------------------------------------
# GeocodingResult
# ---------------------------------------------------------------------------


class TestGeocodingResult:
    def test_coords_returns_lat_lon_tuple(self) -> None:
        result = GeocodingResult(lat=47.6062, lon=-122.3321, display_name="Seattle")
        assert result.coords == (47.6062, -122.3321)

    def test_coords_matches_individual_fields(self) -> None:
        result = GeocodingResult(lat=1.5, lon=-2.5, display_name="x")
        lat, lon = result.coords
        assert lat == result.lat
        assert lon == result.lon

    def test_raw_defaults_to_none(self) -> None:
        result = GeocodingResult(lat=0.0, lon=0.0, display_name="origin")
        assert result.raw is None


# ---------------------------------------------------------------------------
# GeocodingHelper.__init__
# ---------------------------------------------------------------------------


class TestGeocodingHelperInit:
    def test_defaults(self) -> None:
        helper = GeocodingHelper()
        assert helper._provider == "nominatim"
        assert helper._api_key is None
        assert helper._user_agent == "jarvis-assistant/1.0"
        assert helper._default_region is None

    def test_custom_provider_and_api_key(self) -> None:
        helper = GeocodingHelper(
            provider="google",
            api_key="secret-key",
            user_agent="my-app/2.0",
            default_region="us",
        )
        assert helper._provider == "google"
        assert helper._api_key == "secret-key"
        assert helper._user_agent == "my-app/2.0"
        assert helper._default_region == "us"


# ---------------------------------------------------------------------------
# GeocodingHelper.resolve — input validation / routing
# ---------------------------------------------------------------------------


class TestResolveValidation:
    def test_empty_string_returns_none(self) -> None:
        helper = GeocodingHelper()
        assert asyncio.run(helper.resolve("")) is None

    def test_whitespace_only_returns_none(self) -> None:
        helper = GeocodingHelper()
        assert asyncio.run(helper.resolve("   \t\n ")) is None

    def test_routes_to_nominatim_by_default(self) -> None:
        _install_fake_httpx(
            _FakeResponse([{"lat": "1.0", "lon": "2.0", "display_name": "Somewhere"}])
        )
        helper = GeocodingHelper()
        result = asyncio.run(helper.resolve("anywhere"))
        assert result is not None
        # Nominatim URL was used → confirms routing.
        assert _FakeAsyncClient.last_get["url"] == GeocodingHelper.NOMINATIM_URL

    def test_routes_to_google_when_provider_and_key_set(self) -> None:
        _install_fake_httpx(
            _FakeResponse(
                {
                    "results": [
                        {
                            "geometry": {"location": {"lat": 3.0, "lng": 4.0}},
                            "formatted_address": "Google Place",
                        }
                    ]
                }
            )
        )
        helper = GeocodingHelper(provider="google", api_key="k")
        result = asyncio.run(helper.resolve("anywhere"))
        assert result is not None
        assert _FakeAsyncClient.last_get["url"] == GeocodingHelper.GOOGLE_URL

    def test_google_provider_without_key_falls_back_to_nominatim(self) -> None:
        _install_fake_httpx(
            _FakeResponse([{"lat": "5.0", "lon": "6.0", "display_name": "Fallback"}])
        )
        helper = GeocodingHelper(provider="google", api_key=None)
        result = asyncio.run(helper.resolve("anywhere"))
        assert result is not None
        # No key → routes to nominatim despite provider=google.
        assert _FakeAsyncClient.last_get["url"] == GeocodingHelper.NOMINATIM_URL


# ---------------------------------------------------------------------------
# GeocodingHelper._resolve_nominatim
# ---------------------------------------------------------------------------


class TestResolveNominatim:
    def test_successful_resolution(self) -> None:
        _install_fake_httpx(
            _FakeResponse(
                [
                    {
                        "lat": "47.6062",
                        "lon": "-122.3321",
                        "display_name": "Seattle, WA, USA",
                        "type": "city",
                    }
                ]
            )
        )
        helper = GeocodingHelper()
        result = asyncio.run(helper.resolve("Seattle"))
        assert result == GeocodingResult(
            lat=47.6062,
            lon=-122.3321,
            display_name="Seattle, WA, USA",
            raw={
                "lat": "47.6062",
                "lon": "-122.3321",
                "display_name": "Seattle, WA, USA",
                "type": "city",
            },
        )

    def test_request_params_and_headers(self) -> None:
        _install_fake_httpx(
            _FakeResponse([{"lat": "1", "lon": "2", "display_name": "x"}])
        )
        helper = GeocodingHelper(user_agent="custom-agent/9")
        asyncio.run(helper.resolve("Paris"))
        params = _FakeAsyncClient.last_get["params"]
        assert params == {
            "q": "Paris",
            "format": "json",
            "limit": "1",
            "addressdetails": "1",
        }
        assert _FakeAsyncClient.last_get["headers"] == {"User-Agent": "custom-agent/9"}
        # No region → no countrycodes key.
        assert "countrycodes" not in params

    def test_default_region_adds_countrycodes(self) -> None:
        _install_fake_httpx(
            _FakeResponse([{"lat": "1", "lon": "2", "display_name": "x"}])
        )
        helper = GeocodingHelper(default_region="gb")
        asyncio.run(helper.resolve("London"))
        assert _FakeAsyncClient.last_get["params"]["countrycodes"] == "gb"

    def test_empty_results_returns_none(self) -> None:
        _install_fake_httpx(_FakeResponse([]))
        helper = GeocodingHelper()
        assert asyncio.run(helper.resolve("nowhere at all")) is None

    def test_missing_display_name_falls_back_to_query(self) -> None:
        _install_fake_httpx(_FakeResponse([{"lat": "10", "lon": "20"}]))
        helper = GeocodingHelper()
        result = asyncio.run(helper.resolve("Atlantis"))
        assert result is not None
        assert result.display_name == "Atlantis"

    def test_raise_for_status_propagates(self) -> None:
        boom = RuntimeError("502 Bad Gateway")
        _install_fake_httpx(_FakeResponse(None, raise_exc=boom))
        helper = GeocodingHelper()
        with pytest.raises(RuntimeError, match="502 Bad Gateway"):
            asyncio.run(helper.resolve("Seattle"))

    def test_import_error_when_httpx_missing(self) -> None:
        # httpx is genuinely absent in the venv and the autouse fixture
        # guarantees it's not in sys.modules.
        assert "httpx" not in sys.modules
        helper = GeocodingHelper()
        with pytest.raises(ImportError, match="httpx is required for geocoding"):
            asyncio.run(helper.resolve("Seattle"))


# ---------------------------------------------------------------------------
# GeocodingHelper._resolve_google
# ---------------------------------------------------------------------------


class TestResolveGoogle:
    def _google_response(self) -> _FakeResponse:
        return _FakeResponse(
            {
                "results": [
                    {
                        "geometry": {"location": {"lat": 48.8584, "lng": 2.2945}},
                        "formatted_address": "Eiffel Tower, Paris, France",
                    }
                ]
            }
        )

    def test_successful_resolution(self) -> None:
        _install_fake_httpx(self._google_response())
        helper = GeocodingHelper(provider="google", api_key="k")
        result = asyncio.run(helper.resolve("Eiffel Tower"))
        assert result is not None
        assert result.lat == 48.8584
        assert result.lon == 2.2945
        assert result.display_name == "Eiffel Tower, Paris, France"
        assert result.raw["geometry"]["location"]["lng"] == 2.2945

    def test_request_params_include_address_and_key(self) -> None:
        _install_fake_httpx(self._google_response())
        helper = GeocodingHelper(provider="google", api_key="my-key")
        asyncio.run(helper.resolve("Eiffel Tower"))
        params = _FakeAsyncClient.last_get["params"]
        assert params["address"] == "Eiffel Tower"
        assert params["key"] == "my-key"
        assert "region" not in params

    def test_default_region_adds_region_param(self) -> None:
        _install_fake_httpx(self._google_response())
        helper = GeocodingHelper(provider="google", api_key="k", default_region="fr")
        asyncio.run(helper.resolve("Eiffel Tower"))
        assert _FakeAsyncClient.last_get["params"]["region"] == "fr"

    def test_empty_results_returns_none(self) -> None:
        _install_fake_httpx(_FakeResponse({"results": []}))
        helper = GeocodingHelper(provider="google", api_key="k")
        assert asyncio.run(helper.resolve("nowhere")) is None

    def test_missing_results_key_returns_none(self) -> None:
        _install_fake_httpx(_FakeResponse({"status": "ZERO_RESULTS"}))
        helper = GeocodingHelper(provider="google", api_key="k")
        assert asyncio.run(helper.resolve("nowhere")) is None

    def test_missing_formatted_address_falls_back_to_query(self) -> None:
        _install_fake_httpx(
            _FakeResponse(
                {"results": [{"geometry": {"location": {"lat": 1.0, "lng": 2.0}}}]}
            )
        )
        helper = GeocodingHelper(provider="google", api_key="k")
        result = asyncio.run(helper.resolve("MysteryPlace"))
        assert result is not None
        assert result.display_name == "MysteryPlace"

    def test_raise_for_status_propagates(self) -> None:
        boom = RuntimeError("403 Forbidden")
        _install_fake_httpx(_FakeResponse(None, raise_exc=boom))
        helper = GeocodingHelper(provider="google", api_key="k")
        with pytest.raises(RuntimeError, match="403 Forbidden"):
            asyncio.run(helper.resolve("Eiffel Tower"))

    def test_import_error_when_httpx_missing(self) -> None:
        assert "httpx" not in sys.modules
        # Call _resolve_google directly so the missing-httpx branch in the
        # google path is exercised (resolve() would route to nominatim
        # without a key, but here the key is present).
        helper = GeocodingHelper(provider="google", api_key="k")
        with pytest.raises(ImportError, match="httpx is required for geocoding"):
            asyncio.run(helper.resolve("Eiffel Tower"))


# ---------------------------------------------------------------------------
# GeocodingHelper.resolve_batch
# ---------------------------------------------------------------------------


class TestResolveBatch:
    def test_batch_preserves_order_and_handles_empty(self) -> None:
        _install_fake_httpx(
            _FakeResponse([{"lat": "1", "lon": "2", "display_name": "hit"}])
        )
        helper = GeocodingHelper()
        # "" short-circuits to None before any httpx use; the non-empty
        # query goes through the fake client.
        results = asyncio.run(helper.resolve_batch(["", "London"]))
        assert len(results) == 2
        assert results[0] is None
        assert results[1] is not None
        assert results[1].coords == (1.0, 2.0)

    def test_batch_empty_list(self) -> None:
        helper = GeocodingHelper()
        assert asyncio.run(helper.resolve_batch([])) == []
