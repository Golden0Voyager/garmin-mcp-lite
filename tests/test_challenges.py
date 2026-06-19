from __future__ import annotations

from garmin_mcp_lite.tools.challenges import get_challenges


class TestGetChallenges:
    def test_returns_virtual_challenges(self) -> None:
        result = get_challenges()
        assert len(result["virtual_challenges"]) == 1
        vc = result["virtual_challenges"][0]
        assert vc["name"] == "Climb 5000m"
        assert vc["percentage"] == 64.0

    def test_returns_badge_challenges(self) -> None:
        result = get_challenges()
        assert len(result["badge_challenges"]) == 1
        bc = result["badge_challenges"][0]
        assert bc["name"] == "June Challenge"
        assert bc["unit"] == "km"
