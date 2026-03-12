import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.models.base import Base, SiteMixin, UserMixin, SoftDeleteMixin


class SchedaTMA(Base, SiteMixin, UserMixin, SoftDeleteMixin):
    """Scheda TMA ICCD 3.00 (root table)."""

    __tablename__ = "schede_tma"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id = Column(String(36), ForeignKey("archaeological_sites.id"), nullable=False, index=True)

    # CD - Codici
    tsk = Column(String(4), nullable=False, default="TMA")
    lir = Column(String(5), nullable=False, default="I")
    nctr = Column(String(2), nullable=False)
    nctn = Column(String(8), nullable=False)
    esc = Column(String(25), nullable=False)
    ecp = Column(String(25), nullable=False)

    # OG - Oggetto
    ogtd = Column(String(100), nullable=False)
    ogtm = Column(String(250), nullable=False)

    # LC - Localizzazione attuale
    pvcs = Column(String(50), nullable=False, default="ITALIA")
    pvcr = Column(String(25), nullable=False)
    pvcp = Column(String(3), nullable=False)
    pvcc = Column(String(50), nullable=False)

    # LDC - Collocazione specifica
    ldct = Column(String(100), nullable=True)
    ldcn = Column(String(250), nullable=True)
    ldcu = Column(String(250), nullable=True)
    ldcs = Column(String(500), nullable=True)

    # LA - Altre localizzazioni (JSON ripetitivo)
    altre_localizzazioni = Column(JSON, nullable=False, default=list)

    # RE/DSC - Dati di scavo
    scan = Column(String(200), nullable=True)
    dscf = Column(String(200), nullable=True)
    dsca = Column(String(200), nullable=True)
    dsct = Column(String(100), nullable=True)
    dscm = Column(String(100), nullable=True)
    dscd = Column(String(4), nullable=True)
    dscu = Column(String(50), nullable=True)
    dscn = Column(String(250), nullable=True)

    # DT
    dtzg = Column(String(50), nullable=False)

    # DA
    nsc = Column(Text, nullable=True)

    # TU
    cdgg = Column(String(120), nullable=False)

    # AD
    adsp = Column(Integer, nullable=False, default=2)
    adsm = Column(String(70), nullable=True)

    # CM
    cmpd = Column(String(4), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    site = relationship("ArchaeologicalSite", back_populates="tma_schede")

    materiali = relationship(
        "TMAMateriale",
        back_populates="scheda",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TMAMateriale.ordine",
    )
    fotografie = relationship(
        "TMAFotografia",
        back_populates="scheda",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TMAFotografia.ordine",
    )
    compilatori = relationship(
        "TMACompilatore",
        back_populates="scheda",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TMACompilatore.ordine",
    )
    funzionari = relationship(
        "TMAFunzionario",
        back_populates="scheda",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TMAFunzionario.ordine",
    )
    motivazioni_cronologia = relationship(
        "TMAMotivazioneCronologia",
        back_populates="scheda",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TMAMotivazioneCronologia.ordine",
    )

    __table_args__ = (
        UniqueConstraint("site_id", "nctr", "nctn", name="uq_schede_tma_site_nct"),
        Index("idx_schede_tma_site_nct", "site_id", "nctr", "nctn"),
        Index("idx_schede_tma_ogtd", "ogtd"),
        Index("idx_schede_tma_pvcc", "pvcc"),
    )

    @property
    def nct(self) -> str:
        return f"{self.nctr or ''}{self.nctn or ''}"


class TMAMateriale(Base):
    __tablename__ = "tma_materiali"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheda_id = Column(String(36), ForeignKey("schede_tma.id", ondelete="CASCADE"), nullable=False, index=True)
    ordine = Column(Integer, nullable=False, default=0)

    macc = Column(String(100), nullable=False)
    macl = Column(String(150), nullable=True)
    macd = Column(String(150), nullable=True)
    macp = Column(String(150), nullable=True)
    macq = Column(Integer, nullable=False)
    mas = Column(String(250), nullable=True)

    scheda = relationship("SchedaTMA", back_populates="materiali")


class TMAFotografia(Base):
    __tablename__ = "tma_fotografie"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheda_id = Column(String(36), ForeignKey("schede_tma.id", ondelete="CASCADE"), nullable=False, index=True)
    ordine = Column(Integer, nullable=False, default=0)

    ftax = Column(String(100), nullable=True)
    ftap = Column(String(100), nullable=True)
    ftan = Column(String(200), nullable=True)
    file_path = Column(String(500), nullable=True)

    scheda = relationship("SchedaTMA", back_populates="fotografie")


class TMACompilatore(Base):
    __tablename__ = "tma_compilatori"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheda_id = Column(String(36), ForeignKey("schede_tma.id", ondelete="CASCADE"), nullable=False, index=True)
    ordine = Column(Integer, nullable=False, default=0)
    nome = Column(String(70), nullable=False)

    scheda = relationship("SchedaTMA", back_populates="compilatori")


class TMAFunzionario(Base):
    __tablename__ = "tma_funzionari"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheda_id = Column(String(36), ForeignKey("schede_tma.id", ondelete="CASCADE"), nullable=False, index=True)
    ordine = Column(Integer, nullable=False, default=0)
    nome = Column(String(70), nullable=False)

    scheda = relationship("SchedaTMA", back_populates="funzionari")


class TMAMotivazioneCronologia(Base):
    __tablename__ = "tma_motivazioni_cronologia"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheda_id = Column(String(36), ForeignKey("schede_tma.id", ondelete="CASCADE"), nullable=False, index=True)
    ordine = Column(Integer, nullable=False, default=0)
    motivazione = Column(String(250), nullable=False)

    scheda = relationship("SchedaTMA", back_populates="motivazioni_cronologia")

