---
paths:
  - "backend/**/*.py"
---

# Backend: rules an agent must not miss

Source of truth: docs/handbook/kien-truc.md, hanh-vi-api.md, quy-uoc-code.md. Open them when a case is not here.

- Route → service → repository; repositories take the session and never commit, services never read the HTTP request; the route's caller commits once (`get_database()` rolls back).
- Another module's data goes through its service or repository, never by calling its route.
- Module errors subclass `backend.common.base_exceptions` with their own `code` and a client-safe message: no SQL, stack trace, URI or password.
- Timestamps are aware UTC in `DateTime(timezone=True)`; never guess a naive timezone; keep Decimal, do not cast to float.
- New model: import it in its `models/__init__.py` and add the package to `MODEL_PACKAGES` in `backend/modules/model_registry.py`; workers and scripts call `register_all_models()`.
- Behavior change: update `docs/handbook/modules/<module>/` in the same change, marking **đã triển khai** or **dự kiến**.
