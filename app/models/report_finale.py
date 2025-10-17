# app/models/report_finale.py
"""
Modello per generazione automatica relazione finale di scavo
Include tutti i componenti richiesti dalle Soprintendenze italiane
Conforme a DM 154/2017 e linee guida regionali
"""

from datetime import date, datetime
from enum import Enum as PyEnum
from uuid import uuid4
from typing import List, Optional, Dict, Any

from sqlalchemy import Column, String, Text, Boolean, DateTime, Date, Integer, ForeignKey, JSON, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


# ===== ENUM PER REPORT =====
class TipoReport(str, PyEnum):
    """Tipologie di report archeologici"""
    RELAZIONE_PRELIMINARE = "relazione_preliminare"
    RELAZIONE_FINALE = "relazione_finale" 
    RELAZIONE_SCIENTIFICA = "relazione_scientifica"
    SCHEDA_INTERVENTO = "scheda_intervento"
    NOTA_CONSEGNA = "nota_consegna"


class StatoReport(str, PyEnum):
    """Stati del report"""
    BOZZA = "bozza"
    IN_REVISIONE = "in_revisione"
    COMPLETATO = "completato"
    CONSEGNATO = "consegnato"
    APPROVATO = "approvato"


class FormatoOutput(str, PyEnum):
    """Formati di output del report"""
    PDF = "pdf"
    DOCX = "docx"
    HTML = "html"
    LATEX = "latex"


# ===== MODELLI IMPORTATI DA CONFIGURATIONS.PY =====
# Per evitare duplicazioni, tutti i modelli di configurazione sono centralizzati in configurations.py

from app.models.configurations import (
    RelazioneFinaleScavo,  # noqa: F401
    ConfigurazioneExport,  # noqa: F401
    ElencoConsegna,        # noqa: F401
    TemplateRelazione,     # noqa: F401
)


# ===== AGGIORNAMENTI PER ARCHAEOLOGICALSITE =====
"""
AGGIUNGERE QUESTE RELAZIONI in app/models/sites.py nella classe ArchaeologicalSite:

# Relazioni con report finale
relazioni_finali = relationship("RelazioneFinaleScavo", back_populates="site", cascade="all, delete-orphan")
configurazioni_export = relationship("ConfigurazioneExport", back_populates="site", cascade="all, delete-orphan")
"""