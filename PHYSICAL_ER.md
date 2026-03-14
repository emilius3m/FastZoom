# Physical ER (auto-generated from SQLAlchemy metadata)

```mermaid
erDiagram
    %% ||--|| = FK NOT NULL (obbligatoria)
    %% ||--o{ = FK nullable (opzionale)
    %% }o--o{ = many-to-many via junction table

    archaeological_sites ||--|| archaeological_data : "archaeological_data.site_id"
    archaeological_plans ||--|| archaeological_data : "archaeological_data.plan_id"
    excavation_units ||--o{ archaeological_data : "archaeological_data.excavation_unit_id"
    form_schemas ||--|| archaeological_data : "archaeological_data.module_id"
    users ||--|| archaeological_data : "archaeological_data.collector_id"
    users ||--o{ archaeological_data : "archaeological_data.validated_by"
    archaeological_sites ||--|| archaeological_plans : "archaeological_plans.site_id"
    users ||--o{ archaeological_plans : "archaeological_plans.created_by"
    users ||--|| archaeological_sites : "archaeological_sites.created_by"
    users ||--o{ archaeological_sites : "archaeological_sites.updated_by"
    archaeological_sites ||--|| cantieri : "cantieri.site_id"
    archaeological_sites ||--|| configurazioni_export : "configurazioni_export.site_id"
    users ||--|| configurazioni_export : "configurazioni_export.created_by"
    users ||--o{ configurazioni_export : "configurazioni_export.updated_by"
    archaeological_sites ||--|| documents : "documents.site_id"
    users ||--|| documents : "documents.uploaded_by"
    users ||--|| documents : "documents.created_by"
    users ||--o{ documents : "documents.updated_by"
    archaeological_sites ||--|| elenchi_consegna : "elenchi_consegna.site_id"
    archaeological_sites ||--|| excavation_units : "excavation_units.site_id"
    archaeological_plans ||--|| excavation_units : "excavation_units.plan_id"
    users ||--|| excavation_units : "excavation_units.created_by"
    archaeological_sites ||--|| form_data : "form_data.site_id"
    form_schemas ||--|| form_data : "form_data.schema_id"
    users ||--|| form_data : "form_data.submitted_by"
    users ||--|| form_data : "form_data.created_by"
    users ||--o{ form_data : "form_data.updated_by"
    archaeological_sites ||--|| form_schemas : "form_schemas.site_id"
    users ||--|| form_schemas : "form_schemas.created_by"
    users ||--o{ form_schemas : "form_schemas.updated_by"
    archaeological_sites ||--|| fotografie_archeologiche : "fotografie_archeologiche.site_id"
    geographic_maps ||--|| geographic_map_layers : "geographic_map_layers.map_id"
    archaeological_sites ||--|| geographic_map_layers : "geographic_map_layers.site_id"
    users ||--|| geographic_map_layers : "geographic_map_layers.created_by"
    geographic_map_markers ||--|| geographic_map_marker_photos : "geographic_map_marker_photos.marker_id"
    photos ||--|| geographic_map_marker_photos : "geographic_map_marker_photos.photo_id"
    users ||--|| geographic_map_marker_photos : "geographic_map_marker_photos.created_by"
    geographic_maps ||--|| geographic_map_markers : "geographic_map_markers.map_id"
    archaeological_sites ||--|| geographic_map_markers : "geographic_map_markers.site_id"
    users ||--|| geographic_map_markers : "geographic_map_markers.created_by"
    archaeological_sites ||--|| geographic_maps : "geographic_maps.site_id"
    users ||--|| geographic_maps : "geographic_maps.created_by"
    giornali_cantiere ||--|| giornale_foto_associations : "giornale_foto_associations.giornale_id"
    photos ||--|| giornale_foto_associations : "giornale_foto_associations.foto_id"
    giornali_cantiere ||--|| giornale_mezzi : "giornale_mezzi.giornale_id"
    mezzi_cantiere ||--|| giornale_mezzi : "giornale_mezzi.mezzo_id"
    giornali_cantiere ||--|| giornale_operatori : "giornale_operatori.giornale_id"
    operatori_cantiere ||--|| giornale_operatori : "giornale_operatori.operatore_id"
    giornali_cantiere ||--|| giornale_operatori_associations : "giornale_operatori_associations.giornale_id"
    operatori_cantiere ||--|| giornale_operatori_associations : "giornale_operatori_associations.operatore_id"
    archaeological_sites ||--|| giornali_cantiere : "giornali_cantiere.site_id"
    cantieri ||--o{ giornali_cantiere : "giornali_cantiere.cantiere_id"
    users ||--|| giornali_cantiere : "giornali_cantiere.responsabile_id"
    users ||--o{ giornali_cantiere : "giornali_cantiere.validated_by_id"
    archaeological_sites ||--|| iccd_authority_files : "iccd_authority_files.site_id"
    users ||--|| iccd_authority_files : "iccd_authority_files.created_by"
    iccd_base_records ||--o{ iccd_base_records : "iccd_base_records.parent_id"
    archaeological_sites ||--|| iccd_base_records : "iccd_base_records.site_id"
    users ||--|| iccd_base_records : "iccd_base_records.created_by"
    archaeological_sites ||--|| matrix_harris : "matrix_harris.site_id"
    archaeological_sites ||--o{ mezzi_cantiere : "mezzi_cantiere.site_id"
    archaeological_sites ||--o{ operatori_cantiere : "operatori_cantiere.site_id"
    archaeological_sites ||--|| photos : "photos.site_id"
    users ||--|| photos : "photos.uploaded_by"
    users ||--|| photos : "photos.created_by"
    users ||--o{ photos : "photos.updated_by"
    archaeological_sites ||--|| relazioni_finali_scavo : "relazioni_finali_scavo.site_id"
    configurazioni_export ||--o{ relazioni_finali_scavo : "relazioni_finali_scavo.configurazione_export_id"
    users ||--o{ relazioni_finali_scavo : "relazioni_finali_scavo.approvata_da"
    relazioni_finali_scavo ||--o{ relazioni_finali_scavo : "relazioni_finali_scavo.versione_precedente_id"
    users ||--|| relazioni_finali_scavo : "relazioni_finali_scavo.created_by"
    users ||--o{ relazioni_finali_scavo : "relazioni_finali_scavo.updated_by"
    archaeological_sites ||--|| schede_tma : "schede_tma.site_id"
    users ||--|| schede_tma : "schede_tma.created_by"
    users ||--o{ schede_tma : "schede_tma.updated_by"
    archaeological_sites ||--|| tavole_grafiche : "tavole_grafiche.site_id"
    archaeological_sites ||--|| template_relazioni : "template_relazioni.site_id"
    users ||--|| template_relazioni : "template_relazioni.created_by"
    users ||--o{ template_relazioni : "template_relazioni.updated_by"
    schede_tma ||--|| tma_compilatori : "tma_compilatori.scheda_id"
    schede_tma ||--|| tma_fotografie : "tma_fotografie.scheda_id"
    schede_tma ||--|| tma_funzionari : "tma_funzionari.scheda_id"
    schede_tma ||--|| tma_materiali : "tma_materiali.scheda_id"
    archaeological_sites ||--|| tma_materiali_archeologici : "tma_materiali_archeologici.site_id"
    users ||--|| tma_materiali_archeologici : "tma_materiali_archeologici.created_by"
    users ||--o{ tma_materiali_archeologici : "tma_materiali_archeologici.updated_by"
    schede_tma ||--|| tma_motivazioni_cronologia : "tma_motivazioni_cronologia.scheda_id"
    users ||--|| token_blacklist : "token_blacklist.user_id"
    archaeological_sites ||--|| unita_stratigrafiche : "unita_stratigrafiche.site_id"
    users ||--|| unita_stratigrafiche : "unita_stratigrafiche.created_by"
    users ||--o{ unita_stratigrafiche : "unita_stratigrafiche.updated_by"
    archaeological_sites ||--|| unita_stratigrafiche_murarie : "unita_stratigrafiche_murarie.site_id"
    users ||--|| unita_stratigrafiche_murarie : "unita_stratigrafiche_murarie.created_by"
    users ||--o{ unita_stratigrafiche_murarie : "unita_stratigrafiche_murarie.updated_by"
    archaeological_sites ||--|| us_files : "us_files.site_id"
    users ||--|| us_files : "us_files.uploaded_by"
    users ||--o{ us_files : "us_files.validated_by"
    users ||--|| us_files : "us_files.created_by"
    users ||--o{ us_files : "us_files.updated_by"
    unita_stratigrafiche ||--|| us_files_associations : "us_files_associations.us_id"
    us_files ||--|| us_files_associations : "us_files_associations.file_id"
    users ||--|| user_activities : "user_activities.user_id"
    archaeological_sites ||--o{ user_activities : "user_activities.site_id"
    users ||--|| user_profiles : "user_profiles.user_id"
    users ||--|| user_roles_associations : "user_roles_associations.user_id"
    roles ||--|| user_roles_associations : "user_roles_associations.role_id"
    users ||--o{ user_roles_associations : "user_roles_associations.assigned_by"
    users ||--|| user_site_permissions : "user_site_permissions.user_id"
    archaeological_sites ||--|| user_site_permissions : "user_site_permissions.site_id"
    users ||--o{ user_site_permissions : "user_site_permissions.granted_by"
    unita_stratigrafiche_murarie ||--|| usm_files_associations : "usm_files_associations.usm_id"
    us_files ||--|| usm_files_associations : "usm_files_associations.file_id"

    archaeological_data {
        UUID id PK
        UUID site_id FK
        UUID plan_id FK
        VARCHAR(20) excavation_unit_id FK
        UUID module_id FK
        FLOAT coordinates_x
        FLOAT coordinates_y
        FLOAT elevation
        JSON data
        DATETIME collection_date
        UUID collector_id FK
        VARCHAR(50) collection_method
        FLOAT accuracy
        BOOLEAN is_validated
        UUID validated_by FK
        DATETIME validated_at
        TEXT validation_notes
        DATETIME created_at
        DATETIME updated_at
    }

    archaeological_plans {
        UUID id PK
        UUID site_id FK
        VARCHAR(255) name
        TEXT description
        VARCHAR(100) plan_type
        VARCHAR(500) image_path
        VARCHAR(255) image_filename
        INTEGER file_size
        VARCHAR(100) coordinate_system
        FLOAT origin_x
        FLOAT origin_y
        FLOAT scale_factor
        FLOAT bounds_north
        FLOAT bounds_south
        FLOAT bounds_east
        FLOAT bounds_west
        INTEGER image_width
        INTEGER image_height
        DATETIME survey_date
        VARCHAR(255) surveyor
        VARCHAR(50) drawing_scale
        TEXT notes
        JSON grid_config
        BOOLEAN is_active
        BOOLEAN is_primary
        DATETIME created_at
        DATETIME updated_at
        UUID created_by FK
    }

    archaeological_sites {
        VARCHAR(36) id PK
        VARCHAR(200) name
        VARCHAR(50) code UK
        JSON alternative_names
        TEXT description
        VARCHAR(500) short_description
        VARCHAR(50) site_type
        VARCHAR(200) historical_period
        VARCHAR(100) chronology_start
        VARCHAR(100) chronology_end
        VARCHAR(200) cultural_attribution
        VARCHAR(20) coordinates_lat
        VARCHAR(20) coordinates_lng
        FLOAT coordinates_precision
        FLOAT elevation
        VARCHAR(100) country
        VARCHAR(100) region
        VARCHAR(100) province
        VARCHAR(100) municipality
        VARCHAR(200) locality
        VARCHAR(300) address
        VARCHAR(50) cadastral_sheet
        JSON cadastral_parcels
        VARCHAR(20) status
        VARCHAR(20) research_status
        DATETIME discovery_date
        DATETIME excavation_start
        DATETIME excavation_end
        VARCHAR(300) research_project
        VARCHAR(300) funding_source
        VARCHAR(200) excavation_method
        JSON bibliography
        JSON external_references
        VARCHAR(100) authorization_number
        DATETIME authorization_date
        VARCHAR(300) superintendency
        VARCHAR(50) default_coordinate_system
        VARCHAR(10) default_measurement_unit
        JSON site_grid_system
        BOOLEAN is_public
        BOOLEAN is_template
        INTEGER storage_quota_mb
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(36) created_by FK
        VARCHAR(36) updated_by FK
        BOOLEAN is_deleted
        DATETIME deleted_at
        VARCHAR(36) deleted_by
    }

    cantieri {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(200) nome
        VARCHAR(50) codice
        TEXT descrizione
        VARCHAR(200) committente
        VARCHAR(200) impresa_esecutrice
        VARCHAR(200) direttore_lavori
        VARCHAR(200) responsabile_procedimento
        TEXT oggetto_appalto
        VARCHAR(50) codice_cup
        VARCHAR(50) codice_cig
        NUMERIC(15,2) importo_lavori
        DATE data_inizio_prevista
        DATE data_fine_prevista
        DATE data_inizio_effettiva
        DATE data_fine_effettiva
        VARCHAR(20) stato
        TEXT area_descrizione
        VARCHAR(50) coordinate_lat
        VARCHAR(50) coordinate_lon
        VARCHAR(20) quota
        VARCHAR(200) responsabile_cantiere
        VARCHAR(100) tipologia_intervento
        INTEGER priorita
        VARCHAR(50) iccd_re_tipo
        VARCHAR(50) iccd_re_metodo
        TEXT iccd_geometria
        DATETIME created_at
        DATETIME updated_at
        BOOLEAN is_active
        DATETIME deleted_at
    }

    configurazioni_export {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(200) nome_configurazione
        TEXT descrizione
        VARCHAR(100) destinatario
        VARCHAR(300) ente_destinatario
        BOOLEAN includi_us
        BOOLEAN includi_usm
        BOOLEAN includi_foto
        BOOLEAN includi_documenti
        BOOLEAN includi_tavole
        BOOLEAN solo_validati
        DATE data_inizio
        DATE data_fine
        JSON settori_inclusi
        VARCHAR(20) formato_principale
        JSON formati_aggiuntivi
        TEXT template_copertina
        BOOLEAN template_indice
        BOOLEAN template_bibliografia
        JSON campi_us
        JSON campi_personalizzati
        TEXT intestazione_ente
        VARCHAR(500) logo_path
        VARCHAR(200) responsabile_scientifico
        VARCHAR(200) direttore_scavo
        VARCHAR(200) compilatore
        BOOLEAN export_automatico
        VARCHAR(50) frequenza_export
        DATETIME ultimo_export
        DATETIME prossimo_export
        BOOLEAN attiva
        BOOLEAN predefinita
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(36) created_by FK
        VARCHAR(36) updated_by FK
    }

    documents {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(500) title
        TEXT description
        VARCHAR(100) category
        VARCHAR(100) doc_type
        VARCHAR(500) filename
        VARCHAR(1000) filepath
        BIGINT filesize
        VARCHAR(200) mimetype
        VARCHAR(500) tags
        DATETIME doc_date
        VARCHAR(200) author
        BOOLEAN is_public
        INTEGER version
        TEXT version_notes
        DATETIME uploaded_at
        VARCHAR(36) uploaded_by FK
        DATETIME updated_at
        VARCHAR(36) created_by FK
        VARCHAR(36) updated_by FK
        BOOLEAN is_deleted
        DATETIME deleted_at
        VARCHAR(36) deleted_by
    }

    elenchi_consegna {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(50) tipo_elenco
        VARCHAR(200) titolo
        JSON contenuto
        BOOLEAN generato_automaticamente
        DATETIME data_generazione
        VARCHAR(20) formato_export
        VARCHAR(500) file_path
        VARCHAR(200) compilatore
        TEXT note
        DATETIME created_at
        DATETIME updated_at
    }

    excavation_units {
        VARCHAR(20) id PK
        UUID site_id FK
        UUID plan_id FK
        FLOAT coordinates_x
        FLOAT coordinates_y
        FLOAT size_x
        FLOAT size_y
        VARCHAR(20) status
        FLOAT current_depth
        FLOAT max_depth
        JSON stratigraphic_sequence
        JSON finds_summary
        VARCHAR(100) supervisor
        JSON team_members
        INTEGER priority
        TEXT notes
        TEXT soil_description
        TEXT preservation_conditions
        DATETIME start_date
        DATETIME completion_date
        DATETIME last_excavation_date
        VARCHAR(100) excavation_method
        VARCHAR(20) documentation_level
        DATETIME created_at
        DATETIME updated_at
        UUID created_by FK
    }

    form_data {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(36) schema_id FK
        JSON data
        VARCHAR(36) submitted_by FK
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(36) created_by FK
        VARCHAR(36) updated_by FK
    }

    form_schemas {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(255) name
        TEXT description
        VARCHAR(50) category
        TEXT schema_json
        BOOLEAN is_active
        VARCHAR(36) created_by FK
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(36) updated_by FK
    }

    fotografie_archeologiche {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(20) numero_foto UK
        INTEGER numero_progressivo
        VARCHAR(30) tipo_foto
        VARCHAR(200) soggetto_principale
        TEXT descrizione
        VARCHAR(500) file_path
        VARCHAR(255) file_name
        VARCHAR(10) file_format
        INTEGER file_size
        VARCHAR(100) camera_make
        VARCHAR(100) camera_model
        VARCHAR(100) lens_model
        VARCHAR(20) focal_length
        VARCHAR(10) aperture
        VARCHAR(20) shutter_speed
        VARCHAR(10) iso
        DATETIME data_scatto
        VARCHAR(10) ora_scatto
        NUMERIC(10,8) gps_latitude
        NUMERIC(11,8) gps_longitude
        NUMERIC(8,3) quota
        VARCHAR(36) us_fotografata_id
        VARCHAR(20) direzione_scatto
        NUMERIC(5,2) altezza_scatto
        NUMERIC(5,2) distanza_soggetto
        VARCHAR(50) tipo_illuminazione
        VARCHAR(100) condizioni_luce
        BOOLEAN post_elaborazione
        VARCHAR(100) software_elaborazione
        TEXT note_elaborazione
        VARCHAR(20) qualita
        VARCHAR(100) utilizzo_previsto
        TEXT tag_liberi
        TEXT parole_chiave
        VARCHAR(200) fotografo
        VARCHAR(200) assistente
        BOOLEAN pubblicabile
        VARCHAR(200) diritti_utilizzo
        VARCHAR(200) copyright
        TEXT note_tecniche
        TEXT note_contenuto
        DATETIME created_at
        DATETIME updated_at
    }

    geographic_map_layers {
        VARCHAR(36) id PK
        VARCHAR(36) map_id FK
        VARCHAR(36) site_id FK
        VARCHAR(255) name
        TEXT description
        VARCHAR(100) layer_type
        JSON geojson_data
        INTEGER features_count
        JSON style_config
        BOOLEAN is_visible
        INTEGER display_order
        FLOAT bounds_north
        FLOAT bounds_south
        FLOAT bounds_east
        FLOAT bounds_west
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(36) created_by FK
    }

    geographic_map_marker_photos {
        VARCHAR(36) id PK
        VARCHAR(36) marker_id FK
        VARCHAR(36) photo_id FK
        TEXT description
        INTEGER display_order
        BOOLEAN is_primary
        DATETIME created_at
        VARCHAR(36) created_by FK
    }

    geographic_map_markers {
        VARCHAR(36) id PK
        VARCHAR(36) map_id FK
        VARCHAR(36) site_id FK
        FLOAT latitude
        FLOAT longitude
        VARCHAR(255) title
        TEXT description
        VARCHAR(100) marker_type
        VARCHAR(10) icon
        VARCHAR(20) color
        JSON metadata
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(36) created_by FK
    }

    geographic_maps {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(255) name
        TEXT description
        FLOAT bounds_north
        FLOAT bounds_south
        FLOAT bounds_east
        FLOAT bounds_west
        FLOAT center_lat
        FLOAT center_lng
        INTEGER default_zoom
        JSON map_config
        BOOLEAN is_active
        BOOLEAN is_default
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(36) created_by FK
    }

    giornale_foto_associations {
        VARCHAR(36) giornale_id PK FK
        VARCHAR(36) foto_id PK FK
        TEXT didascalia
        INTEGER ordine
        DATETIME created_at
    }

    giornale_mezzi {
        VARCHAR(36) id PK
        VARCHAR(36) giornale_id FK
        VARCHAR(36) mezzo_id FK
        NUMERIC(5,2) ore_utilizzo
        TEXT note_utilizzo
        DATETIME created_at
    }

    giornale_operatori {
        VARCHAR(36) id PK
        VARCHAR(36) giornale_id FK
        VARCHAR(36) operatore_id FK
        NUMERIC(5,2) ore_lavorate
        TEXT note_presenza
        DATETIME created_at
    }

    giornale_operatori_associations {
        VARCHAR(36) giornale_id PK FK
        VARCHAR(36) operatore_id PK FK
        FLOAT ore_lavorate
        TEXT note_giornaliere
    }

    giornali_cantiere {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(36) cantiere_id FK
        DATE data
        TIME ora_inizio
        TIME ora_fine
        VARCHAR(20) condizioni_meteo
        INTEGER temperatura
        INTEGER temperatura_min
        INTEGER temperatura_max
        TEXT note_meteo
        VARCHAR(200) compilatore
        VARCHAR(200) area_intervento
        VARCHAR(100) saggio
        TEXT obiettivi
        TEXT descrizione_lavori
        TEXT modalita_lavorazioni
        TEXT attrezzatura_utilizzata
        TEXT us_elaborate
        TEXT usm_elaborate
        TEXT usr_elaborate
        TEXT materiali_rinvenuti
        TEXT interpretazione
        TEXT campioni_prelevati
        TEXT strutture
        TEXT documentazione_prodotta
        TEXT sopralluoghi
        TEXT disposizioni_rup
        TEXT disposizioni_direttore
        TEXT contestazioni
        TEXT sospensioni
        TEXT incidenti
        TEXT note_generali
        TEXT problematiche
        TEXT forniture
        VARCHAR(36) responsabile_id FK
        VARCHAR(200) responsabile_nome
        BOOLEAN validato
        DATETIME data_validazione
        VARCHAR(500) firma_digitale_hash
        VARCHAR(36) validated_by_id FK
        VARCHAR(128) content_hash
        DATETIME legal_freeze_at
        VARCHAR(50) signature_type
        VARCHAR(1000) signed_file_path
        VARCHAR(255) signature_reference
        DATETIME signature_timestamp
        VARCHAR(100) protocol_number
        DATE protocol_date
        VARCHAR(30) legal_status
        TEXT validation_audit
        TEXT allegati_paths
        DATETIME created_at
        DATETIME updated_at
        INTEGER version
    }

    harris_matrix_mappings {
        UUID id PK
        UUID site_id
        VARCHAR(255) session_id
        VARCHAR(255) temp_id
        UUID db_id
        VARCHAR(50) unit_code
        VARCHAR(255) transaction_id
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(20) status
        UUID user_id
        DATETIME expires_at
        INTEGER retry_count
        DATETIME last_accessed
    }

    iccd_authority_files {
        VARCHAR(36) id PK
        VARCHAR(10) authority_type
        VARCHAR(20) authority_code UK
        VARCHAR(200) name
        TEXT description
        JSON authority_data
        VARCHAR(36) site_id FK
        VARCHAR(36) created_by FK
        DATETIME created_at
    }

    iccd_base_records {
        VARCHAR(36) id PK
        VARCHAR(2) nct_region
        VARCHAR(8) nct_number
        VARCHAR(2) nct_suffix
        VARCHAR(5) schema_type
        VARCHAR(10) schema_version
        VARCHAR(1) level
        JSON iccd_data
        VARCHAR(36) parent_id FK
        VARCHAR(36) site_id FK
        VARCHAR(36) created_by FK
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(20) status
    }

    iccd_schema_templates {
        VARCHAR(36) id PK
        VARCHAR(5) schema_type UK
        VARCHAR(255) name
        TEXT description
        VARCHAR(10) version
        JSON json_schema
        JSON ui_schema
        VARCHAR(50) category
        VARCHAR(10) icon
        BOOLEAN is_active
        BOOLEAN standard_compliant
        DATETIME created_at
        DATETIME updated_at
    }

    matrix_harris {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(200) nome_matrix
        TEXT descrizione
        VARCHAR(100) area
        VARCHAR(50) settore
        JSON layout_config
        JSON stile_grafico
        JSON fasi_cronologiche
        JSON periodi_culturali
        TEXT interpretazione_generale
        TEXT sequenza_attivita
        VARCHAR(500) immagine_path
        VARCHAR(500) pdf_path
        DATETIME ultima_generazione
        BOOLEAN validata
        VARCHAR(200) validata_da
        DATE data_validazione
        TEXT note_validazione
        VARCHAR(10) versione
        TEXT note_versione
        VARCHAR(200) compilatore
        VARCHAR(200) revisore
        DATE data_compilazione
        DATE data_revisione
        DATETIME created_at
        DATETIME updated_at
    }

    mezzi_cantiere {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(150) nome
        VARCHAR(100) tipo
        VARCHAR(100) marca
        VARCHAR(100) modello
        VARCHAR(20) targa
        VARCHAR(80) matricola
        BOOLEAN is_active
        TEXT note
        DATETIME created_at
        DATETIME updated_at
    }

    operatori_cantiere {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(100) nome
        VARCHAR(100) cognome
        VARCHAR(16) codice_fiscale UK
        VARCHAR(150) qualifica
        VARCHAR(100) ruolo
        VARCHAR(200) specializzazione
        VARCHAR(320) email
        VARCHAR(20) telefono
        TEXT abilitazioni
        TEXT note
        BOOLEAN is_active
        INTEGER ore_totali
        DATETIME created_at
        DATETIME updated_at
    }

    photos {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(255) filename
        VARCHAR(255) original_filename
        VARCHAR(500) filepath
        VARCHAR(500) thumbnail_path
        BIGINT file_size
        VARCHAR(100) mime_type
        INTEGER width
        INTEGER height
        VARCHAR(10) format
        VARCHAR(20) color_space
        VARCHAR(50) color_profile
        VARCHAR(200) title
        TEXT description
        VARCHAR(500) keywords
        VARCHAR(50) photo_type
        VARCHAR(100) camera_make
        VARCHAR(100) camera_model
        VARCHAR(200) lens_info
        INTEGER iso
        VARCHAR(20) aperture
        VARCHAR(20) shutter_speed
        VARCHAR(20) focal_length
        VARCHAR(50) us_reference
        VARCHAR(50) usm_reference
        VARCHAR(50) tomba_reference
        VARCHAR(50) reperto_reference
        VARCHAR(50) gps_lat
        VARCHAR(50) gps_lng
        VARCHAR(50) gps_altitude
        VARCHAR(100) inventory_number
        VARCHAR(100) catalog_number
        VARCHAR(100) excavation_area
        VARCHAR(100) stratigraphic_unit
        VARCHAR(50) grid_square
        FLOAT depth_level
        DATETIME find_date
        VARCHAR(200) finder
        VARCHAR(100) excavation_campaign
        VARCHAR(50) material
        VARCHAR(255) material_details
        VARCHAR(100) object_type
        VARCHAR(200) object_function
        FLOAT length_cm
        FLOAT width_cm
        FLOAT height_cm
        FLOAT diameter_cm
        FLOAT weight_grams
        VARCHAR(100) chronology_period
        VARCHAR(100) chronology_culture
        VARCHAR(50) dating_from
        VARCHAR(50) dating_to
        TEXT dating_notes
        VARCHAR(50) conservation_status
        TEXT conservation_notes
        TEXT restoration_history
        TEXT bibliography
        TEXT comparative_references
        TEXT external_links
        VARCHAR(255) copyright_holder
        VARCHAR(100) license_type
        TEXT usage_rights
        BOOLEAN is_published
        BOOLEAN is_validated
        TEXT validation_notes
        BOOLEAN has_deep_zoom
        VARCHAR(20) deepzoom_status
        DATETIME deepzoom_processed_at
        INTEGER tile_count
        INTEGER max_zoom_level
        VARCHAR(200) photographer
        DATETIME photo_date
        VARCHAR(36) uploaded_by FK
        BOOLEAN is_featured
        BOOLEAN is_public
        INTEGER sort_order
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(36) created_by FK
        VARCHAR(36) updated_by FK
    }

    relazioni_finali_scavo {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(300) titolo
        VARCHAR(300) sottotitolo
        VARCHAR(50) codice_relazione
        VARCHAR(300) ente_responsabile
        VARCHAR(300) soprintendenza
        VARCHAR(100) autorizzazione_scavo
        DATE data_inizio_scavo
        DATE data_fine_scavo
        DATE data_consegna
        VARCHAR(200) direttore_scientifico
        VARCHAR(200) direttore_scavo
        JSON assistenti
        JSON specialisti
        TEXT premessa
        TEXT inquadramento_storico
        TEXT inquadramento_geologico
        TEXT metodologia
        TEXT risultati
        TEXT interpretazione
        TEXT conclusioni
        TEXT cronologia
        TEXT bibliografia
        TEXT ringraziamenti
        JSON elenco_us
        JSON elenco_foto
        JSON elenco_tavole
        VARCHAR(36) configurazione_export_id FK
        VARCHAR(20) formato_finale
        BOOLEAN include_allegati_digitali
        VARCHAR(500) file_relazione_pdf
        VARCHAR(500) file_allegati_zip
        VARCHAR(500) file_completo_path
        VARCHAR(20) stato
        VARCHAR(36) approvata_da FK
        DATETIME data_approvazione
        TEXT note_approvazione
        VARCHAR(300) consegnata_a
        DATETIME data_consegna_effettiva
        VARCHAR(500) ricevuta_consegna
        VARCHAR(10) versione
        TEXT note_versione
        VARCHAR(36) versione_precedente_id FK
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(36) created_by FK
        VARCHAR(36) updated_by FK
        BOOLEAN is_deleted
        DATETIME deleted_at
        VARCHAR(36) deleted_by
    }

    roles {
        VARCHAR(36) id PK
        VARCHAR(50) name UK
        VARCHAR(100) display_name
        TEXT description
        BOOLEAN is_system_role
        BOOLEAN is_active
        JSON base_permissions
        DATETIME created_at
        DATETIME updated_at
    }

    schede_tma {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(4) tsk
        VARCHAR(5) lir
        VARCHAR(2) nctr
        VARCHAR(8) nctn
        VARCHAR(25) esc
        VARCHAR(25) ecp
        VARCHAR(100) ogtd
        VARCHAR(250) ogtm
        VARCHAR(50) pvcs
        VARCHAR(50) pvcr
        VARCHAR(3) pvcp
        VARCHAR(50) pvcc
        VARCHAR(100) ldct
        VARCHAR(250) ldcn
        VARCHAR(250) ldcu
        VARCHAR(500) ldcs
        JSON altre_localizzazioni
        VARCHAR(200) scan
        VARCHAR(200) dscf
        VARCHAR(200) dsca
        VARCHAR(100) dsct
        VARCHAR(100) dscm
        VARCHAR(4) dscd
        VARCHAR(50) dscu
        VARCHAR(250) dscn
        VARCHAR(50) dtzg
        TEXT nsc
        VARCHAR(120) cdgg
        INTEGER adsp
        VARCHAR(70) adsm
        VARCHAR(4) cmpd
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(36) created_by FK
        VARCHAR(36) updated_by FK
        BOOLEAN is_deleted
        DATETIME deleted_at
        VARCHAR(36) deleted_by
    }

    tavole_grafiche {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(20) numero_tavola
        INTEGER numero_progressivo
        VARCHAR(30) tipo_tavola
        VARCHAR(200) titolo
        TEXT descrizione
        VARCHAR(10) scala
        VARCHAR(10) formato_foglio
        VARCHAR(500) file_path
        VARCHAR(255) file_name
        VARCHAR(10) file_format
        INTEGER file_size
        VARCHAR(200) autore_rilievo
        VARCHAR(200) autore_disegno
        DATE data_rilievo
        DATE data_disegno
        VARCHAR(200) area_rappresentata
        TEXT us_rappresentate
        TEXT coordinate_note
        VARCHAR(100) sistema_riferimento
        VARCHAR(10) versione
        VARCHAR(20) stato
        TEXT note_versione
        BOOLEAN approvata
        VARCHAR(200) approvata_da
        DATE data_approvazione
        BOOLEAN consegnata
        DATE data_consegna
        VARCHAR(200) destinatario
        TEXT note_tecniche
        TEXT note_generali
        DATETIME created_at
        DATETIME updated_at
    }

    template_relazioni {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(200) nome_template
        TEXT descrizione
        VARCHAR(100) categoria
        JSON sezioni_obbligatorie
        JSON sezioni_opzionali
        TEXT template_premessa
        TEXT template_inquadramento
        TEXT template_metodologia
        TEXT template_risultati
        TEXT template_conclusioni
        JSON stile_testo
        JSON stile_titoli
        VARCHAR(20) formato_pagina
        JSON margini
        TEXT intestazione_template
        TEXT piedi_pagina_template
        BOOLEAN include_numero_pagina
        JSON firme_template
        BOOLEAN attivo
        BOOLEAN predefinito
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(36) created_by FK
        VARCHAR(36) updated_by FK
    }

    tma_compilatori {
        INTEGER id PK
        VARCHAR(36) scheda_id FK
        INTEGER ordine
        VARCHAR(70) nome
    }

    tma_fotografie {
        INTEGER id PK
        VARCHAR(36) scheda_id FK
        INTEGER ordine
        VARCHAR(100) ftax
        VARCHAR(100) ftap
        VARCHAR(200) ftan
        VARCHAR(500) file_path
    }

    tma_funzionari {
        INTEGER id PK
        VARCHAR(36) scheda_id FK
        INTEGER ordine
        VARCHAR(70) nome
    }

    tma_materiali {
        INTEGER id PK
        VARCHAR(36) scheda_id FK
        INTEGER ordine
        VARCHAR(100) macc
        VARCHAR(150) macl
        VARCHAR(150) macd
        VARCHAR(150) macp
        INTEGER macq
        VARCHAR(250) mas
    }

    tma_materiali_archeologici {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(4) tsk
        VARCHAR(5) lir
        VARCHAR(2) nctr
        VARCHAR(8) nctn
        VARCHAR(25) esc
        VARCHAR(25) ecp
        VARCHAR(100) ogtd
        VARCHAR(250) ogtm
        VARCHAR(50) pvcs
        VARCHAR(25) pvcr
        VARCHAR(3) pvcp
        VARCHAR(50) pvcc
        VARCHAR(50) dtzg
        JSON dtm
        VARCHAR(100) macc
        VARCHAR(100) macq
        JSON ma_items
        VARCHAR(50) cdgg
        VARCHAR(1) adsp
        VARCHAR(70) adsm
        VARCHAR(4) cmpd
        JSON cmpn
        JSON fur
        JSON ldc
        JSON provenienze
        JSON scavo
        TEXT nsc
        JSON fta
        JSON entita_multimediali
        TEXT notes
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(36) created_by FK
        VARCHAR(36) updated_by FK
        BOOLEAN is_deleted
        DATETIME deleted_at
        VARCHAR(36) deleted_by
    }

    tma_motivazioni_cronologia {
        INTEGER id PK
        VARCHAR(36) scheda_id FK
        INTEGER ordine
        VARCHAR(250) motivazione
    }

    token_blacklist {
        VARCHAR(36) id PK
        VARCHAR(255) token_jti UK
        VARCHAR(36) user_id FK
        DATETIME invalidated_at
        VARCHAR(100) reason
        VARCHAR(45) ip_address
        VARCHAR(500) user_agent
    }

    unita_stratigrafiche {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(20) tipo
        VARCHAR(16) us_code
        VARCHAR(200) ente_responsabile
        INTEGER anno
        VARCHAR(200) ufficio_mic
        VARCHAR(200) identificativo_rif
        VARCHAR(200) localita
        VARCHAR(200) area_struttura
        VARCHAR(100) saggio
        VARCHAR(200) ambiente_unita_funzione
        VARCHAR(200) posizione
        VARCHAR(200) settori
        TEXT piante_riferimenti
        TEXT prospetti_riferimenti
        TEXT sezioni_riferimenti
        TEXT definizione
        TEXT criteri_distinzione
        TEXT modo_formazione
        TEXT componenti_inorganici
        TEXT componenti_organici
        VARCHAR(50) consistenza
        VARCHAR(50) colore
        VARCHAR(100) misure
        TEXT stato_conservazione
        JSON sequenza_fisica
        TEXT descrizione
        TEXT osservazioni
        TEXT interpretazione
        VARCHAR(200) datazione
        VARCHAR(100) periodo
        VARCHAR(100) fase
        TEXT elementi_datanti
        TEXT dati_quantitativi_reperti
        JSON campionature
        VARCHAR(50) affidabilita_stratigrafica
        VARCHAR(200) responsabile_scientifico
        DATE data_rilevamento
        VARCHAR(200) responsabile_compilazione
        DATE data_rielaborazione
        VARCHAR(200) responsabile_rielaborazione
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(36) created_by FK
        VARCHAR(36) updated_by FK
        BOOLEAN is_deleted
        DATETIME deleted_at
        VARCHAR(36) deleted_by
    }

    unita_stratigrafiche_murarie {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(16) usm_code
        VARCHAR(200) ente_responsabile
        INTEGER anno
        VARCHAR(200) ufficio_mic
        VARCHAR(200) identificativo_rif
        VARCHAR(200) localita
        VARCHAR(200) area_struttura
        VARCHAR(100) saggio
        VARCHAR(200) ambiente_unita_funzione
        VARCHAR(200) posizione
        VARCHAR(200) settori
        TEXT piante_riferimenti
        TEXT prospetti_riferimenti
        TEXT sezioni_riferimenti
        VARCHAR(100) misure
        NUMERIC(10,2) superficie_analizzata
        TEXT definizione
        VARCHAR(200) tecnica_costruttiva
        BOOLEAN sezione_muraria_visibile
        VARCHAR(200) sezione_muraria_tipo
        VARCHAR(50) sezione_muraria_spessore
        VARCHAR(200) funzione_statica
        VARCHAR(200) modulo
        TEXT criteri_distinzione
        TEXT provenienza_materiali
        VARCHAR(100) orientamento
        VARCHAR(200) uso_primario
        VARCHAR(200) riutilizzo
        TEXT stato_conservazione
        JSON materiali_laterizi
        JSON materiali_elementi_litici
        TEXT materiali_altro
        JSON legante
        TEXT legante_altro
        TEXT finiture_elementi_particolari
        JSON sequenza_fisica
        TEXT descrizione
        TEXT osservazioni
        TEXT interpretazione
        VARCHAR(200) datazione
        VARCHAR(100) periodo
        VARCHAR(100) fase
        TEXT elementi_datanti
        JSON campionature
        VARCHAR(50) affidabilita_stratigrafica
        VARCHAR(200) responsabile_scientifico
        DATE data_rilevamento
        VARCHAR(200) responsabile_compilazione
        DATE data_rielaborazione
        VARCHAR(200) responsabile_rielaborazione
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(36) created_by FK
        VARCHAR(36) updated_by FK
        BOOLEAN is_deleted
        DATETIME deleted_at
        VARCHAR(36) deleted_by
    }

    us_files {
        VARCHAR(36) id PK
        VARCHAR(36) site_id FK
        VARCHAR(255) filename
        VARCHAR(255) original_filename
        VARCHAR(500) filepath
        INTEGER filesize
        VARCHAR(100) mimetype
        VARCHAR(50) file_category
        VARCHAR(200) title
        TEXT description
        VARCHAR(50) scale_ratio
        VARCHAR(50) drawing_type
        VARCHAR(50) tavola_number
        DATE photo_date
        VARCHAR(200) photographer
        VARCHAR(200) camera_info
        INTEGER width
        INTEGER height
        INTEGER dpi
        BOOLEAN is_deepzoom_enabled
        VARCHAR(20) deepzoom_status
        VARCHAR(500) thumbnail_path
        VARCHAR(36) uploaded_by FK
        BOOLEAN is_published
        BOOLEAN is_validated
        VARCHAR(36) validated_by FK
        DATETIME validated_at
        DATETIME created_at
        DATETIME updated_at
        VARCHAR(36) created_by FK
        VARCHAR(36) updated_by FK
    }

    us_files_associations {
        VARCHAR(36) us_id PK FK
        VARCHAR(36) file_id PK FK
        VARCHAR(50) file_type
        DATETIME created_at
        INTEGER ordine
    }

    user_activities {
        VARCHAR(36) id PK
        VARCHAR(36) user_id FK
        DATETIME activity_date
        VARCHAR(200) activity_type
        VARCHAR(1024) activity_desc
        VARCHAR(36) site_id FK
        VARCHAR(36) photo_id
        VARCHAR(36) us_id
        VARCHAR(36) usm_id
        VARCHAR(36) tomba_id
        VARCHAR(36) reperto_id
        VARCHAR(45) ip_address
        TEXT user_agent
        TEXT extra_data
        DATETIME created_at
    }

    user_profiles {
        VARCHAR(36) id PK
        VARCHAR(36) user_id FK
        VARCHAR(100) first_name
        VARCHAR(100) last_name
        VARCHAR(20) phone
        VARCHAR(100) department
        VARCHAR(10) gender
        DATETIME date_of_birth
        VARCHAR(50) city
        VARCHAR(50) country
        VARCHAR(255) address
        VARCHAR(100) company
        TEXT bio
        VARCHAR(200) qualifica_professionale
        VARCHAR(300) ente_appartenenza
        VARCHAR(50) codice_archeologo
        VARCHAR(500) avatar_url
    }

    user_roles_associations {
        VARCHAR(36) user_id PK FK
        VARCHAR(36) role_id PK FK
        DATETIME assigned_at
        VARCHAR(36) assigned_by FK
    }

    user_site_permissions {
        VARCHAR(36) id PK
        VARCHAR(36) user_id FK
        VARCHAR(36) site_id FK
        VARCHAR(50) permission_level
        JSON permissions
        VARCHAR(50) site_role
        VARCHAR(36) granted_by FK
        DATETIME granted_at
        DATETIME expires_at
        TEXT notes
        BOOLEAN is_active
        DATETIME created_at
        DATETIME updated_at
    }

    users {
        VARCHAR(36) id PK
        VARCHAR(255) email UK
        VARCHAR(100) username UK
        VARCHAR(255) hashed_password
        VARCHAR(20) status
        BOOLEAN is_active
        BOOLEAN is_verified
        BOOLEAN is_superuser
        DATETIME email_verified_at
        DATETIME last_login_at
        INTEGER login_count
        JSON preferences
        DATETIME created_at
        DATETIME updated_at
        BOOLEAN is_deleted
        DATETIME deleted_at
        VARCHAR(36) deleted_by
    }

    usm_files_associations {
        VARCHAR(36) usm_id PK FK
        VARCHAR(36) file_id PK FK
        VARCHAR(50) file_type
        DATETIME created_at
        INTEGER ordine
    }

```

## Regeneration

- Command: `python scripts/generate_physical_er.py`
- Source of truth: `Base.metadata` from SQLAlchemy models