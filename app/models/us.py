# app/models/us.py
from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from uuid import uuid4, UUID

from sqlalchemy import (
    Column, String, Text, Enum, Date, DateTime, Boolean, ForeignKey, Numeric, Integer
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from sqlalchemy import JSON
JSONType = JSON
from sqlalchemy.orm import relationship
from app.database.base import Base

# Vocabolari controllati (estratti dalle schede)
ConsistenzaEnum = Enum(
    "COMPATTA", "MEDIA", "FRIABILE", name="consistenza_enum", native_enum=False
)
AffidabilitaEnum = Enum(
    "ALTA", "MEDIA", "BASSA", name="affidabilita_enum", native_enum=False
)
# Colori Munsell gestiti come stringa; materiali e lavorazioni come liste tipizzate

class UnitaStratigrafica(Base):
    __tablename__ = "unita_stratigrafiche"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    site_id = Column(PG_UUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=False)

    # Intestazione e contesto
    us_code = Column(String(16), nullable=False, index=True)  # es. US001
    ente_responsabile = Column(String(200))
    anno = Column(Integer)
    ufficio_mic = Column(String(200))
    identificativo_rif = Column(String(200))  # saggio/edificio/struttura/deposizione
    localita = Column(String(200))
    area_struttura = Column(String(200))
    saggio = Column(String(100))
    ambiente_unita_funzione = Column(String(200))
    posizione = Column(String(200))
    settori = Column(String(200))  # elenco semplice separato da virgole
    piante = Column(String(200))
    prospetti = Column(String(200))
    sezioni = Column(String(200))

    # Definizione, criteri, formazione
    definizione = Column(Text)             # Definizione [US]
    criteri_distinzione = Column(Text)     # Criteri di distinzione [US]
    modo_formazione = Column(Text)         # Modo di formazione [US]

    # Componenti
    componenti_inorganici = Column(Text)   # [US]
    componenti_organici = Column(Text)     # [US]

    # Proprietà fisiche
    consistenza = Column(String(50))       # libero o enum se noto [US]
    colore = Column(String(50))            # Munsell o libero [US]
    misure = Column(String(100))           # lunghezza/larghezza/spessore [US]
    stato_conservazione = Column(Text)     # [US]

    # Sequenza fisica (relazioni Harris) come JSON list di codici US
    sequenza_fisica = Column(
        JSONType,
        default=lambda: {
            "uguale_a": [],
            "si_lega_a": [],
            "gli_si_appoggia": [],
            "si_appoggia_a": [],
            "coperto_da": [],
            "copre": [],
            "tagliato_da": [],
            "taglia": [],
            "riempito_da": [],
            "riempie": [],
        },
        nullable=False,
    )

    # Testi principali
    descrizione = Column(Text)             # [US]
    osservazioni = Column(Text)            # [US]
    interpretazione = Column(Text)         # [US]

    # Datazione
    datazione = Column(String(200))        # [US]
    periodo = Column(String(100))          # [US]
    fase = Column(String(100))             # [US]
    elementi_datanti = Column(Text)        # [US]

    # Reperti e campionature
    dati_quantitativi_reperti = Column(Text)  # [US]
    campionature = Column(
        JSONType, default=lambda: {"flottazione": False, "setacciatura": False}, nullable=False
    )  # [US]

    # Meta e responsabilità
    affidabilita_stratigrafica = Column(String(50))  # [US]
    responsabile_scientifico = Column(String(200))   # [US]
    data_rilevamento = Column(Date)                  # [US]
    responsabile_compilazione = Column(String(200))  # [US]
    data_rielaborazione = Column(Date)               # [US]
    responsabile_rielaborazione = Column(String(200))# [US]

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    site = relationship("ArchaeologicalSite", back_populates="unita_stratigrafiche")


class UnitaStratigraficaMuraria(Base):
    __tablename__ = "unita_stratigrafiche_murarie"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    site_id = Column(PG_UUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=False)

    # Intestazione e contesto
    usm_code = Column(String(16), nullable=False, index=True)  # es. USM001
    ente_responsabile = Column(String(200))
    anno = Column(Integer)
    ufficio_mic = Column(String(200))
    identificativo_rif = Column(String(200))
    localita = Column(String(200))
    area_struttura = Column(String(200))
    saggio = Column(String(100))
    ambiente_unita_funzione = Column(String(200))
    posizione = Column(String(200))
    settori = Column(String(200))
    piante = Column(String(200))
    prospetti = Column(String(200))
    sezioni = Column(String(200))

    # Misure e superficie
    misure = Column(String(100))                  # [USM]
    superficie_analizzata = Column(Numeric(10, 2))# [USM]

    # Definizione e tecnica
    definizione = Column(Text)                    # [USM]
    tecnica_costruttiva = Column(String(200))     # Paramento esterno/interno [USM]
    sezione_muraria_visibile = Column(Boolean)    # visibile/non visibile [USM]
    sezione_muraria_tipo = Column(String(200))    # tipo [USM]
    sezione_muraria_spessore = Column(String(50)) # spessore [USM]
    funzione_statica = Column(String(200))        # [USM]
    modulo = Column(String(200))                  # [USM]
    criteri_distinzione = Column(Text)            # [USM]
    provenienza_materiali = Column(Text)          # [USM]
    orientamento = Column(String(100))            # [USM]
    uso_primario = Column(String(200))            # [USM]
    riutilizzo = Column(String(200))              # [USM]

    # Stato di conservazione
    stato_conservazione = Column(Text)            # [USM]

    # Materiali, lavorazioni, consistenze
    materiali_laterizi = Column(JSONType, default=dict)  # {tipo:[...], consistenza:[...]} [USM]
    materiali_elementi_litici = Column(JSONType, default=dict)  # {litotipi:[...], lavorazione:[...]} [USM]
    materiali_altro = Column(Text)                     # [USM]
    legante = Column(JSONType, default=dict)              # {tipo, consistenza} [USM]
    legante_altro = Column(Text)                       # [USM]
    finiture_elementi_particolari = Column(Text)       # [USM]

    # Sequenza fisica
    sequenza_fisica = Column(
        JSONType,
        default=lambda: {
            "uguale_a": [],
            "si_lega_a": [],
            "gli_si_appoggia": [],
            "si_appoggia_a": [],
            "coperto_da": [],
            "copre": [],
            "tagliato_da": [],
            "taglia": [],
            "riempito_da": [],
            "riempie": [],
        },
        nullable=False,
    )

    # Testi principali
    descrizione = Column(Text)                   # [USM]
    osservazioni = Column(Text)                  # [USM]
    interpretazione = Column(Text)               # [USM]

    # Datazione e campionature
    datazione = Column(String(200))              # [USM]
    periodo = Column(String(100))                # [USM]
    fase = Column(String(100))                   # [USM]
    elementi_datanti = Column(Text)              # [USM]
    campionature = Column(
        JSONType, default=lambda: {
            "elementi_litici": False, "laterizi": False, "malta": False
        }, nullable=False
    )  # [USM]

    # Meta e responsabilità
    affidabilita_stratigrafica = Column(String(50))  # [USM]
    responsabile_scientifico = Column(String(200))   # [USM]
    data_rilevamento = Column(Date)                  # [USM]
    responsabile_compilazione = Column(String(200))  # [USM]
    data_rielaborazione = Column(Date)               # [USM]
    responsabile_rielaborazione = Column(String(200))# [USM]

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    site = relationship("ArchaeologicalSite", back_populates="unita_stratigrafiche_murarie")
