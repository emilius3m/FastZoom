# ER-FieldOps

```mermaid
erDiagram
    %% ||--|| = FK NOT NULL (obbligatoria)
    %% ||--o{ = FK nullable (opzionale)
    %% }o--o{ = many-to-many via junction table

    ArchaeologicalSite ||--|| Cantiere : "cantieri.site_id"
    ArchaeologicalSite ||--|| GiornaleCantiere : "giornali_cantiere.site_id"
    ArchaeologicalSite ||--o{ OperatoreCantiere : "operatori_cantiere.site_id"
    ArchaeologicalSite ||--o{ MezzoCantiere : "mezzi_cantiere.site_id"

    Cantiere ||--o{ GiornaleCantiere : "giornali_cantiere.cantiere_id"

    GiornaleCantiere }o--o{ OperatoreCantiere : giornale_operatori
    GiornaleCantiere }o--o{ MezzoCantiere : giornale_mezzi

    User ||--|| GiornaleCantiere : "responsabile_id"
    User ||--o{ GiornaleCantiere : "validated_by_id"

    Cantiere {
        string id PK
        string site_id FK
        string nome
        string codice
        string stato
        string responsabile_cantiere
    }

    GiornaleCantiere {
        string id PK
        string site_id FK
        string cantiere_id FK
        date data
        string responsabile_id FK
        string validated_by_id FK
        bool validato
        string legal_status
    }

    OperatoreCantiere {
        string id PK
        string site_id FK
        string nome
        string cognome
        string qualifica
        bool is_active
    }

    MezzoCantiere {
        string id PK
        string site_id FK
        string nome
        string tipo
        string targa
        bool is_active
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

Nota: [`responsabile_cantiere`](app/models/cantiere.py:86) in [`Cantiere`](app/models/cantiere.py:18) è un campo testuale libero e **non** una FK verso [`User`](app/models/users.py:56).
