import os
import sys

import sqlalchemy
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(BASE_DIR, ".env"))
sys.path.append(BASE_DIR)


class Base(DeclarativeBase):
    metadata: sqlalchemy.MetaData = sqlalchemy.MetaData()  # type: ignore


DATABASE_URL = os.environ["DATABASE_URL"]


engine = create_async_engine(DATABASE_URL, echo=False, future=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


def init_models():
    # Import esistenti


    from ..models.users import Role, User, UserActivity  # noqa: F401

    # 🆕 NUOVI: Modelli archeologici
    from ..models.sites import ArchaeologicalSite # noqa: F401
    from ..models.user_sites import UserSitePermission # noqa: F401
    from ..models.photos import Photo # noqa: F401
    from ..models.iccd_records import ICCDRecord, ICCDSchemaTemplate # noqa: F401
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
    UnitaStratigrafica = archeologia_module.UnitaStratigrafica  # noqa: F401
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
