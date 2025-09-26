# app/models/users.py - VERSIONE CORRETTA SENZA ERRORI SQLALCHEMY

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import uuid4, UUID

from sqlalchemy import Column, String, DateTime, Boolean, Text, func, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.schema import ForeignKey
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from app.models.base import Base, BaseSQLModel


class User(Base):
    """
    Modello User personalizzato per sistema archeologico multi-sito
    SENZA dipendenza da fastapi-users - Sistema completo
    """
    
    __tablename__ = "users"
    
    # ===== CAMPI BASE UTENTE =====
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Autenticazione
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(1024), nullable=False)
    
    # Stati utente
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Informazioni base per display
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Timestamp - CORREZIONE: nomi standard per compatibilità
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now(),
        nullable=False
    )
    
    # Ultimo accesso per statistiche
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True
    )
    
    # ===== RELAZIONI SISTEMA ARCHEOLOGICO =====
    
    # Relazioni esistenti (mantieni quelle che ti servono)
    role_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roles.id"), nullable=True, default=None
    )
    
    role: Mapped[Optional["Role"]] = relationship(
        "Role", uselist=False, back_populates="users"
    )
    
    profile: Mapped[Optional["UserProfile"]] = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    
    # Attività utente
    activities: Mapped[List["UserActivity"]] = relationship(
        "UserActivity", back_populates="user", cascade="all, delete-orphan"
    )
    
    # 🏛️ NUOVE RELAZIONI SISTEMA ARCHEOLOGICO MULTI-SITO
    site_permissions: Mapped[List["UserSitePermission"]] = relationship(
        "UserSitePermission",
        foreign_keys="UserSitePermission.user_id",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    # Permessi assegnati da questo utente (se è admin)
    granted_permissions: Mapped[List["UserSitePermission"]] = relationship(
        "UserSitePermission",
        foreign_keys="UserSitePermission.assigned_by",
        back_populates="assigned_by_user"
    )
    
    # Indici per performance
    __table_args__ = (
        Index("idx_user_email", "email"),
        Index("idx_user_active", "is_active"),
        Index("idx_user_superuser", "is_superuser"),
        Index("idx_user_verified", "is_verified"),
        Index("idx_user_created", "created_at"),
        Index("idx_user_last_login", "last_login"),
    )
    
    def __repr__(self):
        return f"User(id={self.id!r}, email={self.email!r})"
    
    def __str__(self):
        return self.email
    
    # ===== PROPERTIES PER DISPLAY =====
    
    @property
    def display_name(self) -> str:
        """Nome da mostrare nell'interfaccia"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.profile and self.profile.first_name and self.profile.last_name:
            return self.profile.get_full_name()
        else:
            return self.email.split('@')[0].title()
    
    @property
    def full_name(self) -> str:
        """Nome completo dell'utente"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        elif self.profile:
            return self.profile.get_full_name()
        return self.email
    
    @property
    def initials(self) -> str:
        """Iniziali per avatar"""
        if self.first_name and self.last_name:
            return f"{self.first_name[0]}{self.last_name[0]}".upper()
        elif self.profile and self.profile.first_name and self.profile.last_name:
            return f"{self.profile.first_name[0]}{self.profile.last_name[0]}".upper()
        else:
            return self.email[0].upper()
    
    # ===== METODI SISTEMA ARCHEOLOGICO MULTI-SITO =====
    
    def get_active_site_permissions(self) -> List["UserSitePermission"]:
        """Restituisce solo i permessi attivi e non scaduti"""
        return [perm for perm in self.site_permissions if perm.is_valid]
    
    def can_access_site(self, site_id: UUID) -> bool:
        """Controlla se l'utente può accedere ad un sito specifico"""
        if self.is_superuser:
            return True
        
        for perm in self.get_active_site_permissions():
            if perm.site_id == site_id:
                return True
        
        return False
    
    def get_permission_for_site(self, site_id: UUID) -> Optional["UserSitePermission"]:
        """Restituisce il permesso per un sito specifico"""
        for perm in self.get_active_site_permissions():
            if perm.site_id == site_id:
                return perm
        return None
    
    def can_read_site(self, site_id: UUID) -> bool:
        """Controlla se può leggere contenuti del sito"""
        if self.is_superuser:
            return True
        
        perm = self.get_permission_for_site(site_id)
        return perm and perm.can_read()
    
    def can_write_site(self, site_id: UUID) -> bool:
        """Controlla se può modificare contenuti del sito"""
        if self.is_superuser:
            return True
        
        perm = self.get_permission_for_site(site_id)
        return perm and perm.can_write()
    
    def can_admin_site(self, site_id: UUID) -> bool:
        """Controlla se l'utente può amministrare un sito"""
        if self.is_superuser:
            return True
        
        perm = self.get_permission_for_site(site_id)
        return perm and perm.can_admin()
    
    def get_accessible_sites(self) -> List["ArchaeologicalSite"]:
        """Restituisce lista dei siti accessibili"""
        return [perm.site for perm in self.get_active_site_permissions() if perm.site]
    
    def has_regional_admin_access(self) -> bool:
        """Controlla se ha accesso regionale admin"""
        if self.is_superuser:
            return True
        
        from app.models.user_sites import PermissionLevel
        
        for perm in self.get_active_site_permissions():
            if perm.permission_level == PermissionLevel.REGIONAL_ADMIN:
                return True
        
        return False
    
    def get_sites_count(self) -> int:
        """Numero di siti accessibili"""
        return len(self.get_active_site_permissions())
    
    def requires_site_selection(self) -> bool:
        """Determina se l'utente deve selezionare un sito al login"""
        if self.is_superuser:
            return False
        
        active_permissions = self.get_active_site_permissions()
        return len(active_permissions) > 1
    
    def get_default_site(self) -> Optional["ArchaeologicalSite"]:
        """Restituisce il sito predefinito per utenti single-site"""
        active_permissions = self.get_active_site_permissions()
        
        if len(active_permissions) == 1:
            return active_permissions[0].site
        
        return None
    
    # ===== METODI ASYNC PER DATABASE =====
    
    async def get_accessible_sites_async(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """Restituisce lista dei siti accessibili con dettagli (versione async)"""
        from app.models.sites import ArchaeologicalSite
        from app.models.user_sites import UserSitePermission
        
        query = (
            select(UserSitePermission, ArchaeologicalSite)
            .join(ArchaeologicalSite, UserSitePermission.site_id == ArchaeologicalSite.id)
            .where(
                and_(
                    UserSitePermission.user_id == self.id,
                    UserSitePermission.is_active == True,
                    or_(
                        UserSitePermission.expires_at.is_(None),
                        UserSitePermission.expires_at > func.now()
                    )
                )
            )
            .order_by(ArchaeologicalSite.name)
        )
        
        results = await db.execute(query)
        
        accessible_sites = []
        for permission, site in results:
            accessible_sites.append({
                "site_id": site.id,
                "site_code": site.code,
                "site_name": site.name,
                "site_description": site.description,
                "permission_level": permission.permission_level,
                "permission_display": permission.permission_display_name,
                "can_read": permission.can_read(),
                "can_write": permission.can_write(),
                "can_admin": permission.can_admin(),
                "expires_at": permission.expires_at,
                "granted_at": permission.created_at
            })
        
        return accessible_sites
    
    async def update_last_login(self, db: AsyncSession):
        """Aggiorna timestamp ultimo accesso"""
        self.last_login = datetime.now(timezone.utc)
        await db.commit()


class Role(BaseSQLModel):
    """
    Ruoli utente per sistema archeologico
    """
    
    __tablename__ = "roles"
    
    role_name: Mapped[str] = mapped_column(
        String(length=200), nullable=False, unique=True
    )
    
    role_desc: Mapped[Optional[str]] = mapped_column(String(length=1024), nullable=True)
    
    # Permessi globali del ruolo
    can_create_sites: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_users: Mapped[bool] = mapped_column(Boolean, default=False)
    can_export_data: Mapped[bool] = mapped_column(Boolean, default=True)
    can_access_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relazioni
    users: Mapped[List["User"]] = relationship("User", back_populates="role")
    
    def __str__(self):
        return self.role_name


class UserActivity(BaseSQLModel):
    """
    Tracciamento attività utente nel sistema archeologico
    🔧 RISOLTO: Rimosso campo 'metadata' riservato in SQLAlchemy
    """
    
    __tablename__ = "user_activities"
    
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    
    activity_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    
    activity_type: Mapped[str] = mapped_column(String(length=200), nullable=False)
    activity_desc: Mapped[Optional[str]] = mapped_column(String(length=1024), nullable=True)
    
    # Contesto archeologico
    site_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=True
    )
    
    photo_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )  # Per tracking modifiche foto
    
    # Informazioni tecniche per audit
    ip_address: Mapped[Optional[str]] = mapped_column(String(length=45), nullable=True)  # IPv6 support
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 🔧 CORREZIONE: Rinominato da 'metadata' a 'extra_data' per evitare conflitto SQLAlchemy
    extra_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    
    # Relazioni
    user: Mapped["User"] = relationship("User", back_populates="activities")
    site: Mapped[Optional["ArchaeologicalSite"]] = relationship("ArchaeologicalSite")
    
    # Indici per performance
    __table_args__ = (
        Index("idx_activity_user_date", "user_id", "activity_date"),
        Index("idx_activity_type", "activity_type"),
        Index("idx_activity_site", "site_id"),
        Index("idx_activity_date", "activity_date"),
    )
    
    def __str__(self):
        return f"{self.activity_type} - {self.activity_date}"
    
    # 🔧 AGGIUNTO: Metodi per gestire i dati extra come JSON
    def set_extra_data(self, data: Dict[str, Any]):
        """Imposta dati extra come JSON"""
        import json
        self.extra_data = json.dumps(data) if data else None
    
    def get_extra_data(self) -> Dict[str, Any]:
        """Recupera dati extra dal JSON"""
        if not self.extra_data:
            return {}
        
        try:
            import json
            return json.loads(self.extra_data)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    @classmethod
    async def log_activity(
        cls,
        db: AsyncSession,
        user_id: UUID,
        activity_type: str,
        description: Optional[str] = None,
        site_id: Optional[UUID] = None,
        photo_id: Optional[UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> "UserActivity":
        """Crea e salva una nuova attività utente"""
        
        activity = cls(
            user_id=user_id,
            activity_type=activity_type,
            activity_desc=description,
            site_id=site_id,
            photo_id=photo_id,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if extra_data:
            activity.set_extra_data(extra_data)
        
        db.add(activity)
        await db.commit()
        await db.refresh(activity)

        return activity


class TokenBlacklist(BaseSQLModel):
    """
    Blacklist per token JWT invalidati
    Permette di invalidare token prima della loro scadenza naturale
    """

    __tablename__ = "token_blacklist"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Token identifier (JTI - JWT ID)
    token_jti: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # User che ha invalidato il token
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Timestamp invalidazione
    invalidated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Motivo invalidazione (opzionale)
    reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relazione con User
    user: Mapped["User"] = relationship("User")

    # Indici per performance
    __table_args__ = (
        Index("idx_token_blacklist_user", "user_id"),
        Index("idx_token_blacklist_jti", "token_jti"),
        Index("idx_token_blacklist_invalidated", "invalidated_at"),
    )

    def __str__(self):
        return f"TokenBlacklist(jti={self.token_jti[:8]}..., user={self.user_id})"

    @classmethod
    async def is_token_blacklisted(cls, db: AsyncSession, token_jti: str) -> bool:
        """Verifica se un token JTI è nella blacklist"""
        query = select(cls).where(cls.token_jti == token_jti)
        result = await db.execute(query)
        return result.scalar_one_or_none() is not None

    @classmethod
    async def blacklist_token(
        cls,
        db: AsyncSession,
        token_jti: str,
        user_id: UUID,
        reason: Optional[str] = None
    ) -> "TokenBlacklist":
        """Aggiunge un token alla blacklist"""
        blacklist_entry = cls(
            token_jti=token_jti,
            user_id=user_id,
            reason=reason
        )

        db.add(blacklist_entry)
        await db.commit()
        await db.refresh(blacklist_entry)

        return blacklist_entry

    @classmethod
    async def cleanup_expired_tokens(cls, db: AsyncSession, older_than_days: int = 30):
        """Rimuove token dalla blacklist più vecchi di N giorni"""
        from datetime import timedelta

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        query = cls.__table__.delete().where(
            cls.invalidated_at < cutoff_date
        )

        result = await db.execute(query)
        await db.commit()

        return result.rowcount
