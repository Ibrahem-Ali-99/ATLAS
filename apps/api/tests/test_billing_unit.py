from app.domains.billing.service import PLAN_DEFINITIONS


def test_all_plans_define_enforced_entitlements() -> None:
    required = {"seats", "ai_requests", "knowledge_storage_bytes", "active_workflows"}
    assert set(PLAN_DEFINITIONS) == {"free", "starter", "pro", "business"}
    for plan in PLAN_DEFINITIONS.values():
        assert required <= set(plan)
        assert all(isinstance(plan[key], int) and plan[key] > 0 for key in required)


def test_plan_limits_increase_with_tier() -> None:
    for key in ("seats", "ai_requests", "knowledge_storage_bytes", "active_workflows"):
        values = [PLAN_DEFINITIONS[name][key] for name in ("free", "starter", "pro", "business")]
        assert values == sorted(values)
