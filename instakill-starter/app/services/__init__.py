"""Application services: use cases that coordinate the domain models.

Services sit between the HTTP layer (``app.api``) and persistence (``app.db``).
They never handle HTTP requests/responses and never talk to SQLite directly;
storage is reached through the small repository protocols they declare.
"""
