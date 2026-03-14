# ER-Media

```mermaid
erDiagram
    %% ||--|| = FK NOT NULL (obbligatoria)
    %% ||--o{ = FK nullable (opzionale)
    %% }o--o{ = many-to-many via junction table

    ArchaeologicalSite ||--|| Photo : "photos.site_id"
    ArchaeologicalSite ||--|| Document : "documents.site_id"
    ArchaeologicalSite ||--|| TavolaGrafica : "tavole_grafiche.site_id"
    ArchaeologicalSite ||--|| FotografiaArcheologica : "fotografie_archeologiche.site_id"
    ArchaeologicalSite ||--|| ElencoConsegna : "elenchi_consegna.site_id"

    User ||--|| Photo : "photos.uploaded_by"
    User ||--|| Document : "documents.uploaded_by"

    Photo {
        string id PK
        string site_id FK
        string uploaded_by FK
        string filename
        string photo_type
        string deepzoom_status
    }

    Document {
        string id PK
        string site_id FK
        string uploaded_by FK
        string title
        string category
        string filepath
    }

    TavolaGrafica {
        string id PK
        string site_id FK
        string numero_tavola
        string tipo_tavola
        string file_path
    }

    FotografiaArcheologica {
        string id PK
        string site_id FK
        string numero_foto
        string tipo_foto
        string file_path
    }

    ElencoConsegna {
        string id PK
        string site_id FK
        string tipo_elenco
        json contenuto
        datetime data_generazione
    }

    ArchaeologicalSite {
        string id PK
        string code UK
    }

    User {
        string id PK
        string email UK
    }
```

Nota: i riferimenti a US/USM in [`Photo`](app/models/documentation_and_field.py:193) (`us_reference`, `usm_reference`) sono campi testuali/logici e non FK fisiche verso [`UnitaStratigrafica`](app/models/stratigraphy.py:188) o [`UnitaStratigraficaMuraria`](app/models/stratigraphy.py:386).

