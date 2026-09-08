"""Resolve granted secret values for operation-output redaction."""
from .gateway_operation import AuthorizedOperation


def _secret_values(authorized: AuthorizedOperation) -> tuple[str, ...]:
    bindings = authorized.credential_bindings
    if bindings is None:
        return ()
    if hasattr(bindings, "values"):
        values = bindings.values()
    else:
        value_for = getattr(bindings, "value_for", None)
        slots = getattr(authorized.execution_plan, "required_slots", ())
        values = [value_for(slot) for slot in slots] if callable(value_for) else ()
    return tuple(value for value in values if type(value) is str and value)
