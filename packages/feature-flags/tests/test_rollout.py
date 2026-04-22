"""Feature flag rollout tests — allowlist, denylist, kill switch, bucketing."""

from __future__ import annotations

from meridian_feature_flags import (
    FeatureFlag,
    FlagDecision,
    InMemoryFeatureFlagStore,
    RolloutResult,
    RolloutService,
    bucket_for_user,
)


def _service(flag: FeatureFlag) -> RolloutService:
    store = InMemoryFeatureFlagStore()
    store.put(flag)
    return RolloutService(store=store)


def test_missing_flag_denies() -> None:
    svc = RolloutService(store=InMemoryFeatureFlagStore())
    result = svc.evaluate("missing", "u_alice")
    assert result.allowed is False
    assert result.result is RolloutResult.FLAG_MISSING


def test_kill_switch_denies_all() -> None:
    svc = _service(FeatureFlag(name="meridian.enabled", percentage=100, kill_switch=True))
    result = svc.evaluate("meridian.enabled", "u_alice")
    assert result.allowed is False
    assert result.result is RolloutResult.KILL_SWITCH


def test_allowlist_overrides_percentage() -> None:
    svc = _service(FeatureFlag(name="meridian.enabled", percentage=0, allowlist=["u_alice"]))
    result = svc.evaluate("meridian.enabled", "u_alice")
    assert result.allowed is True
    assert result.result is RolloutResult.ALLOWLISTED


def test_denylist_overrides_percentage() -> None:
    svc = _service(FeatureFlag(name="meridian.enabled", percentage=100, denylist=["u_blocked"]))
    assert svc.evaluate("meridian.enabled", "u_blocked").result is RolloutResult.DENYLISTED


def test_percentage_zero_denies_everyone() -> None:
    svc = _service(FeatureFlag(name="meridian.enabled", percentage=0))
    for user in ["u_a", "u_b", "u_c", "u_d", "u_e"]:
        decision: FlagDecision = svc.evaluate("meridian.enabled", user)
        assert decision.allowed is False
        assert decision.result is RolloutResult.OUT_OF_ROLLOUT


def test_percentage_100_allows_everyone() -> None:
    svc = _service(FeatureFlag(name="meridian.enabled", percentage=100))
    for user in ["u_a", "u_b", "u_c", "u_d", "u_e"]:
        decision = svc.evaluate("meridian.enabled", user)
        assert decision.allowed is True
        assert decision.result is RolloutResult.IN_ROLLOUT


def test_percentage_50_roughly_half() -> None:
    svc = _service(FeatureFlag(name="meridian.enabled", percentage=50))
    allowed = sum(1 for i in range(1000) if svc.evaluate("meridian.enabled", f"u_{i}").allowed)
    assert 420 <= allowed <= 580, f"expected ~500 allowed, got {allowed}"


def test_bucket_is_stable() -> None:
    assert bucket_for_user("u_alice", flag_name="x") == bucket_for_user("u_alice", flag_name="x")


def test_bucket_differs_by_flag_name() -> None:
    different = sum(
        1
        for i in range(20)
        if bucket_for_user(f"u_{i}", flag_name="a") != bucket_for_user(f"u_{i}", flag_name="b")
    )
    assert different >= 10


def test_store_list_all_returns_sorted() -> None:
    store = InMemoryFeatureFlagStore()
    store.put(FeatureFlag(name="z.thing"))
    store.put(FeatureFlag(name="a.thing"))
    store.put(FeatureFlag(name="m.thing"))
    assert [f.name for f in store.list_all()] == ["a.thing", "m.thing", "z.thing"]
