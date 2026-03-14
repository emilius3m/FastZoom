# app/models/user_activity.py
"""
Modello UserActivity per tracciamento attività utente
RIPRISTINATO - era sparito nella riorganizzazione!
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any
import json

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base


class UserActivity(Base):
    """
    Tracciamento attività utente nel sistema archeologico
    RIPRISTINATO modello mancante dai file riorganizzati
    """
    __tablename__ = "user_activities"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # ===== IDENTIFICAZIONE ATTIVITÀ =====
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    activity_date = Column(DateTime, server_default=func.now(), nullable=False)
    activity_type = Column(String(200), nullable=False, index=True)
    activity_desc = Column(String(1024), nullable=True)
    
    # ===== CONTESTO ARCHEOLOGICO =====
    site_id = Column(String(36), ForeignKey('archaeological_sites.id'), nullable=True, index=True)
    photo_id = Column(String(36), nullable=True)  # Per tracking modifiche foto
    us_id = Column(String(36), nullable=True)     # Per tracking modifiche US
    usm_id = Column(String(36), nullable=True)    # Per tracking modifiche USM
    tomba_id = Column(String(36), nullable=True)  # Per tracking modifiche tombe
    reperto_id = Column(String(36), nullable=True)  # Per tracking modifiche reperti
    
    # ===== INFORMAZIONI TECNICHE =====
    ip_address = Column(String(45), nullable=True)        # IPv6 support
    user_agent = Column(Text, nullable=True)
    extra_data = Column(Text, nullable=True)              # JSON string - metadati aggiuntivi
    
    # ===== TIMESTAMP =====
    created_at = Column(DateTime, server_default=func.now())
    
    # ===== RELAZIONI =====
    user = relationship("User", back_populates="activities")
    site = relationship("ArchaeologicalSite")
    
    # ===== INDICI PER PERFORMANCE =====
    __table_args__ = (
        Index('idx_activity_user_date', 'user_id', 'activity_date'),
        Index('idx_activity_type', 'activity_type'),
        Index('idx_activity_site', 'site_id'),
        Index('idx_activity_date', 'activity_date'),
        Index('idx_activity_user_type', 'user_id', 'activity_type'),
    )
    
    def __repr__(self):
        return f"<UserActivity(type={self.activity_type}, user_id={self.user_id}, date={self.activity_date})>"
    
    def __str__(self):
        return f"{self.activity_type} - {self.activity_date}"
    
    # ===== METODI PER GESTIONE JSON =====
    
    def set_extra_data(self, data: Dict[str, Any]):
        """Imposta dati extra come JSON"""
        self.extra_data = json.dumps(data) if data else None
    
    def get_extra_data(self) -> Dict[str, Any]:
        """Recupera dati extra dal JSON"""
        if not self.extra_data:
            return {}
        try:
            return json.loads(self.extra_data)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    @property
    def extra_data_dict(self) -> Dict[str, Any]:
        """Property per accesso facile ai dati extra"""
        return self.get_extra_data()
    
    # ===== METODI STATICI PER LOGGING =====
    
    @classmethod
    async def log_activity(
        cls,
        db: AsyncSession,
        user_id: str,
        activity_type: str,
        description: Optional[str] = None,
        site_id: Optional[str] = None,
        photo_id: Optional[str] = None,
        us_id: Optional[str] = None,
        usm_id: Optional[str] = None,
        tomba_id: Optional[str] = None,
        reperto_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> 'UserActivity':
        """
        Crea e salva una nuova attività utente
        Metodo helper per logging centralizzato
        """
        activity = cls(
            user_id=str(user_id),
            activity_type=activity_type,
            activity_desc=description,
            site_id=str(site_id) if site_id else None,
            photo_id=str(photo_id) if photo_id else None,
            us_id=str(us_id) if us_id else None,
            usm_id=str(usm_id) if usm_id else None,
            tomba_id=str(tomba_id) if tomba_id else None,
            reperto_id=str(reperto_id) if reperto_id else None,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if extra_data:
            activity.set_extra_data(extra_data)
        
        db.add(activity)
        await db.commit()
        await db.refresh(activity)
        return activity
    
    @classmethod
    async def log_login(
        cls,
        db: AsyncSession,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True
    ) -> 'UserActivity':
        """Log tentativo di login"""
        activity_type = "user_login_success" if success else "user_login_failed"
        return await cls.log_activity(
            db=db,
            user_id=user_id,
            activity_type=activity_type,
            description=f"Login {'riuscito' if success else 'fallito'}",
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @classmethod
    async def log_logout(
        cls,
        db: AsyncSession,
        user_id: str,
        ip_address: Optional[str] = None
    ) -> 'UserActivity':
        """Log logout utente"""
        return await cls.log_activity(
            db=db,
            user_id=user_id,
            activity_type="user_logout",
            description="Logout utente",
            ip_address=ip_address
        )
    
    @classmethod
    async def log_us_action(
        cls,
        db: AsyncSession,
        user_id: str,
        action: str,  # 'create', 'update', 'delete', 'validate'
        us_id: str,
        site_id: str,
        us_code: str,
        description: Optional[str] = None
    ) -> 'UserActivity':
        """Log azione su US"""
        activity_type = f"us_{action}"
        default_desc = f"{action.title()} US {us_code}"
        
        return await cls.log_activity(
            db=db,
            user_id=user_id,
            activity_type=activity_type,
            description=description or default_desc,
            site_id=site_id,
            us_id=us_id,
            extra_data={'us_code': us_code, 'action': action}
        )
    
    @classmethod
    async def log_usm_action(
        cls,
        db: AsyncSession,
        user_id: str,
        action: str,
        usm_id: str,
        site_id: str,
        usm_code: str,
        description: Optional[str] = None
    ) -> 'UserActivity':
        """Log azione su USM"""
        activity_type = f"usm_{action}"
        default_desc = f"{action.title()} USM {usm_code}"
        
        return await cls.log_activity(
            db=db,
            user_id=user_id,
            activity_type=activity_type,
            description=description or default_desc,
            site_id=site_id,
            usm_id=usm_id,
            extra_data={'usm_code': usm_code, 'action': action}
        )
    
    @classmethod
    async def log_photo_action(
        cls,
        db: AsyncSession,
        user_id: str,
        action: str,  # 'upload', 'update', 'delete', 'validate'
        photo_id: str,
        site_id: str,
        filename: str,
        description: Optional[str] = None
    ) -> 'UserActivity':
        """Log azione su foto"""
        activity_type = f"photo_{action}"
        default_desc = f"{action.title()} foto {filename}"
        
        return await cls.log_activity(
            db=db,
            user_id=user_id,
            activity_type=activity_type,
            description=description or default_desc,
            site_id=site_id,
            photo_id=photo_id,
            extra_data={'filename': filename, 'action': action}
        )
    
    @classmethod
    async def log_export_action(
        cls,
        db: AsyncSession,
        user_id: str,
        export_type: str,  # 'word', 'pdf', 'excel', 'zip'
        site_id: str,
        entity_count: int,
        description: Optional[str] = None
    ) -> 'UserActivity':
        """Log operazione di export"""
        activity_type = f"export_{export_type}"
        default_desc = f"Export {export_type.upper()}: {entity_count} elementi"
        
        return await cls.log_activity(
            db=db,
            user_id=user_id,
            activity_type=activity_type,
            description=description or default_desc,
            site_id=site_id,
            extra_data={
                'export_type': export_type,
                'entity_count': entity_count
            }
        )
    
    @classmethod
    async def log_tma_action(
        cls,
        db: AsyncSession,
        user_id: str,
        action: str,
        tomba_id: str,
        site_id: str,
        nct: str,
        description: Optional[str] = None
    ) -> 'UserActivity':
        """Log azione su Scheda TMA"""
        activity_type = f"tma_{action}"
        default_desc = f"{action.title()} TMA {nct}"
        
        return await cls.log_activity(
            db=db,
            user_id=user_id,
            activity_type=activity_type,
            description=description or default_desc,
            site_id=site_id,
            tomba_id=tomba_id,
            extra_data={'nct': nct, 'action': action}
        )
    
    # ===== METODI QUERY =====
    
    @classmethod
    async def get_user_activities(
        cls,
        db: AsyncSession,
        user_id: str,
        site_id: Optional[str] = None,
        activity_types: Optional[list] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list['UserActivity']:
        """Recupera attività utente con filtri"""
        from sqlalchemy import select
        
        query = select(cls).where(cls.user_id == user_id)
        
        if site_id:
            query = query.where(cls.site_id == site_id)
        
        if activity_types:
            query = query.where(cls.activity_type.in_(activity_types))
        
        query = query.order_by(cls.activity_date.desc()).limit(limit).offset(offset)
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    @classmethod
    async def get_site_activities(
        cls,
        db: AsyncSession,
        site_id: str,
        activity_types: Optional[list] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list['UserActivity']:
        """Recupera attività per sito"""
        from sqlalchemy import select
        
        query = select(cls).where(cls.site_id == site_id)
        
        if activity_types:
            query = query.where(cls.activity_type.in_(activity_types))
        
        query = query.order_by(cls.activity_date.desc()).limit(limit).offset(offset)
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    @classmethod
    async def get_activity_stats(
        cls,
        db: AsyncSession,
        user_id: Optional[str] = None,
        site_id: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, int]:
        """Statistiche attività per periodo"""
        from sqlalchemy import select, func
        from datetime import timedelta
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        query = select(
            cls.activity_type,
            func.count().label('count')
        ).where(
            cls.activity_date >= cutoff_date
        )
        
        if user_id:
            query = query.where(cls.user_id == user_id)
            
        if site_id:
            query = query.where(cls.site_id == site_id)
        
        query = query.group_by(cls.activity_type)
        
        result = await db.execute(query)
        return {row.activity_type: row.count for row in result}


# ===== COSTANTI TIPI ATTIVITÀ =====

ACTIVITY_TYPES = {
    # Login/Logout
    'user_login_success': 'Login riuscito',
    'user_login_failed': 'Login fallito', 
    'user_logout': 'Logout',
    
    # US/USM Actions
    'us_create': 'Creazione US',
    'us_update': 'Modifica US',
    'us_delete': 'Eliminazione US',
    'us_validate': 'Validazione US',
    'usm_create': 'Creazione USM',
    'usm_update': 'Modifica USM',
    'usm_delete': 'Eliminazione USM',
    'usm_validate': 'Validazione USM',
    
    # TMA Actions
    'tma_create': 'Creazione Tomba',
    'tma_update': 'Modifica Tomba',
    'tma_delete': 'Eliminazione Tomba',
    'tma_validate': 'Validazione Tomba',
    
    # Photo Actions
    'photo_upload': 'Caricamento foto',
    'photo_update': 'Modifica foto',
    'photo_delete': 'Eliminazione foto',
    'photo_validate': 'Validazione foto',
    
    # Export Actions
    'export_word': 'Export Word',
    'export_pdf': 'Export PDF',
    'export_excel': 'Export Excel',
    'export_zip': 'Export ZIP',
    
    # Site Actions
    'site_access': 'Accesso sito',
    'site_switch': 'Cambio sito',
    
    # Admin Actions
    'user_create': 'Creazione utente',
    'user_update': 'Modifica utente',
    'permission_grant': 'Assegnazione permessi',
    'permission_revoke': 'Revoca permessi',
}

def get_activity_display_name(activity_type: str) -> str:
    """Restituisce nome visualizzabile per tipo attività"""
    return ACTIVITY_TYPES.get(activity_type, activity_type.replace('_', ' ').title())