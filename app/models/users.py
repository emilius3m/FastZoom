# app/models/users.py
"""
Modelli per gestione utenti, ruoli e permessi
Sistema multi-tenant con permessi per sito
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import List, Optional

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Table, Index, Integer
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base, TimestampMixin, SoftDeleteMixin


# Tabella associativa user-role many-to-many
user_roles_association = Table(
    'user_roles_associations',
    Base.metadata,
    Column('user_id', UUID(as_uuid=True), ForeignKey('users.id'), primary_key=True),
    Column('role_id', UUID(as_uuid=True), ForeignKey('roles.id'), primary_key=True),
    Column('assigned_at', DateTime, default=datetime.utcnow),
    Column('assigned_by', UUID(as_uuid=True), ForeignKey('users.id'))
)


class UserStatusEnum(str, PyEnum):
    """Stati utente"""
    ACTIVE = "active"
    INACTIVE = "inactive" 
    SUSPENDED = "suspended"
    PENDING = "pending"


class User(Base, SoftDeleteMixin):
    """Modello utente con autenticazione e profilo"""
    __tablename__ = "users"
    
    # Chiave primaria
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Credenziali
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    
    # Profilo personale
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    full_name = Column(String(200), nullable=True)  # Calcolato automaticamente
    
    # Dati professionali archeologici
    qualifica_professionale = Column(String(200), nullable=True)  # Archeologo, Dottore di Ricerca, etc.
    ente_appartenenza = Column(String(300), nullable=True)  # Università, Soprintendenza, etc.
    codice_archeologo = Column(String(50), nullable=True)   # Codice MiC/Albo se applicabile
    
    # Contatti
    phone = Column(String(20), nullable=True)
    bio = Column(Text, nullable=True)
    avatar_url = Column(String(500), nullable=True)
    
    # Status e sicurezza
    status = Column(String(20), default=UserStatusEnum.PENDING, nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)
    
    # Autenticazione
    email_verified_at = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    login_count = Column(Integer, default=0)
    
    # Preferenze utente
    preferences = Column(JSON, default=dict)  # Theme, lingua, etc.
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relazioni
    roles = relationship("Role", secondary=user_roles_association, back_populates="users")
    site_permissions = relationship("UserSitePermission", back_populates="user", cascade="all, delete-orphan")
    
    # Relazioni con contenuti creati
    created_sites = relationship("ArchaeologicalSite", foreign_keys="ArchaeologicalSite.created_by", back_populates="creator")
    uploaded_documents = relationship("Document", foreign_keys="Document.uploaded_by", back_populates="uploader")
    created_forms = relationship("FormSchema", foreign_keys="FormSchema.created_by", back_populates="creator")
    giornali_cantiere = relationship("GiornaleCantiere", back_populates="responsabile")
    
    def __repr__(self):
        return f"<User(email={self.email}, status={self.status})>"
    
    def __str__(self):
        return f"{self.full_name or f'{self.first_name} {self.last_name}'}"
    
    @property
    def display_name(self) -> str:
        """Nome visualizzato per UI"""
        if self.full_name:
            return self.full_name
        return f"{self.first_name} {self.last_name}"
    
    def has_role(self, role_name: str) -> bool:
        """Controlla se utente ha ruolo specifico"""
        return any(role.name == role_name for role in self.roles)
    
    def has_site_permission(self, site_id: uuid.UUID, permission: str) -> bool:
        """Controlla permesso su sito specifico"""
        return any(
            perm.site_id == site_id and permission in perm.permissions
            for perm in self.site_permissions
        )
    
    def get_site_permissions(self, site_id: uuid.UUID) -> List[str]:
        """Ottieni lista permessi per sito"""
        for perm in self.site_permissions:
            if perm.site_id == site_id:
                return perm.permissions
        return []
    
    def update_last_login(self):
        """Aggiorna timestamp ultimo login"""
        self.last_login_at = datetime.utcnow()
        self.login_count += 1


class Role(Base):
    """Modello ruoli sistema"""
    __tablename__ = "roles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Definizione ruolo
    name = Column(String(50), unique=True, nullable=False, index=True)  # admin, archaeologist, student, etc.
    display_name = Column(String(100), nullable=False)  # Nome leggibile
    description = Column(Text, nullable=True)
    
    # Configurazione
    is_system_role = Column(Boolean, default=False)  # Non eliminabile
    is_active = Column(Boolean, default=True)
    
    # Permessi globali di base (JSON array)
    base_permissions = Column(JSON, default=list)  # ['read_sites', 'create_us', etc.]
    
    # Metadati
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relazioni
    users = relationship("User", secondary=user_roles_association, back_populates="roles")
    
    def __repr__(self):
        return f"<Role(name={self.name})>"
    
    def __str__(self):
        return self.display_name


class UserSitePermission(Base):
    """Permessi utente per sito specifico (multi-tenant)"""
    __tablename__ = "user_site_permissions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Relazioni
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    site_id = Column(UUID(as_uuid=True), ForeignKey('archaeological_sites.id', ondelete='CASCADE'), nullable=False)
    
    # Permessi specifici per sito (JSON array)
    permissions = Column(JSON, default=list, nullable=False)  # ['read', 'write', 'admin', 'export', etc.]
    
    # Ruolo nel sito
    site_role = Column(String(50), nullable=True)  # 'director', 'supervisor', 'collaborator', 'observer'
    
    # Metadati
    granted_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    granted_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # Permessi temporanei
    
    is_active = Column(Boolean, default=True)
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relazioni
    user = relationship("User", back_populates="site_permissions")
    site = relationship("ArchaeologicalSite", back_populates="user_permissions")
    granter = relationship("User", foreign_keys=[granted_by])
    
    # Indici per performance
    __table_args__ = (
        Index('idx_user_site_perms', 'user_id', 'site_id'),
        Index('idx_site_perms_active', 'site_id', 'is_active'),
    )
    
    def __repr__(self):
        return f"<UserSitePermission(user_id={self.user_id}, site_id={self.site_id}, role={self.site_role})>"
    
    def has_permission(self, permission: str) -> bool:
        """Controlla se ha permesso specifico"""
        return self.is_active and (permission in self.permissions)
    
    def is_expired(self) -> bool:
        """Controlla se permesso è scaduto"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False
    
    def add_permission(self, permission: str):
        """Aggiunge permesso alla lista"""
        if permission not in self.permissions:
            perms = self.permissions.copy()
            perms.append(permission)
            self.permissions = perms
    
    def remove_permission(self, permission: str):
        """Rimuove permesso dalla lista"""
        if permission in self.permissions:
            perms = self.permissions.copy()
            perms.remove(permission)
            self.permissions = perms


# Definizioni permessi standard
SITE_PERMISSIONS = {
    'read': 'Visualizzazione dati',
    'write': 'Modifica dati',
    'delete': 'Eliminazione dati', 
    'export': 'Esportazione dati',
    'admin': 'Amministrazione sito',
    'upload': 'Caricamento file',
    'validate': 'Validazione schede',
    'publish': 'Pubblicazione'
}

SYSTEM_ROLES = {
    'superadmin': 'Amministratore Sistema',
    'admin': 'Amministratore',
    'archaeologist': 'Archeologo',
    'researcher': 'Ricercatore', 
    'student': 'Studente',
    'viewer': 'Visualizzatore'
}