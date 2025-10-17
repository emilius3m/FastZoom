# app/models/token_blacklist.py
"""
Modello TokenBlacklist per gestione token JWT invalidati
RIPRISTINATO - era sparito nella riorganizzazione!
Gestisce logout sicuro e invalidazione token prima della scadenza
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base


class TokenBlacklist(Base):
    """
    Blacklist per token JWT invalidati
    RIPRISTINATO modello mancante dai file riorganizzati
    Permette di invalidare token prima della loro scadenza naturale
    """
    __tablename__ = "token_blacklist"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # ===== TOKEN INFO =====
    token_jti = Column(String(255), unique=True, nullable=False, index=True)  # JWT ID
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    
    # ===== INVALIDATION INFO =====
    invalidated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reason = Column(String(100), nullable=True)  # logout, security, admin_revoke, etc.
    
    # ===== OPTIONAL METADATA =====
    ip_address = Column(String(45), nullable=True)   # IP da cui è stato invalidato
    user_agent = Column(String(500), nullable=True)  # User agent
    
    # ===== RELAZIONI =====
    user = relationship("User")
    
    # ===== INDICI PER PERFORMANCE =====
    __table_args__ = (
        Index('idx_token_blacklist_user', 'user_id'),
        Index('idx_token_blacklist_jti', 'token_jti'),
        Index('idx_token_blacklist_invalidated', 'invalidated_at'),
        Index('idx_token_blacklist_user_date', 'user_id', 'invalidated_at'),
    )
    
    def __repr__(self):
        return f"<TokenBlacklist(jti={self.token_jti[:8]}..., user={self.user_id})>"
    
    def __str__(self):
        return f"Token invalidato: {self.token_jti[:12]}... - {self.invalidated_at}"
    
    # ===== METODI STATICI PER GESTIONE BLACKLIST =====
    
    @classmethod
    async def is_token_blacklisted(cls, db: AsyncSession, token_jti: str) -> bool:
        """
        Verifica se un token JTI è nella blacklist
        Metodo principale per controllo autenticazione
        """
        from sqlalchemy import select
        
        query = select(cls).where(cls.token_jti == token_jti)
        result = await db.execute(query)
        return result.scalar_one_or_none() is not None
    
    @classmethod
    async def blacklist_token(
        cls, 
        db: AsyncSession,
        token_jti: str, 
        user_id: uuid.UUID,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> 'TokenBlacklist':
        """
        Aggiunge un token alla blacklist
        Usato durante logout o revoca token
        """
        blacklist_entry = cls(
            token_jti=token_jti,
            user_id=user_id,
            reason=reason or 'logout',
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        db.add(blacklist_entry)
        await db.commit()
        await db.refresh(blacklist_entry)
        return blacklist_entry
    
    @classmethod
    async def blacklist_user_tokens(
        cls, 
        db: AsyncSession,
        user_id: uuid.UUID, 
        token_jtis: list[str],
        reason: str = "user_logout_all"
    ) -> int:
        """
        Invalida multipli token di un utente
        Usato per "logout da tutti i dispositivi"
        """
        blacklist_entries = []
        for jti in token_jtis:
            entry = cls(
                token_jti=jti,
                user_id=user_id,
                reason=reason
            )
            blacklist_entries.append(entry)
        
        db.add_all(blacklist_entries)
        await db.commit()
        return len(blacklist_entries)
    
    @classmethod
    async def cleanup_expired_tokens(cls, db: AsyncSession, older_than_days: int = 30) -> int:
        """
        Rimuove token dalla blacklist più vecchi di N giorni
        Manutenzione periodica per evitare crescita infinita
        """
        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
        
        # Elimina record vecchi
        query = cls.__table__.delete().where(cls.invalidated_at < cutoff_date)
        result = await db.execute(query)
        await db.commit()
        
        return result.rowcount
    
    @classmethod 
    async def get_user_blacklisted_tokens(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 100
    ) -> list['TokenBlacklist']:
        """
        Recupera token blacklist per utente specifico
        Utile per dashboard sicurezza
        """
        from sqlalchemy import select
        
        query = select(cls).where(
            cls.user_id == user_id
        ).order_by(
            cls.invalidated_at.desc()
        ).limit(limit)
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    @classmethod
    async def get_blacklist_stats(cls, db: AsyncSession) -> dict[str, int]:
        """
        Statistiche blacklist per monitoring
        """
        from sqlalchemy import select, func
        from datetime import timedelta
        
        now = datetime.utcnow()
        
        # Conteggi per periodo
        queries = {
            'total': select(func.count()).select_from(cls),
            'last_24h': select(func.count()).select_from(cls).where(
                cls.invalidated_at >= now - timedelta(hours=24)
            ),
            'last_week': select(func.count()).select_from(cls).where(
                cls.invalidated_at >= now - timedelta(days=7)
            ),
            'last_month': select(func.count()).select_from(cls).where(
                cls.invalidated_at >= now - timedelta(days=30)
            )
        }
        
        stats = {}
        for key, query in queries.items():
            result = await db.execute(query)
            stats[key] = result.scalar()
        
        return stats
    
    @classmethod
    async def count_user_active_sessions(cls, db: AsyncSession, user_id: uuid.UUID) -> int:
        """
        Stima sessioni attive utente
        (token emessi ma non ancora blacklisted)
        Richiede integrazione con JWT service per essere preciso
        """
        from sqlalchemy import select, func
        
        # Conta token blacklisted dell'utente nelle ultime 24h
        # (approssimazione - i token reali richiederebbero un registro separato)
        last_24h = datetime.utcnow() - timedelta(hours=24)
        
        query = select(func.count()).select_from(cls).where(
            cls.user_id == user_id,
            cls.invalidated_at >= last_24h
        )
        
        result = await db.execute(query)
        recent_blacklisted = result.scalar()
        
        return max(0, recent_blacklisted)  # Stima conservativa
    
    # ===== METODI ISTANZA =====
    
    def is_recent(self, hours: int = 1) -> bool:
        """Controlla se l'invalidazione è recente"""
        if not self.invalidated_at:
            return False
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return self.invalidated_at >= cutoff
    
    @property
    def reason_display(self) -> str:
        """Nome visualizzabile per motivo invalidazione"""
        reason_names = {
            'logout': 'Logout utente',
            'user_logout_all': 'Logout da tutti i dispositivi',
            'security': 'Motivi di sicurezza', 
            'admin_revoke': 'Revocato da amministratore',
            'password_change': 'Cambio password',
            'account_suspended': 'Account sospeso',
            'expired': 'Token scaduto',
            'invalid': 'Token non valido'
        }
        return reason_names.get(self.reason, self.reason or 'Non specificato')
    
    def to_dict(self) -> dict:
        """Conversione a dizionario per API"""
        return {
            'id': str(self.id),
            'token_jti': self.token_jti[:12] + '...' if len(self.token_jti) > 12 else self.token_jti,
            'user_id': str(self.user_id),
            'invalidated_at': self.invalidated_at.isoformat() if self.invalidated_at else None,
            'reason': self.reason,
            'reason_display': self.reason_display,
            'ip_address': self.ip_address,
            'is_recent': self.is_recent()
        }


# ===== COSTANTI MOTIVI INVALIDAZIONE =====

BLACKLIST_REASONS = {
    'logout': 'Logout utente',
    'user_logout_all': 'Logout da tutti i dispositivi',
    'security': 'Motivi di sicurezza',
    'admin_revoke': 'Revocato da amministratore', 
    'password_change': 'Cambio password',
    'account_suspended': 'Account sospeso',
    'account_deleted': 'Account eliminato',
    'permission_revoke': 'Permessi revocati',
    'expired': 'Token scaduto',
    'invalid': 'Token non valido',
    'maintenance': 'Manutenzione sistema'
}


# ===== HELPER FUNCTIONS =====

async def invalidate_user_session(
    db: AsyncSession, 
    user_id: uuid.UUID, 
    token_jti: str,
    reason: str = 'logout',
    ip_address: Optional[str] = None
) -> bool:
    """
    Helper function per invalidare singola sessione utente
    """
    try:
        await TokenBlacklist.blacklist_token(
            db=db,
            token_jti=token_jti,
            user_id=user_id,
            reason=reason,
            ip_address=ip_address
        )
        return True
    except Exception:
        return False

async def invalidate_all_user_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    current_token_jti: Optional[str] = None,
    reason: str = 'user_logout_all'
) -> int:
    """
    Helper per invalidare tutte le sessioni utente
    Opzionalmente esclude token corrente
    """
    # Questo richiederebbe un registro di tutti i token attivi
    # Per ora implementazione semplificata
    # In produzione, integrare con JWT service/cache
    
    # Per implementazione completa, avresti bisogno di:
    # 1. Registro token attivi (Redis/database)
    # 2. Query tutti i token dell'utente non scaduti
    # 3. Blacklist tutti eccetto current_token_jti
    
    # Placeholder implementation
    tokens_to_blacklist = []  # Da implementare con token store
    
    if tokens_to_blacklist:
        return await TokenBlacklist.blacklist_user_tokens(
            db=db,
            user_id=user_id,
            token_jtis=tokens_to_blacklist,
            reason=reason
        )
    
    return 0

async def is_token_valid(db: AsyncSession, token_jti: str) -> bool:
    """
    Helper per controllo validità token
    Verifica che non sia blacklisted
    """
    is_blacklisted = await TokenBlacklist.is_token_blacklisted(db, token_jti)
    return not is_blacklisted

def get_blacklist_reason_choices() -> list[tuple[str, str]]:
    """Helper per form choices"""
    return [(key, value) for key, value in BLACKLIST_REASONS.items()]