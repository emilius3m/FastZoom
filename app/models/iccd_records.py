"""Modelli per Standard ICCD - Sistema Gerarchico Completo."""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Index, UniqueConstraint, Integer
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship, mapped_column, Mapped
from app.database.base import Base


class ICCDBaseRecord(Base):
    """Modello base per tutte le schede ICCD con supporto gerarchico."""
    
    __tablename__ = "iccd_base_records"
    
    # Chiave primaria
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Codice Univoco Nazionale ICCD
    nct_region: Mapped[str] = mapped_column(String(2), nullable=False, default='12')  # NCTR - Lazio
    nct_number: Mapped[str] = mapped_column(String(8), nullable=False)               # NCTN
    nct_suffix: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)      # NCTS
    
    # Metadati scheda
    schema_type: Mapped[str] = mapped_column(String(5), nullable=False)  # SI, CA, MA, SAS, RA, NU, TMA, AT
    schema_version: Mapped[str] = mapped_column(String(10), default='3.00')
    level: Mapped[str] = mapped_column(String(1), nullable=False, default='C')  # P, C, A
    
    # Dati JSON della scheda
    iccd_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    # Relazioni gerarchiche
    parent_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("iccd_base_records.id"), nullable=True)
    site_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id"))
    
    # Metadati gestione
    created_by: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, onupdate=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(20), default='draft')  # draft, validated, published
    
    # Relazioni
    parent = relationship("ICCDBaseRecord", remote_side=[id])
    children = relationship("ICCDBaseRecord", back_populates="parent")
    site = relationship("ArchaeologicalSite", back_populates="iccd_records")
    creator = relationship("User", foreign_keys=[created_by])
    
    __table_args__ = (
        Index('idx_nct_complete', 'nct_region', 'nct_number', 'nct_suffix'),
        Index('idx_schema_site', 'schema_type', 'site_id'),
        Index('idx_hierarchy', 'parent_id', 'schema_type'),
        UniqueConstraint('nct_region', 'nct_number', 'nct_suffix', name='uq_nct_complete')
    )


# Mantengo ICCDRecord per compatibilità con il codice esistente
class ICCDRecord(ICCDBaseRecord):
    """Alias per compatibilità con il sistema esistente."""
    
    __tablename__ = None  # Usa la stessa tabella di ICCDBaseRecord
    
    # Campi aggiuntivi per compatibilità
    @property
    def cataloging_institution(self) -> str:
        """Ente schedatore estratto dai dati ICCD."""
        return self.iccd_data.get('CD', {}).get('ESC', 'SSABAP-RM')
    
    @property
    def cataloger_name(self) -> Optional[str]:
        """Nome catalogatore estratto dai dati ICCD."""
        return self.iccd_data.get('CD', {}).get('RCG', {}).get('RCGR', None)
    
    @property
    def is_validated(self) -> bool:
        """Stato validazione."""
        return self.status in ['validated', 'published']
    
    @property
    def validation_date(self) -> Optional[datetime]:
        """Data validazione."""
        return self.updated_at if self.is_validated else None
    
    @property
    def validation_notes(self) -> Optional[str]:
        """Note validazione."""
        return self.iccd_data.get('CD', {}).get('RCG', {}).get('RCGN', None)
    
    @property
    def survey_date(self) -> Optional[datetime]:
        """Data rilevamento."""
        survey_str = self.iccd_data.get('CD', {}).get('RCG', {}).get('RCGD', None)
        if survey_str:
            try:
                return datetime.fromisoformat(survey_str)
            except:
                return None
        return None
    
    @property
    def creation_date(self) -> datetime:
        """Data creazione scheda."""
        return self.created_at
    
    @property
    def validated_by(self) -> Optional[UUID]:
        """ID validatore."""
        return self.created_by if self.is_validated else None
    
    validator = relationship("User", foreign_keys=[validated_by], viewonly=True)
    
    def __repr__(self):
        return f"<ICCDRecord(nct='{self.get_nct()}', type='{self.schema_type}', level='{self.level}')>"
    
    def get_nct(self) -> str:
        """Restituisce il codice NCT completo."""
        suffix = self.nct_suffix or ""
        return f"{self.nct_region}{self.nct_number}{suffix}"
    
    def get_object_name(self) -> str:
        """Estrae il nome dell'oggetto dai dati ICCD."""
        try:
            return self.iccd_data.get("OG", {}).get("OGT", {}).get("OGTD", "Oggetto sconosciuto")
        except (AttributeError, KeyError):
            return "Oggetto sconosciuto"
    
    def get_cultural_context(self) -> str:
        """Estrae l'ambito culturale dai dati ICCD."""
        try:
            return self.iccd_data.get("AU", {}).get("AUT", {}).get("AUTM", "Non specificato")
        except (AttributeError, KeyError):
            return "Non specificato"
    
    def get_chronology(self) -> str:
        """Estrae la cronologia dai dati ICCD."""
        try:
            dt_data = self.iccd_data.get("DT", {})
            if "DTS" in dt_data:
                dts = dt_data["DTS"]
                start = dts.get("DTSI", "")
                end = dts.get("DTSF", "")
                if start == end:
                    return start
                return f"{start} - {end}" if start and end else start or end
            return "Non specificato"
        except (AttributeError, KeyError):
            return "Non specificato"
    
    def get_conservation_status(self) -> str:
        """Estrae lo stato di conservazione dai dati ICCD."""
        try:
            return self.iccd_data.get("DA", {}).get("STC", {}).get("STCC", "Non specificato")
        except (AttributeError, KeyError):
            return "Non specificato"
    
    def get_material(self) -> str:
        """Estrae il materiale principale dai dati ICCD."""
        try:
            materials = self.iccd_data.get("MT", {}).get("MTC", {}).get("MTCM", [])
            if isinstance(materials, list) and materials:
                return ", ".join(materials)
            elif isinstance(materials, str):
                return materials
            return "Non specificato"
        except (AttributeError, KeyError):
            return "Non specificato"
    
    def get_location_name(self) -> str:
        """Estrae la denominazione del luogo dai dati ICCD."""
        try:
            return self.iccd_data.get("LC", {}).get("PVL", {}).get("PVLN", "Non specificato")
        except (AttributeError, KeyError):
            return "Non specificato"
    
    def is_complete_for_level(self) -> tuple[bool, list[str]]:
        """Verifica se la scheda è completa per il livello indicato."""
        required_sections = {
            'P': ['CD', 'OG', 'LC'],  # Precatalogazione
            'C': ['CD', 'OG', 'LC', 'DT', 'MT', 'DA'],  # Catalogazione
            'A': ['CD', 'OG', 'LC', 'DT', 'MT', 'DA', 'AU', 'NS', 'RS']  # Approfondimento
        }
        
        required = required_sections.get(self.level, [])
        missing = []
        
        for section in required:
            if section not in self.iccd_data or not self.iccd_data[section]:
                missing.append(section)
        
        return len(missing) == 0, missing
    
    def get_level_display(self) -> str:
        """Restituisce il nome completo del livello."""
        levels = {
            'P': 'Precatalogazione',
            'C': 'Catalogazione',
            'A': 'Approfondimento'
        }
        return levels.get(self.level, 'Sconosciuto')
    
    def get_status_display(self) -> str:
        """Restituisce il nome completo dello status."""
        statuses = {
            'draft': 'Bozza',
            'submitted': 'Inviata',
            'approved': 'Approvata',
            'published': 'Pubblicata'
        }
        return statuses.get(self.status, 'Sconosciuto')
    
    def to_dict(self) -> dict:
        """Conversione a dizionario per API."""
        is_complete, missing_sections = self.is_complete_for_level()
        
        return {
            "id": str(self.id),
            "nct": self.get_nct(),
            "nct_region": self.nct_region,
            "nct_number": self.nct_number,
            "nct_suffix": self.nct_suffix,
            "schema_type": self.schema_type,
            "level": self.level,
            "level_display": self.get_level_display(),
            "status": self.status,
            "status_display": self.get_status_display(),
            "cataloging_institution": self.cataloging_institution,
            "cataloger_name": self.cataloger_name,
            "is_validated": self.is_validated,
            "validation_date": self.validation_date.isoformat() if self.validation_date else None,
            "validation_notes": self.validation_notes,
            "survey_date": self.survey_date.isoformat() if self.survey_date else None,
            "site_id": str(self.site_id),
            "created_by": str(self.created_by),
            "validated_by": str(self.validated_by) if self.validated_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "iccd_data": self.iccd_data,
            # Dati estratti per visualizzazione rapida
            "object_name": self.get_object_name(),
            "cultural_context": self.get_cultural_context(),
            "chronology": self.get_chronology(),
            "conservation_status": self.get_conservation_status(),
            "material": self.get_material(),
            "location_name": self.get_location_name(),
            "is_complete": is_complete,
            "missing_sections": missing_sections
        }


class ICCDRelation(Base):
    """Modello per relazioni tra schede ICCD."""
    
    __tablename__ = "iccd_relations"
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    source_record_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("iccd_base_records.id"))
    target_record_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("iccd_base_records.id"))
    
    relation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Tipi: "contenuto_in", "composto_da", "relazionato_a", "derivato_da",
    #       "stesso_contesto", "stesso_corredo", "stessa_campagna"
    
    relation_level: Mapped[str] = mapped_column(String(1), default='1')  # 1=principale, 2=secondaria, 3=terziaria
    notes: Mapped[Optional[str]] = mapped_column(Text)
    
    created_by: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relazioni
    source_record = relationship("ICCDBaseRecord", foreign_keys=[source_record_id])
    target_record = relationship("ICCDBaseRecord", foreign_keys=[target_record_id])
    creator = relationship("User")


class ICCDAuthorityFile(Base):
    """Authority Files per campagne di scavo e altri riferimenti."""
    
    __tablename__ = "iccd_authority_files"
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    authority_type: Mapped[str] = mapped_column(String(10), nullable=False)  # DSC, RCG, BIB, AUT
    authority_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Dati specifici authority
    authority_data: Mapped[dict] = mapped_column(JSON)
    
    site_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id"))
    created_by: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relazioni
    site = relationship("ArchaeologicalSite")
    creator = relationship("User")


class ICCDSchemaTemplate(Base):
    """Template predefiniti per schemi ICCD standard."""
    
    __tablename__ = "iccd_schema_templates"
    
    # Chiave primaria
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Identificativo schema
    schema_type: Mapped[str] = mapped_column(String(5), nullable=False, unique=True, index=True)  # RA, CA, SI, etc.
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(10), default="4.00")  # Versione standard ICCD
    
    # Schema JSON completo
    json_schema: Mapped[dict] = mapped_column(JSON, nullable=False)
    ui_schema: Mapped[dict] = mapped_column(JSON, nullable=True)  # Configurazione UI per form
    
    # Metadati template
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # artifact, architecture, site, etc.
    icon: Mapped[str] = mapped_column(String(10), default="🏺")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    standard_compliant: Mapped[bool] = mapped_column(Boolean, default=True)  # Conforme agli standard ICCD
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<ICCDSchemaTemplate(type='{self.schema_type}', name='{self.name}')>"
    
    def to_dict(self) -> dict:
        """Conversione a dizionario per API."""
        return {
            "id": str(self.id),
            "schema_type": self.schema_type,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "category": self.category,
            "icon": self.icon,
            "is_active": self.is_active,
            "standard_compliant": self.standard_compliant,
            "json_schema": self.json_schema,
            "ui_schema": self.ui_schema,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class ICCDValidationRule(Base):
    """Regole di validazione specifiche per standard ICCD."""
    
    __tablename__ = "iccd_validation_rules"
    
    # Chiave primaria
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Tipologia regola
    schema_type: Mapped[str] = mapped_column(String(5), nullable=False, index=True)  # RA, CA, SI, etc.
    level: Mapped[str] = mapped_column(String(1), nullable=False, index=True)        # P, C, A
    field_path: Mapped[str] = mapped_column(String(255), nullable=False)             # Percorso campo (es: "CD.NCT.NCTR")
    
    # Configurazione validazione
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)  # required, pattern, enum, range, etc.
    rule_config: Mapped[dict] = mapped_column(JSON, nullable=False)     # Configurazione specifica della regola
    
    # Metadati
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Stato
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)  # Priorità di esecuzione (1=alta, 10=bassa)
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Indici per performance
    __table_args__ = (
        Index('idx_validation_schema_level', 'schema_type', 'level'),
        Index('idx_validation_active', 'is_active', 'priority'),
    )
    
    def __repr__(self):
        return f"<ICCDValidationRule(type='{self.schema_type}', field='{self.field_path}')>"
    
    def to_dict(self) -> dict:
        """Conversione a dizionario per API."""
        return {
            "id": str(self.id),
            "schema_type": self.schema_type,
            "level": self.level,
            "field_path": self.field_path,
            "rule_type": self.rule_type,
            "rule_config": self.rule_config,
            "name": self.name,
            "description": self.description,
            "error_message": self.error_message,
            "is_active": self.is_active,
            "priority": self.priority,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }