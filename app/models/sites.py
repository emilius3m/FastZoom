from sqlalchemy import Column, String, Text, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4
from app.database.base import Base

class ArchaeologicalSite(Base):
    """Modello per siti archeologici"""
    __tablename__ = "archaeological_sites"
    
    # Chiave primaria UUID per sicurezza multi-tenant
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    
    # Informazioni base sito
    name = Column(String(255), nullable=False, unique=True, index=True)
    code = Column(String(50), nullable=False, unique=True)  # Codice sito (es. "PMP-001")
    location = Column(String(255), nullable=True)
    region = Column(String(100), nullable=True)
    province = Column(String(100), nullable=True)
    
    # Metadati archeologici
    description = Column(Text, nullable=True)
    historical_period = Column(String(200), nullable=True)  # Es. "Romano Imperiale"
    site_type = Column(String(100), nullable=True)  # Es. "Necropoli", "Abitato", etc.
    coordinates_lat = Column(String(20), nullable=True)  # GPS Latitudine
    coordinates_lng = Column(String(20), nullable=True)  # GPS Longitudine
    municipality = Column(String(100), nullable=True)  # Comune
    research_status = Column(String(50), nullable=True)  # Es. "In corso", "Completato", etc.
    
    # Stato e gestione
    is_active = Column(Boolean, default=True, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)  # Visibile al pubblico
    
    # Timestamp automatici
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 🔥 RELAZIONI - DECOMMENTATE E CORRETTE
    user_permissions = relationship("UserSitePermission", back_populates="site", cascade="all, delete-orphan")

    # Relazione con le foto del sito
    photos = relationship("Photo", back_populates="site", cascade="all, delete-orphan")
    
    # Relazione con i form schema del sito
    form_schemas = relationship("FormSchema", back_populates="site", cascade="all, delete-orphan")
    
    # Relazione con le piante archeologiche
    plans = relationship("ArchaeologicalPlan", back_populates="site", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ArchaeologicalSite(name='{self.name}', code='{self.code}')>"
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    # 🆕 METODI UTILITY
    def get_active_permissions(self):
        """Restituisce solo i permessi attivi per questo sito"""
        return [perm for perm in self.user_permissions if perm.is_valid]
    
    def get_users_with_access(self):
        """Restituisce lista degli utenti che hanno accesso a questo sito"""
        return [perm.user for perm in self.get_active_permissions()]
    
    def has_user_access(self, user_id: UUID) -> bool:
        """Controlla se un utente specifico ha accesso a questo sito"""
        for perm in self.get_active_permissions():
            if perm.user_id == user_id:
                return True
        return False
    
    def get_user_permission_level(self, user_id: UUID):
        """Restituisce il livello di permesso di un utente per questo sito"""
        for perm in self.get_active_permissions():
            if perm.user_id == user_id:
                return perm.permission_level
        return None
