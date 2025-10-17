# app/models/roles.py - REINDIRIZZATO
# Role è importata da app.models.users per evitare duplicazione

from app.models.users import Role  # noqa: F401

# Tutto il resto è gestito in app.models.users