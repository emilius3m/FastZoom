# Entity Relationship Diagram - FastZoom Archaeological System

## Complete ERD with All Models

```mermaid
erDiagram
    %% ===== CORE USER & AUTHENTICATION =====
    USERS {
        uuid id PK
        string email
        string username
        string hashed_password
        string status
        boolean is_active
        boolean is_superuser
        boolean is_verified
        datetime email_verified_at
        datetime last_login_at
        integer login_count
        json preferences
        datetime created_at
        datetime updated_at
    }

    ROLES {
        uuid id PK
        string name
        string display_name
        text description
        boolean is_system_role
        boolean is_active
        json base_permissions
        datetime created_at
        datetime updated_at
    }

    USER_PROFILE {
        uuid id PK
        uuid user_id FK
        string first_name
        string last_name
        string phone
        string department
        string position
        string institution
        text bio
        datetime created_at
        datetime updated_at
    }

    USER_SITE_PERMISSIONS {
        uuid id PK
        uuid user_id FK
        uuid site_id FK
        string permission_level
        json permissions
        string site_role
        uuid granted_by FK
        datetime granted_at
        datetime expires_at
        boolean is_active
        text notes
        datetime created_at
        datetime updated_at
    }

    USER_ACTIVITIES {
        uuid id PK
        uuid user_id FK
        uuid site_id FK
        uuid photo_id FK
        datetime activity_date
        string activity_type
        string activity_desc
        string ip_address
        string user_agent
        text extra_data
        datetime created_at
        datetime updated_at
    }

    TOKEN_BLACKLIST {
        uuid id PK
        string token_jti
        uuid user_id FK
        datetime invalidated_at
        string reason
        datetime created_at
        datetime updated_at
    }

    %% ===== ARCHAEOLOGICAL SITES =====
    ARCHAEOLOGICAL_SITES {
        uuid id PK
        string name
        string code
        text description
        string short_description
        string site_type
        string historical_period
        string chronology_start
        string chronology_end
        string cultural_attribution
        string coordinates_lat
        string coordinates_lng
        float coordinates_precision
        float elevation
        string country
        string region
        string province
        string municipality
        string locality
        string address
        json alternative_names
        json cadastral_parcels
        string cadastral_sheet
        string status
        string research_status
        datetime discovery_date
        datetime excavation_start
        datetime excavation_end
        string research_project
        string funding_source
        string excavation_method
        json bibliography
        json external_references
        string authorization_number
        datetime authorization_date
        string superintendency
        string default_coordinate_system
        string default_measurement_unit
        json site_grid_system
        boolean is_public
        boolean is_template
        integer storage_quota_mb
        datetime created_at
        datetime updated_at
    }

    %% ===== STRATIGRAPHY (US/USM) =====
    UNITA_STRATIGRAFICHE {
        uuid id PK
        uuid site_id FK
        string tipo
        string us_code
        string ente_responsabile
        integer anno
        string ufficio_mic
        string identificativo_rif
        string localita
        string area_struttura
        string saggio
        string ambiente_unita_funzione
        string posizione
        string settori
        text piante_riferimenti
        text prospetti_riferimenti
        text sezioni_riferimenti
        text definizione
        text criteri_distinzione
        text modo_formazione
        text componenti_inorganici
        text componenti_organici
        string consistenza
        string colore
        string misure
        text stato_conservazione
        json sequenza_fisica
        text descrizione
        text osservazioni
        text interpretazione
        string datazione
        string periodo
        string fase
        text elementi_datanti
        text dati_quantitativi_reperti
        json campionature
        string affidabilita_stratigrafica
        string responsabile_scientifico
        date data_rilevamento
        string responsabile_compilazione
        date data_rielaborazione
        string responsabile_rielaborazione
        datetime created_at
        datetime updated_at
    }

    UNITA_STRATIGRAFICHE_MURARIE {
        uuid id PK
        uuid site_id FK
        string usm_code
        string ente_responsabile
        integer anno
        string ufficio_mic
        string identificativo_rif
        string localita
        string area_struttura
        string saggio
        string ambiente_unita_funzione
        string posizione
        string settori
        text piante_riferimenti
        text prospetti_riferimenti
        text sezioni_riferimenti
        string misure
        numeric superficie_analizzata
        text definizione
        string tecnica_costruttiva
        boolean sezione_muraria_visibile
        string sezione_muraria_tipo
        string sezione_muraria_spessore
        string funzione_statica
        string modulo
        text criteri_distinzione
        text provenienza_materiali
        string orientamento
        string uso_primario
        string riutilizzo
        text stato_conservazione
        json materiali_laterizi
        json materiali_elementi_litici
        text materiali_altro
        json legante
        text legante_altro
        text finiture_elementi_particolari
        json sequenza_fisica
        text descrizione
        text osservazioni
        text interpretazione
        string datazione
        string periodo
        string fase
        text elementi_datanti
        json campionature
        string affidabilita_stratigrafica
        string responsabile_scientifico
        date data_rilevamento
        string responsabile_compilazione
        date data_rielaborazione
        string responsabile_rielaborazione
        datetime created_at
        datetime updated_at
    }

    US_FILES {
        uuid id PK
        uuid site_id FK
        string filename
        string original_filename
        string filepath
        integer filesize
        string mimetype
        string file_category
        string title
        text description
        string scale_ratio
        string drawing_type
        string tavola_number
        date photo_date
        string photographer
        string camera_info
        integer width
        integer height
        integer dpi
        boolean is_deepzoom_enabled
        string deepzoom_status
        string thumbnail_path
        uuid uploaded_by FK
        boolean is_published
        boolean is_validated
        uuid validated_by FK
        datetime validated_at
        datetime created_at
        datetime updated_at
    }

    %% ===== ARCHAEOLOGICAL RECORDS =====
    SCHEDE_TOMBE {
        uuid id PK
        uuid site_id FK
        string numero_tomba
        string numero_individuo
        string denominazione
        string settore
        string quadrato
        string us_riferimento
        numeric coord_x
        numeric coord_y
        numeric quota_superiore
        numeric quota_inferiore
        string tipo_tomba
        string tipo_deposizione
        text struttura_tomba
        string copertura
        string segnacoli
        string sesso
        string eta_stimata
        string statura_stimata
        string orientamento_scheletro
        string posizione_braccia
        string posizione_gambe
        string posizione_cranio
        string stato_conservazione
        text conservazione_dettagli
        text patologie
        text traumi
        boolean presenza_corredo
        text corredo_posizione
        text corredo_descrizione
        json campionature_effettuate
        text analisi_antropologiche
        text analisi_paleopatologiche
        string datazione_relativa
        string datazione_assoluta
        string periodo_culturale
        string fase
        json foto_generali
        json foto_dettaglio
        json rilievi_grafici
        date data_scavo
        string responsabile_scavo
        text metodo_scavo
        text note_scavo
        text interpretazione
        text osservazioni
        text anomalie
        datetime created_at
        datetime updated_at
    }

    INVENTARIO_REPERTI {
        uuid id PK
        uuid site_id FK
        string numero_inventario
        string sigla_sito
        string numero_catalogo
        uuid unita_stratigrafica_id FK
        uuid unita_stratigrafica_completa_id FK
        uuid tomba_id FK
        string settore
        string quadrato
        numeric coord_x
        numeric coord_y
        numeric quota
        string categoria
        string sottocategoria
        string classe
        string tipo
        string forma
        string materiale
        string colore
        string dimensioni
        numeric peso
        numeric spessore
        numeric diametro
        string stato_conservazione
        string completezza
        text restauri
        text descrizione
        text decorazioni
        text iscrizioni
        text confronti
        string datazione
        string periodo
        string fase
        json foto_ids
        json disegno_ids
        text bibliografia
        json analisi_effettuate
        text risultati_analisi
        string ubicazione_attuale
        string numero_cassa
        boolean esposto
        json prestiti
        string importanza_scientifica
        string valore_economico
        text note_conservazione
        datetime created_at
        datetime updated_at
    }

    CAMPIONI_SCIENTIFICI {
        uuid id PK
        uuid site_id FK
        string numero_campione
        string tipo_campione
        string descrizione_campione
        uuid unita_stratigrafica_id FK
        uuid unita_stratigrafica_completa_id FK
        uuid unita_stratigrafica_muraria_id FK
        uuid tomba_id FK
        uuid reperto_id FK
        string settore
        string quadrato
        numeric coord_x
        numeric coord_y
        numeric quota
        date data_prelievo
        string responsabile_prelievo
        string metodo_prelievo
        string strumenti_utilizzati
        text descrizione
        numeric peso_campione
        numeric volume_campione
        string modalita_conservazione
        string contenitore
        string posizione_deposito
        string laboratorio_analisi
        date data_invio
        date data_risultati
        string codice_laboratorio
        json risultati_analisi
        text interpretazione_risultati
        string data_calibrata
        string sigma
        boolean pubblicato
        text riferimenti_pubblicazione
        text note_prelievo
        text note_analisi
        datetime created_at
        datetime updated_at
    }

    MATERIALE_ARCHEOLOGICO {
        uuid id PK
        string nome
        string descrizione
        string categoria
        json proprietà
        datetime created_at
        datetime updated_at
    }

    %% ===== PHOTOS & DOCUMENTATION =====
    PHOTOS {
        uuid id PK
        uuid site_id FK
        uuid uploaded_by FK
        uuid validated_by FK
        string filename
        string original_filename
        string file_path
        integer file_size
        string mime_type
        integer width
        integer height
        integer dpi
        string color_profile
        string thumbnail_path
        string title
        text description
        text keywords
        string photo_type
        string photographer
        datetime photo_date
        string camera_model
        string lens
        string inventory_number
        string old_inventory_number
        string catalog_number
        string excavation_area
        string stratigraphic_unit
        string grid_square
        float depth_level
        datetime find_date
        string finder
        string excavation_campaign
        string material
        string material_details
        string object_type
        string object_function
        float length_cm
        float width_cm
        float height_cm
        float diameter_cm
        float weight_grams
        string chronology_period
        string chronology_culture
        integer dating_from
        integer dating_to
        text dating_notes
        string conservation_status
        text conservation_notes
        text restoration_history
        text bibliography
        text comparative_references
        text external_links
        text exif_data
        text iptc_data
        string copyright_holder
        string license_type
        text usage_rights
        boolean is_published
        boolean is_validated
        text validation_notes
        boolean has_deep_zoom
        string deep_zoom_status
        integer deep_zoom_levels
        integer deep_zoom_tile_count
        datetime deep_zoom_processed_at
        datetime created
        datetime updated
    }

    PHOTO_MODIFICATIONS {
        uuid id PK
        uuid photo_id FK
        uuid modified_by FK
        string modification_type
        string field_changed
        text old_value
        text new_value
        text notes
        datetime created
        datetime updated
    }

    DOCUMENTS {
        uuid id PK
        uuid site_id FK
        uuid uploaded_by FK
        string filename
        string original_filename
        string file_path
        integer filesize
        string mimetype
        string document_type
        string title
        text description
        string author
        date document_date
        string version
        string language
        string category
        json tags
        boolean is_published
        boolean is_validated
        uuid validated_by FK
        datetime validated_at
        datetime created_at
        datetime updated_at
    }

    %% ===== GEOGRAPHIC MAPS =====
    GEOGRAPHIC_MAPS {
        uuid id PK
        uuid site_id FK
        uuid created_by FK
        string name
        text description
        float bounds_north
        float bounds_south
        float bounds_east
        float bounds_west
        float center_lat
        float center_lng
        integer default_zoom
        json map_config
        boolean is_active
        boolean is_default
        datetime created_at
        datetime updated_at
    }

    GEOGRAPHIC_MAP_LAYERS {
        uuid id PK
        uuid map_id FK
        uuid site_id FK
        uuid created_by FK
        string name
        text description
        string layer_type
        json geojson_data
        integer features_count
        json style_config
        boolean is_visible
        integer display_order
        float bounds_north
        float bounds_south
        float bounds_east
        float bounds_west
        datetime created_at
        datetime updated_at
    }

    GEOGRAPHIC_MAP_MARKERS {
        uuid id PK
        uuid map_id FK
        uuid site_id FK
        uuid created_by FK
        float latitude
        float longitude
        string title
        text description
        string marker_type
        string icon
        string color
        json metadata
        datetime created_at
        datetime updated_at
    }

    GEOGRAPHIC_MAP_MARKER_PHOTOS {
        uuid id PK
        uuid marker_id FK
        uuid photo_id FK
        text description
        integer display_order
        boolean is_primary
        datetime created_at
        uuid created_by FK
    }

    %% ===== ARCHAEOLOGICAL PLANS =====
    ARCHAEOLOGICAL_PLANS {
        uuid id PK
        uuid site_id FK
        uuid uploaded_by FK
        string plan_title
        string plan_description
        string plan_type
        string file_path
        string file_format
        integer width_px
        integer height_px
        string scale
        text notes
        boolean is_published
        datetime created_at
        datetime updated_at
    }

    %% ===== FORMS & ICCD =====
    FORM_SCHEMAS {
        uuid id PK
        uuid site_id FK
        uuid created_by FK
        string schema_name
        string schema_type
        json schema_definition
        boolean is_active
        text description
        datetime created_at
        datetime updated_at
    }

    FORM_DATA {
        uuid id PK
        uuid site_id FK
        uuid schema_id FK
        uuid submitted_by FK
        json form_data
        string status
        datetime submitted_at
        datetime created_at
        datetime updated_at
    }

    ICCD_RECORDS {
        uuid id PK
        uuid site_id FK
        uuid created_by FK
        uuid updated_by FK
        string record_type
        string record_number
        json record_data
        string status
        text notes
        datetime created_at
        datetime updated_at
    }

    %% ===== CONSTRUCTION SITE MANAGEMENT =====
    CANTIERE {
        uuid id PK
        uuid site_id FK
        uuid created_by FK
        string nome
        string codice
        string stato
        string responsabile_cantiere
        string direttore_lavori
        string responsabile_procedimento
        date data_inizio_prevista
        date data_fine_prevista
        date data_inizio_effettiva
        date data_fine_effettiva
        string tipologia_intervento
        integer priorita
        string area_descrizione
        text descrizione
        string committente
        string impresa_esecutrice
        string oggetto_appalto
        string codice_cup
        string codice_cig
        numeric importo_lavori
        string iccd_re_tipo
        string iccd_re_metodo
        text iccd_geometria
        datetime created_at
        datetime updated_at
    }

    GIORNALE_CANTIERE {
        uuid id PK
        uuid site_id FK
        uuid cantiere_id FK
        uuid responsabile_id FK
        date data
        text condizioni_meteorologiche
        text note_generali
        integer numero_operatori
        text descrizione_attivita
        json attivita_dettagliate
        json problematiche_rilevate
        json soluzioni_adopte
        json materiali_utilizzati
        json attrezzature_utilizzate
        json foto_riferimenti
        json documenti_riferimenti
        string stato
        datetime created_at
        datetime updated_at
    }

    OPERATORE_CANTIERE {
        uuid id PK
        uuid site_id FK
        uuid user_id FK
        string nome
        string cognome
        string qualifica
        string specializzazione
        date data_inizio
        date data_fine
        string note
        datetime created_at
        datetime updated_at
    }

    %% ===== GRAPHIC DOCUMENTATION =====
    TAVOLE_GRAFICHE {
        uuid id PK
        uuid site_id FK
        uuid created_by FK
        string numero_tavola
        string titolo
        text descrizione
        string tipo
        string file_path
        integer width_px
        integer height_px
        string scala
        json us_riferimenti
        json usm_riferimenti
        boolean is_pubblicata
        datetime created_at
        datetime updated_at
    }

    FOTOGRAFIE_ARCHEOLOGICHE {
        uuid id PK
        uuid site_id FK
        uuid created_by FK
        string codice_foto
        string titolo
        text descrizione
        string tipo
        string file_path
        integer width_px
        integer height_px
        date data_scatto
        string fotografo
        string attrezzatura
        json us_riferimenti
        json usm_riferimenti
        boolean is_pubblicata
        datetime created_at
        datetime updated_at
    }

    %% ===== HARRIS MATRIX =====
    MATRIX_HARRIS {
        uuid id PK
        uuid site_id FK
        uuid created_by FK
        string nome
        text descrizione
        json dati_matrix
        json configurazione_layout
        boolean is_pubblicata
        datetime created_at
        datetime updated_at
    }

    HARRIS_MATRIX_MAPPING {
        uuid id PK
        uuid matrix_id FK
        uuid us_id FK
        uuid usm_id FK
        string tipo_relazione
        integer posizione_x
        integer posizione_y
        text note
        datetime created_at
        datetime updated_at
    }

    HARRIS_MATRIX_LAYOUT {
        uuid id PK
        uuid matrix_id FK
        string nome_layout
        json configurazione
        string tipo_visualizzazione
        datetime created_at
        datetime updated_at
    }

    %% ===== FINAL REPORTS =====
    RELAZIONE_FINALE_SCAVO {
        uuid id PK
        uuid site_id FK
        uuid created_by FK
        string titolo
        text descrizione
        date data_inizio
        date data_fine
        json risultati_principali
        json conclusioni
        json raccomandazioni
        json bibliografia
        string stato
        datetime created_at
        datetime updated_at
    }

    TEMPLATE_RELAZIONE {
        uuid id PK
        uuid site_id FK
        uuid created_by FK
        string nome_template
        json struttura_template
        boolean is_default
        datetime created_at
        datetime updated_at
    }

    ELCONCO_CONSEGNA {
        uuid id PK
        uuid site_id FK
        uuid created_by FK
        string numero_elenco
        date data_consegna
        string destinatario
        text descrizione
        json oggetti_consegnati
        json firme_responsabili
        string stato
        datetime created_at
        datetime updated_at
    }

    %% ===== CONFIGURATIONS =====
    CONFIGURAZIONE_EXPORT {
        uuid id PK
        uuid site_id FK
        uuid created_by FK
        string nome_configurazione
        json parametri_export
        string formato_output
        boolean is_default
        datetime created_at
        datetime updated_at
    }

    %% ===== RELATIONSHIPS =====
    
    %% User Core
    USERS ||--o{ USER_PROFILE : "has"
    USERS ||--o{ USER_SITE_PERMISSIONS : "has"
    USERS ||--o{ USER_ACTIVITIES : "performs"
    USERS ||--o{ TOKEN_BLACKLIST : "invalidates"
    USERS }o--|| ROLES : "has"
    
    %% Site Relations
    ARCHAEOLOGICAL_SITES ||--o{ USER_SITE_PERMISSIONS : "grants"
    ARCHAEOLOGICAL_SITES ||--o{ USER_ACTIVITIES : "records"
    ARCHAEOLOGICAL_SITES ||--o{ PHOTOS : "contains"
    ARCHAEOLOGICAL_SITES ||--o{ DOCUMENTS : "contains"
    ARCHAEOLOGICAL_SITES ||--o{ GEOGRAPHIC_MAPS : "has"
    ARCHAEOLOGICAL_SITES ||--o{ ARCHAEOLOGICAL_PLANS : "has"
    ARCHAEOLOGICAL_SITES ||--o{ FORM_SCHEMAS : "has"
    ARCHAEOLOGICAL_SITES ||--o{ ICCD_RECORDS : "contains"
    ARCHAEOLOGICAL_SITES ||--o{ CANTIERE : "has"
    ARCHAEOLOGICAL_SITES ||--o{ GIORNALE_CANTIERE : "has"
    ARCHAEOLOGICAL_SITES ||--o{ OPERATORE_CANTIERE : "has"
    ARCHAEOLOGICAL_SITES ||--o{ TAVOLE_GRAFICHE : "has"
    ARCHAEOLOGICAL_SITES ||--o{ FOTOGRAFIE_ARCHEOLOGICHE : "has"
    ARCHAEOLOGICAL_SITES ||--o{ MATRIX_HARRIS : "has"
    ARCHAEOLOGICAL_SITES ||--o{ RELAZIONE_FINALE_SCAVO : "has"
    ARCHAEOLOGICAL_SITES ||--o{ TEMPLATE_RELAZIONE : "has"
    ARCHAEOLOGICAL_SITES ||--o{ ELCONCO_CONSEGNA : "has"
    ARCHAEOLOGICAL_SITES ||--o{ CONFIGURAZIONE_EXPORT : "has"
    
    %% Stratigraphy Relations
    ARCHAEOLOGICAL_SITES ||--o{ UNITA_STRATIGRAFICHE : "contains"
    ARCHAEOLOGICAL_SITES ||--o{ UNITA_STRATIGRAFICHE_MURARIE : "contains"
    ARCHAEOLOGICAL_SITES ||--o{ US_FILES : "contains"
    UNITA_STRATIGRAFICHE ||--o{ US_FILES : "has"
    UNITA_STRATIGRAFICHE_MURARIE ||--o{ US_FILES : "has"
    UNITA_STRATIGRAFICHE ||--o{ INVENTARIO_REPERTI : "contains"
    UNITA_STRATIGRAFICHE ||--o{ CAMPIONI_SCIENTIFICI : "contains"
    UNITA_STRATIGRAFICHE_MURARIE ||--o{ CAMPIONI_SCIENTIFICI : "contains"
    
    %% Archaeological Records Relations
    ARCHAEOLOGICAL_SITES ||--o{ SCHEDE_TOMBE : "contains"
    SCHEDE_TOMBE ||--o{ INVENTARIO_REPERTI : "has_corredo"
    SCHEDE_TOMBE ||--o{ CAMPIONI_SCIENTIFICI : "has"
    INVENTARIO_REPERTI ||--o{ CAMPIONI_SCIENTIFICI : "has"
    INVENTARIO_REPERTI ||--o{ MATERIALE_ARCHEOLOGICO : "has"
    
    %% Photos Relations
    USERS ||--o{ PHOTOS : "uploads"
    USERS ||--o{ PHOTOS : "validates"
    PHOTOS ||--o{ PHOTO_MODIFICATIONS : "has"
    PHOTOS ||--o{ GEOGRAPHIC_MAP_MARKER_PHOTOS : "linked_to"
    
    %% Geographic Maps Relations
    GEOGRAPHIC_MAPS ||--o{ GEOGRAPHIC_MAP_LAYERS : "contains"
    GEOGRAPHIC_MAPS ||--o{ GEOGRAPHIC_MAP_MARKERS : "contains"
    GEOGRAPHIC_MAP_MARKERS ||--o{ GEOGRAPHIC_MAP_MARKER_PHOTOS : "associates"
    
    %% Harris Matrix Relations
    MATRIX_HARRIS ||--o{ HARRIS_MATRIX_MAPPING : "has"
    MATRIX_HARRIS ||--o{ HARRIS_MATRIX_LAYOUT : "has"
    HARRIS_MATRIX_MAPPING ||--o{ UNITA_STRATIGRAFICHE : "references"
    HARRIS_MATRIX_MAPPING ||--o{ UNITA_STRATIGRAFICHE_MURARIE : "references"
    
    %% Construction Site Relations
    CANTIERE ||--o{ GIORNALE_CANTIERE : "has"
    GIORNALE_CANTIERE ||--o{ OPERATORE_CANTIERE : "involves"
    
    %% Form Relations
    FORM_SCHEMAS ||--o{ FORM_DATA : "defines"
    
    %% User Content Creation
    USERS ||--o{ GEOGRAPHIC_MAPS : "creates"
    USERS ||--o{ GEOGRAPHIC_MAP_LAYERS : "creates"
    USERS ||--o{ GEOGRAPHIC_MAP_MARKERS : "creates"
    USERS ||--o{ GEOGRAPHIC_MAP_MARKER_PHOTOS : "creates"
    USERS ||--o{ ARCHAEOLOGICAL_PLANS : "uploads"
    USERS ||--o{ FORM_SCHEMAS : "creates"
    USERS ||--o{ ICCD_RECORDS : "creates"
    USERS ||--o{ ICCD_RECORDS : "updates"
    USERS ||--o{ CANTIERE : "creates"
    USERS ||--o{ TAVOLE_GRAFICHE : "creates"
    USERS ||--o{ FOTOGRAFIE_ARCHEOLOGICHE : "creates"
    USERS ||--o{ MATRIX_HARRIS : "creates"
    USERS ||--o{ RELAZIONE_FINALE_SCAVO : "creates"
    USERS ||--o{ TEMPLATE_RELAZIONE : "creates"
    USERS ||--o{ ELCONCO_CONSEGNA : "creates"
    USERS ||--o{ CONFIGURAZIONE_EXPORT : "creates"
    USERS ||--o{ DOCUMENTS : "uploads"
    USERS ||--o{ FORM_DATA : "submits"
```

## Entity Descriptions

### Core User & Authentication
- **USERS**: User accounts with authentication credentials and preferences
- **ROLES**: System-wide roles (admin, archaeologist, student, etc.)
- **USER_PROFILE**: Extended user information (name, phone, bio, etc.)
- **USER_SITE_PERMISSIONS**: Multi-tenant permissions per site (read, write, admin)
- **USER_ACTIVITIES**: Audit trail of user actions
- **TOKEN_BLACKLIST**: Invalidated JWT tokens for security

### Archaeological Sites
- **ARCHAEOLOGICAL_SITES**: Main sites with full metadata (location, chronology, status, etc.)

### Stratigraphy (US/USM)
- **UNITA_STRATIGRAFICHE**: Stratigraphic Units (US) - standard MiC 2021
- **UNITA_STRATIGRAFICHE_MURARIE**: Wall Stratigraphic Units (USM) - for structures
- **US_FILES**: Files associated with US/USM (drawings, photos, documents)

### Archaeological Records
- **SCHEDE_TOMBE**: Burial records with anthropology and grave goods
- **INVENTARIO_REPERTI**: Artifact inventory with full cataloging
- **CAMPIONI_SCIENTIFICI**: Scientific samples (C14, pollen, bone, etc.)
- **MATERIALE_ARCHEOLOGICO**: Material catalog (many-to-many with artifacts)

### Photos & Documentation
- **PHOTOS**: Photo records with EXIF, archaeological metadata, deep zoom
- **PHOTO_MODIFICATIONS**: Change history for photos
- **DOCUMENTS**: General documents (PDFs, reports, etc.)

### Geographic Maps
- **GEOGRAPHIC_MAPS**: Interactive maps for sites
- **GEOGRAPHIC_MAP_LAYERS**: Map layers (GeoJSON features)
- **GEOGRAPHIC_MAP_MARKERS**: Map markers with photos
- **GEOGRAPHIC_MAP_MARKER_PHOTOS**: Photo-to-marker associations

### Archaeological Plans
- **ARCHAEOLOGICAL_PLANS**: Site plans (excavation plans, maps)

### Forms & ICCD
- **FORM_SCHEMAS**: Custom form definitions per site
- **FORM_DATA**: Submitted form data
- **ICCD_RECORDS**: ICCD catalog records (ICCD standard)

### Construction Site Management
- **CANTIERE**: Construction/excavation site management
- **GIORNALE_CANTIERE**: Daily site journals
- **OPERATORE_CANTIERE**: Site workers/operators

### Graphic Documentation
- **TAVOLE_GRAFICHE**: Graphic tables/plates
- **FOTOGRAFIE_ARCHEOLOGICHE**: Archaeological photography records

### Harris Matrix
- **MATRIX_HARRIS**: Harris Matrix definitions
- **HARRIS_MATRIX_MAPPING**: US/USM relationships in matrix
- **HARRIS_MATRIX_LAYOUT**: Matrix visualization layouts

### Final Reports
- **RELAZIONE_FINALE_SCAVO**: Final excavation reports
- **TEMPLATE_RELAZIONE**: Report templates

### Configurations
- **CONFIGURAZIONE_EXPORT**: Export configurations

## Key Relationships

1. **Multi-tenant**: All content belongs to an ARCHAEOLOGICAL_SITES
2. **Permissions**: USERS access sites via USER_SITE_PERMISSIONS
3. **Stratigraphy**: US/USM contain artifacts and samples
4. **Harris Matrix**: Links US/USM with stratigraphic relationships
5. **Photos**: Linked to sites, markers, and have modification history
6. **Burials**: Tombe have grave goods (artifacts) and samples
7. **Construction**: Cantiere has giornali and operatori
