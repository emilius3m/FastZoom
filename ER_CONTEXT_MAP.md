# ER Context Map - FastZoom

```mermaid
flowchart LR
    IAM[ER-IAM]
    SITE[ER-SiteCore]
    STRAT[ER-Stratigraphy]
    ICCD[ER-ICCD]
    MEDIA[ER-Media]
    FIELD[ER-FieldOps]

    IAM <-- "UserSitePermission" --> SITE
    IAM <-- "created_by / uploaded_by / responsabile_id" --> MEDIA
    IAM <-- "responsabile_id / validated_by_id" --> FIELD
    IAM <-- "created_by" --> ICCD

    SITE <-- "site_id" --> STRAT
    SITE <-- "site_id" --> ICCD
    SITE <-- "site_id" --> MEDIA
    SITE <-- "site_id" --> FIELD

    STRAT <-- "US/USM refs (logical)" --> MEDIA
    STRAT <-- "contesto di scavo" --> ICCD
    FIELD <-- "documentazione giornaliera" --> MEDIA
```

## Overview Entities (ridotto: PK/FK + campi critici)

```mermaid
erDiagram
    %% ||--|| = FK NOT NULL (obbligatoria)
    %% ||--o{ = FK nullable (opzionale)
    %% }o--o{ = many-to-many via junction table

    ArchaeologicalSite ||--|| UnitaStratigrafica : site_id
    ArchaeologicalSite ||--|| ICCDBaseRecord : site_id
    ArchaeologicalSite ||--|| Photo : site_id
    ArchaeologicalSite ||--|| Cantiere : site_id
    User ||--|| GiornaleCantiere : responsabile_id
    User ||--o{ GiornaleCantiere : validated_by_id

    ArchaeologicalSite {
        string id PK
        string code UK
        string site_type
    }

    UnitaStratigrafica {
        string id PK
        string site_id FK
        string us_code
        string tipo
        string periodo
        string fase
    }

    ICCDBaseRecord {
        string id PK
        string site_id FK
        string schema_type
        string level
    }

    Photo {
        string id PK
        string site_id FK
        string photo_type
    }

    Cantiere {
        string id PK
        string site_id FK
        string stato
    }

    GiornaleCantiere {
        string id PK
        string site_id FK
        string cantiere_id FK
        string responsabile_id FK
        string validated_by_id FK
    }

    User {
        string id PK
        string email UK
        string status
    }
```

## Boundaries

- **ER-IAM**: identità, ruoli, permessi, audit, session invalidation.
- **ER-SiteCore**: tenant root e geografia/cartografia.
- **ER-Stratigraphy**: unità stratigrafiche e mapping Harris.
- **ER-ICCD**: catalogazione standard ICCD + TMA normalizzato.
- **ER-Media**: documenti, foto, tavole, consegne.
- **ER-FieldOps**: cantieri e giornale operativo.

