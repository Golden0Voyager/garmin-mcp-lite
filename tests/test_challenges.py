from __future__ import annotations

import pytest

from garmin_mcp_lite.client import TOKEN_FILE
from garmin_mcp_lite.tools.challenges import get_challenges

# These are live smoke tests: they call the real Garmin API with the logged-in
# account, so they only mean anything when a token is present. CI has none and
# skips them (same rationale as the `-k 'not test_get_client'` filter in ci.yml).
needs_garmin_token = pytest.mark.skipif(
    not TOKEN_FILE.exists(),
    reason=f"needs a logged-in Garmin account ({TOKEN_FILE}); run garmin-mcp-lite-login",
)


@needs_garmin_token
class TestGetChallenges:
    def test_returns_virtual_challenges(self) -> None:
        result = get_challenges()
        for vc in result["virtual_challenges"]:
            assert isinstance(vc["name"], str)
            assert 0.0 <= vc["percentage"] <= 100.0

    def test_returns_badge_challenges(self) -> None:
        # get_challenges() keeps only challenges whose window contains "now", so
        # this asserts the shape of whatever is active rather than a fixed
        # challenge name — a hardcoded name (e.g. "June Challenge") stopped
        # matching the moment that month ended.
        result = get_challenges()
        for bc in result["badge_challenges"]:
            assert isinstance(bc["name"], str)
            assert bc["unit"] in {"km", "hours", "units"}
            assert bc["target"] > 0
