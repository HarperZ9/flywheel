"""Select and admit an endpoint gate before health or generation I/O."""
from typing import Any


def select_profiles(
    profiles: list[dict[str, Any]], *, models: list[str], backends: list[str],
    profile_id: str | None, max_generation_calls: int | None,
) -> tuple[list[dict[str, Any]], str]:
    if max_generation_calls is not None and (
        type(max_generation_calls) is not int or max_generation_calls < 0
    ):
        return [], "invalid_generation_call_budget"
    candidates = profiles
    if profile_id is not None:
        if not isinstance(profile_id, str) or not profile_id.strip():
            return [], "invalid_profile_id"
        candidates = [row for row in profiles if row.get("profile_id") == profile_id]
        if not candidates:
            return [], "profile_id_not_found"
        if len(candidates) != 1:
            return [], "profile_id_ambiguous"
    wanted_models = {item.lower() for item in models}
    wanted_backends = {item.lower() for item in backends}
    selected = [row for row in candidates
                if (not wanted_models or str(row.get("model", "")).lower() in wanted_models)
                and (not wanted_backends or str(row.get("backend", "")).lower() in wanted_backends)]
    if not selected:
        return [], "no_profiles_selected"
    # Each admitted profile may generate once. Refuse the entire plan instead
    # of spending part of the budget and silently dropping the remaining rows.
    if max_generation_calls is not None and len(selected) > max_generation_calls:
        return selected, "generation_call_budget_exceeded"
    return selected, ""
