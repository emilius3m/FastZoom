from typing import Annotated, AsyncGenerator
from fastapi import Depends
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import bcrypt

from app.database.base import async_session_maker, Base, engine
from app.models import User

def get_password_hash(password: str) -> str:
    """Hash password con bcrypt (senza dipendenza da fastapi-users)"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

async def create_db_and_tables():
    """
    Crea tabelle database e superuser iniziale
    SENZA dipendenza da fastapi-users
    """
    # IMPORTANTE: Inizializza tutti i modelli PRIMA di creare le tabelle
    from app.database.base import init_models
    init_models()
    logger.info("📦 Models initialized")
    
    # Crea tutte le tabelle
    async with engine.begin() as conn:
        logger.info("🗄️  Creating database tables...")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables created successfully")
    
    # Crea superuser predefinito se non esiste
    async with async_session_maker() as session:
        # Controlla se superuser esiste già
        select_stmt = select(User).where(User.email == "superuser@admin.com")
        query = await session.execute(select_stmt)
        existing_user = query.scalars().first()
        
        if not existing_user:
            # Crea nuovo superuser
            hashed_password = get_password_hash("password123")
            
            user = User(
                email="superuser@admin.com",
                username="superuser",  # Add required username field
                hashed_password=hashed_password,
                is_superuser=True,
                is_active=True,
                is_verified=True,  # Aggiungi questo campo se presente nel modello
                first_name="Super",  # Add required first_name
                last_name="User"     # Add required last_name
            )
            
            session.add(user)
            await session.commit()
            
            logger.info("👤 Superuser created successfully:")
            logger.info(f"   📧 Email: {user.email}")
            logger.info(f"   🔑 Password: password123")
            logger.info(f"   🔐 Is Superuser: {user.is_superuser}")
            
        else:
            logger.info("⚠️  Superuser already exists:")
            logger.info(f"   📧 Email: {existing_user.email}")
            logger.info(f"   🔑 Password: password123 (if unchanged)")

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency per ottenere sessione database asincrona"""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()

# 🔧 RIMUOVI QUESTA FUNZIONE - non serve più senza fastapi-users
# async def get_user_db(session: AsyncSession = Depends(get_async_session)):
#     yield SQLAlchemyUserDatabase(session, User)

# Type alias per dependency injection
CurrentAsyncSession = Annotated[AsyncSession, Depends(get_async_session)]

# ===== FUNZIONI UTILITY PER SISTEMA ARCHEOLOGICO =====

async def create_archaeological_superadmin():
    """
    Crea superadmin specifico per sistema archeologico
    """
    async with async_session_maker() as session:
        admin_email = "superadmin@archeologico.it"
        admin_password = "SuperAdmin2025!"
        
        # Controlla se esiste già
        select_stmt = select(User).where(User.email == admin_email)
        query = await session.execute(select_stmt)
        existing_admin = query.scalars().first()
        
        if not existing_admin:
            hashed_password = get_password_hash(admin_password)
            
            admin_user = User(
                email=admin_email,
                username="admin",  # Add required username field
                hashed_password=hashed_password,
                is_superuser=True,
                is_active=True,
                is_verified=True,
                first_name="Admin",  # Add required first_name
                last_name="User"     # Add required last_name
            )
            
            session.add(admin_user)
            await session.commit()
            
            logger.info("🏛️  Archaeological Superadmin created:")
            logger.info(f"   📧 Email: {admin_email}")
            logger.info(f"   🔑 Password: {admin_password}")
            
            return admin_user
        else:
            logger.info(f"🏛️  Archaeological Superadmin already exists: {admin_email}")
            return existing_admin

async def get_user_by_email(email: str, session: AsyncSession) -> User | None:
    """Utility per ottenere utente per email"""
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()

async def verify_user_password(user: User, password: str) -> bool:
    """Verifica password utente"""
    return bcrypt.checkpw(password.encode('utf-8'), user.hashed_password.encode('utf-8'))

async def count_users(session: AsyncSession) -> int:
    """Conta totale utenti nel sistema"""
    result = await session.execute(select(User))
    users = result.scalars().all()
    return len(users)

async def count_superusers(session: AsyncSession) -> int:
    """Conta superuser nel sistema"""
    result = await session.execute(select(User).where(User.is_superuser == True))
    superusers = result.scalars().all()
    return len(superusers)

# ===== INIZIALIZZAZIONE COMPLETA SISTEMA ARCHEOLOGICO =====

async def initialize_archaeological_system():
    """
    Inizializza completamente il sistema archeologico:
    1. Crea tabelle
    2. Crea superadmin
    3. Mostra statistiche
    """
    logger.info("🚀 Initializing Archaeological System...")
    logger.info("="*50)
    
    # 1. Crea tabelle
    await create_db_and_tables()
    
    # 2. Crea superadmin archeologico
    await create_archaeological_superadmin()
    
    # 3. Statistiche finali
    async with async_session_maker() as session:
        total_users = await count_users(session)
        total_superusers = await count_superusers(session)
        
        logger.info("📊 System Statistics:")
        logger.info(f"   👥 Total Users: {total_users}")
        logger.info(f"   🔐 Superusers: {total_superusers}")
    
    logger.info("✅ Archaeological System initialized successfully!")
    logger.info("="*50)

# ===== HEALTH CHECK FUNCTIONS =====

async def check_database_connection() -> bool:
    """Controlla se la connessione al database funziona"""
    try:
        async with async_session_maker() as session:
            await session.execute(select(1))
            return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False

async def get_database_stats() -> dict:
    """Ottieni statistiche database"""
    try:
        async with async_session_maker() as session:
            users_count = await count_users(session)
            superusers_count = await count_superusers(session)
            
            # Conta siti se esistono
            try:
                from app.models.sites import ArchaeologicalSite
                sites_result = await session.execute(select(ArchaeologicalSite))
                sites_count = len(sites_result.scalars().all())
            except:
                sites_count = 0
                
            # Conta permessi se esistono
            try:
                from app.models import UserSitePermission
                permissions_result = await session.execute(select(UserSitePermission))
                permissions_count = len(permissions_result.scalars().all())
            except:
                permissions_count = 0
            
            return {
                "users": users_count,
                "superusers": superusers_count,
                "sites": sites_count,
                "permissions": permissions_count,
                "database_healthy": True
            }
    except Exception as e:
        logger.error(f"❌ Database stats error: {e}")
        return {
            "database_healthy": False,
            "error": str(e)
        }
