# ER Diagram - FastZoom (Modulare)

Questo documento ora funge da indice al modello ER modulare (6 moduli + 1 context map).

## Context Map

- [ER_CONTEXT_MAP.md](ER_CONTEXT_MAP.md)

## Physical ER (source of truth)

- [PHYSICAL_ER.md](PHYSICAL_ER.md)
- Generator script: [scripts/generate_physical_er.py](scripts/generate_physical_er.py)
- Regenerate with: `python scripts/generate_physical_er.py`

## Moduli ER

| Modulo | Entità incluse | File |
| --- | --- | --- |
| ER-IAM | User, UserProfile, Role, UserSitePermission, UserActivity, TokenBlacklist | [ER_IAM.md](ER_IAM.md) |
| ER-SiteCore | ArchaeologicalSite, GeographicMap, GeographicMapLayer, GeographicMapMarker, ArchaeologicalPlan | [ER_SITECORE.md](ER_SITECORE.md) |
| ER-Stratigraphy | UnitaStratigrafica, UnitaStratigraficaMuraria, USFile, HarrisMatrixMapping, MatrixHarris | [ER_STRATIGRAPHY.md](ER_STRATIGRAPHY.md) |
| ER-ICCD | ICCDBaseRecord, ICCDAuthorityFile, ICCDSchemaTemplate, SchedaTMA + child tables | [ER_ICCD.md](ER_ICCD.md) |
| ER-Media | Photo, Document, TavolaGrafica, FotografiaArcheologica, ElencoConsegna | [ER_MEDIA.md](ER_MEDIA.md) |
| ER-FieldOps | Cantiere, GiornaleCantiere, OperatoreCantiere, MezzoCantiere | [ER_FIELDOPS.md](ER_FIELDOPS.md) |

## Regole di lettura

- I diagrammi sono orientati al dominio e mantengono i soli campi chiave (PK/FK + identificativi funzionali).
- Le relazioni cross-modulo sono rappresentate come entità esterne minimali quando necessario.
- La fonte di verità tecnica resta nei modelli SQLAlchemy in `app/models/`.

## Workflow consigliato

1. Aggiorna i modelli ORM e/o migrazioni Alembic.
2. Rigenera il physical ER con `python scripts/generate_physical_er.py`.
3. Aggiorna solo i diagrammi modulari impattati (IAM/SiteCore/Stratigraphy/ICCD/Media/FieldOps).
