import os
import sys
import uuid
from datetime import datetime

import sqlalchemy
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import DateTime, Column, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.functions import func

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(BASE_DIR, ".env"))
sys.path.append(BASE_DIR)

# Base SQLAlchemy - UNICA DEFINIZIONE
Base = declarative_base()


# ===== MODELLI BASE E MIXIN =====

class BaseSQLModel(Base):
    """
    Abstract base class per tutti i modelli con campi comuni:
    - ID UUID primario
    - Timestamp created/updated automatici
    """
    __abstract__ = True

    # ID primario UUID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    # Timestamp automatici
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    def __repr__(self):
        return f"<{self.__class__.__name__}(id={self.id})>"


class TimestampMixin:
    """Mixin per aggiungere timestamp a modelli esistenti"""
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SiteMixin:
    """Mixin per modelli associati a un sito archeologico"""
    site_id = Column(UUID(as_uuid=True), nullable=False, index=True)


class UserMixin:
    """Mixin per modelli che richiedono tracciamento utente"""
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)


class SoftDeleteMixin:
    """Mixin per soft delete"""
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(UUID(as_uuid=True), nullable=True)


DATABASE_URL = os.environ["DATABASE_URL"]


engine = create_async_engine(DATABASE_URL, echo=False, future=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


def init_models():
    # Import esistenti


    from ..models import Role, User, UserActivity, UserSitePermission # noqa: F401

    # 🆕 NUOVI: Modelli archeologici
    from ..models.sites import ArchaeologicalSite # noqa: F401
    from ..models.geographic_maps import GeographicMap # noqa: F401
    from ..models import Photo # noqa: F401
    from ..models.iccd_records import ICCDRecord, ICCDBaseRecord, ICCDSchemaTemplate # noqa: F401
    from ..models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria, USFile # noqa: F401
    # Import giornale di cantiere (nota: file con trattini richiede importlib)
    import importlib
    giornale_module = importlib.import_module('app.models.giornale_cantiere')
    GiornaleCantiere = giornale_module.GiornaleCantiere  # noqa: F401
    OperatoreCantiere = giornale_module.OperatoreCantiere  # noqa: F401
    
    # Import documentazione grafica
    doc_grafica_module = importlib.import_module('app.models.documentazione_grafica')
    TavolaGrafica = doc_grafica_module.TavolaGrafica  # noqa: F401
    FotografiaArcheologica = doc_grafica_module.FotografiaArcheologica  # noqa: F401
    MatrixHarris = doc_grafica_module.MatrixHarris  # noqa: F401
    ElencoConsegna = doc_grafica_module.ElencoConsegna  # noqa: F401
    
    # Import archeologia avanzata
    archeologia_module = importlib.import_module('app.models.archeologia_avanzata')
    UnitaStratigrafica = archeologia_module.UnitaStratigraficaCompleta  # noqa: F401
    SchedaTomba = archeologia_module.SchedaTomba  # noqa: F401
    InventarioReperto = archeologia_module.InventarioReperto  # noqa: F401
    MaterialeArcheologico = archeologia_module.MaterialeArcheologico  # noqa: F401
    CampioneScientifico = archeologia_module.CampioneScientifico  # noqa: F401
    
    # Import report finale
    report_module = importlib.import_module('app.models.report_finale')
    RelazioneFinaleScavo = report_module.RelazioneFinaleScavo  # noqa: F401
    TemplateRelazione = report_module.TemplateRelazione  # noqa: F401
    ConfigurazioneExport = report_module.ConfigurazioneExport  # noqa: F401

# Base = declarative_base()


# Declaring the base class for all models
# class Base(DeclarativeBase):
#     pass
