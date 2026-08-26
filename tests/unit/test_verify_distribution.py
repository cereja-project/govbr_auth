"""Tests for installed-wheel verification profiles."""

from scripts import verify_distribution


def test_distribution_profiles_install_each_documented_extra_in_isolation() -> None:
    factory = getattr(verify_distribution, "distribution_profiles", None)
    assert factory is not None

    profiles = factory()

    assert tuple((profile.name, profile.extras) for profile in profiles) == (
        ("fastapi", ("fastapi", "fake")),
        ("django", ("django",)),
        ("flask", ("flask",)),
    )
