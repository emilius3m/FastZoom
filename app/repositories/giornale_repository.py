from typing import List, Dict, Any, Optional, Tuple, Set
from uuid import UUID
from datetime import date
from sqlalchemy import select, and_, or_, desc, delete, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import BaseRepository
from app.models.giornale_cantiere import (
    GiornaleCantiere,
    OperatoreCantiere,
    MezzoCantiere,
    giornale_operatori_association,
    giornale_mezzi_association,
    giornale_foto_association,
)
from app.models.cantiere import Cantiere
from app.models.documentation_and_field import Photo

class GiornaleRepository(BaseRepository[GiornaleCantiere]):
    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session, GiornaleCantiere)

    async def get_with_relations(self, giornale_id: UUID) -> Optional[GiornaleCantiere]:
        """Get giornale with all relations eager loaded (for use in sync contexts like PDF generation)"""
        id_str = str(giornale_id) if isinstance(giornale_id, UUID) else giornale_id
        query = select(GiornaleCantiere).where(GiornaleCantiere.id == id_str).options(
            selectinload(GiornaleCantiere.site),
            selectinload(GiornaleCantiere.responsabile),
            selectinload(GiornaleCantiere.operatori),
            selectinload(GiornaleCantiere.mezzi),
            selectinload(GiornaleCantiere.foto),
            selectinload(GiornaleCantiere.cantiere),
        )
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def get_site_giornali(
        self,
        site_id: UUID,
        skip: int = 0,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[GiornaleCantiere]:
        """
        Recupera giornali del sito con filtri complessi
        """
        query = select(GiornaleCantiere).where(GiornaleCantiere.site_id == str(site_id))
        
        if filters:
            if filters.get("cantiere_id"):
                query = query.where(GiornaleCantiere.cantiere_id == str(filters["cantiere_id"]))
            
            if filters.get("data_da"):
                query = query.where(GiornaleCantiere.data >= filters["data_da"])
                
            if filters.get("data_a"):
                query = query.where(GiornaleCantiere.data <= filters["data_a"])
                
            if filters.get("responsabile"):
                query = query.where(
                    GiornaleCantiere.responsabile_nome.ilike(f"%{filters['responsabile']}%")
                )
                
            if filters.get("stato"):
                if filters["stato"] == "validato":
                    query = query.where(GiornaleCantiere.validato.is_(True))
                elif filters["stato"] == "in_attesa":
                    query = query.where(GiornaleCantiere.validato.is_(False))

            if filters.get("q"):
                search_term = f"%{filters['q']}%"
                query = query.where(
                    or_(
                        GiornaleCantiere.descrizione_lavori.ilike(search_term),
                        GiornaleCantiere.responsabile_nome.ilike(search_term),
                        GiornaleCantiere.compilatore.ilike(search_term),
                        GiornaleCantiere.note_generali.ilike(search_term)
                    )
                )

        # Eager loading
        query = query.options(
            selectinload(GiornaleCantiere.site),
            selectinload(GiornaleCantiere.responsabile),
            selectinload(GiornaleCantiere.operatori),
            selectinload(GiornaleCantiere.mezzi),
            # Carichiamo anche foto e cantiere se necessario, ma foto è già selectin nel model
        )
        
        query = query.order_by(
            desc(GiornaleCantiere.data), desc(GiornaleCantiere.created_at)
        )
        query = query.offset(skip).limit(limit)
        
        result = await self.db_session.execute(query)
        return result.scalars().all()

    async def get_enhanced_operators(self, giornale_id: UUID, operatori: List[OperatoreCantiere]) -> List[Dict[str, Any]]:
        """
        Recupera dati estesi degli operatori (ore, note) dalla tabella di associazione
        """
        enhanced_data = []
        for op in operatori:
            query = select(
                giornale_operatori_association.c.ore_lavorate,
                giornale_operatori_association.c.note_presenza
            ).where(
                and_(
                    giornale_operatori_association.c.giornale_id == str(giornale_id),
                    giornale_operatori_association.c.operatore_id == str(op.id)
                )
            )
            result = await self.db_session.execute(query)
            assoc_data = result.first()
            
            enhanced_data.append({
                "id": str(op.id),
                "nome": op.nome,
                "cognome": op.cognome,
                "ruolo": op.ruolo,
                "qualifica": op.qualifica,
                "ore_lavorate": float(assoc_data.ore_lavorate) if assoc_data and assoc_data.ore_lavorate is not None else None,
                "note_presenza": assoc_data.note_presenza if assoc_data else None,
            })
        return enhanced_data

    async def get_enhanced_mezzi(self, giornale_id: UUID, mezzi: List[MezzoCantiere]) -> List[Dict[str, Any]]:
        """
        Recupera dati estesi dei mezzi (ore, note) dalla tabella di associazione
        """
        enhanced_data = []
        for mezzo in mezzi:
            query = select(
                giornale_mezzi_association.c.ore_utilizzo,
                giornale_mezzi_association.c.note_utilizzo
            ).where(
                and_(
                    giornale_mezzi_association.c.giornale_id == str(giornale_id),
                    giornale_mezzi_association.c.mezzo_id == str(mezzo.id)
                )
            )
            result = await self.db_session.execute(query)
            assoc_data = result.first()

            enhanced_data.append({
                "id": str(mezzo.id),
                "nome": mezzo.nome,
                "tipo": mezzo.tipo,
                "marca": mezzo.marca,
                "modello": mezzo.modello,
                "targa": mezzo.targa,
                "matricola": mezzo.matricola,
                "ore_utilizzo": float(assoc_data.ore_utilizzo) if assoc_data and assoc_data.ore_utilizzo is not None else None,
                "note_utilizzo": assoc_data.note_utilizzo if assoc_data else None,
            })
        return enhanced_data

    async def verify_cantiere_site_access(self, cantiere_id: UUID, site_id: UUID) -> bool:
        """Verifica che il cantiere appartenga al sito"""
        query = select(Cantiere).where(
            and_(
                Cantiere.id == str(cantiere_id),
                Cantiere.site_id == str(site_id)
            )
        )
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none() is not None

    async def verify_operatore_site_access(self, operatore_id: UUID, site_id: UUID) -> bool:
        """Verifica che l'operatore sia assegnato al sito"""
        query = select(OperatoreCantiere).where(
            and_(
                OperatoreCantiere.id == str(operatore_id),
                OperatoreCantiere.site_id == str(site_id)
            )
        )
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none() is not None

    async def verify_mezzo_site_access(self, mezzo_id: UUID, site_id: UUID) -> bool:
        """Verifica che il mezzo sia assegnato al sito"""
        query = select(MezzoCantiere).where(
            and_(
                MezzoCantiere.id == str(mezzo_id),
                MezzoCantiere.site_id == str(site_id)
            )
        )
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none() is not None

    async def get_mezzi_by_ids(self, site_id: UUID, mezzi_ids: List[UUID]) -> List[MezzoCantiere]:
        """Recupera i mezzi di un sito filtrando per lista ID"""
        normalized_ids = [str(mezzo_id) for mezzo_id in (mezzi_ids or []) if mezzo_id]
        if not normalized_ids:
            return []

        compact_ids = [mid.replace("-", "").lower() for mid in normalized_ids]

        query = select(MezzoCantiere).where(
            and_(
                MezzoCantiere.site_id == str(site_id),
                or_(
                    MezzoCantiere.id.in_(normalized_ids),
                    func.replace(func.lower(MezzoCantiere.id), "-", "").in_(compact_ids),
                ),
            )
        )
        result = await self.db_session.execute(query)
        return result.scalars().all()

    async def add_operatore_association(self, giornale_id: UUID, operatore_id: UUID, ore: float = None, note: str = None):
        """Aggiunge associazione operatore-giornale"""
        stmt = giornale_operatori_association.insert().values(
            giornale_id=str(giornale_id),
            operatore_id=str(operatore_id),
            ore_lavorate=ore,
            note_presenza=note
        )
        await self.db_session.execute(stmt)

    async def clear_operatore_associations(self, giornale_id: UUID):
        """Rimuove tutte le associazioni operatori per un giornale"""
        stmt = giornale_operatori_association.delete().where(
            giornale_operatori_association.c.giornale_id == str(giornale_id)
        )
        await self.db_session.execute(stmt)

    async def add_mezzo_association(self, giornale_id: UUID, mezzo_id: UUID, ore: float = None, note: str = None):
        """Aggiunge associazione mezzo-giornale"""
        stmt = giornale_mezzi_association.insert().values(
            giornale_id=str(giornale_id),
            mezzo_id=str(mezzo_id),
            ore_utilizzo=ore,
            note_utilizzo=note
        )
        await self.db_session.execute(stmt)

    async def clear_mezzo_associations(self, giornale_id: UUID):
        """Rimuove tutte le associazioni mezzi per un giornale"""
        stmt = giornale_mezzi_association.delete().where(
            giornale_mezzi_association.c.giornale_id == str(giornale_id)
        )
        await self.db_session.execute(stmt)

    async def get_cantiere_info(self, cantiere_id: str) -> Optional[Cantiere]:
        """Recupera info cantiere"""
        query = select(Cantiere).where(Cantiere.id == cantiere_id)
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def validate_giornale(self, giornale_id: UUID) -> GiornaleCantiere:
        """Valida un giornale"""
        giornale = await self.get(giornale_id)
        if giornale:
            giornale.validato = True
            giornale.data_validazione = date.today() # or datetime.now() depending on model
        return giornale

    async def check_photo_linked(self, giornale_id: UUID, foto_id: UUID) -> bool:
         """Check if photo is already linked"""
         from app.models.giornale_cantiere import giornale_foto_association
         query = select(giornale_foto_association).where(
             and_(
                 giornale_foto_association.c.giornale_id == str(giornale_id),
                 giornale_foto_association.c.foto_id == str(foto_id)
             )
         )
         result = await self.db_session.execute(query)
         return result.first() is not None

    async def link_photo(self, giornale_id: UUID, foto_id: UUID, didascalia: str = None, ordine: int = 0):
        """Link a photo to the journal"""
        from app.models.giornale_cantiere import giornale_foto_association
        stmt = giornale_foto_association.insert().values(
            giornale_id=str(giornale_id),
            foto_id=str(foto_id),
            didascalia=didascalia,
            ordine=ordine
        )
        await self.db_session.execute(stmt)

    async def unlink_photo(self, giornale_id: UUID, foto_id: UUID) -> bool:
        """Unlink a photo"""
        stmt = giornale_foto_association.delete().where(
            and_(
                giornale_foto_association.c.giornale_id == str(giornale_id),
                giornale_foto_association.c.foto_id == str(foto_id)
            )
        )
        result = await self.db_session.execute(stmt)
        return result.rowcount > 0

    async def list_photo_archive_for_giornale(
        self,
        site_id: UUID,
        giornale_id: UUID,
        skip: int = 0,
        limit: int = 40,
        search: Optional[str] = None,
        link_state: str = "all",
        sort_by: str = "created_desc",
    ) -> Dict[str, Any]:
        """Elenco foto paginato per manager dedicato giornale."""
        linked_subquery = select(giornale_foto_association.c.foto_id).where(
            giornale_foto_association.c.giornale_id == str(giornale_id)
        )

        filters = [Photo.site_id == str(site_id)]

        if search:
            search_term = f"%{search.strip()}%"
            filters.append(
                or_(
                    Photo.filename.ilike(search_term),
                    Photo.original_filename.ilike(search_term),
                    Photo.title.ilike(search_term),
                    Photo.description.ilike(search_term),
                )
            )

        if link_state == "linked":
            filters.append(Photo.id.in_(linked_subquery))
        elif link_state == "unlinked":
            filters.append(~Photo.id.in_(linked_subquery))

        where_clause = and_(*filters)

        count_query = select(func.count(Photo.id)).where(where_clause)
        total_result = await self.db_session.execute(count_query)
        total = total_result.scalar() or 0

        order_mappings = {
            "created_desc": Photo.created_at.desc(),
            "created_asc": Photo.created_at.asc(),
            "filename_asc": Photo.filename.asc(),
            "filename_desc": Photo.filename.desc(),
        }
        order_by = order_mappings.get(sort_by, Photo.created_at.desc())

        items_query = (
            select(Photo)
            .where(where_clause)
            .order_by(order_by)
            .offset(skip)
            .limit(limit)
        )
        items_result = await self.db_session.execute(items_query)
        photos = items_result.scalars().all()

        linked_ids_result = await self.db_session.execute(
            select(giornale_foto_association.c.foto_id).where(
                giornale_foto_association.c.giornale_id == str(giornale_id)
            )
        )
        linked_ids = {str(row[0]) for row in linked_ids_result.fetchall()}

        data = []
        for photo in photos:
            photo_id = str(photo.id)
            data.append(
                {
                    "id": photo_id,
                    "filename": photo.filename,
                    "original_filename": photo.original_filename,
                    "title": photo.title,
                    "description": photo.description,
                    "created_at": photo.created_at.isoformat() if photo.created_at else None,
                    "thumbnail_url": f"/api/v1/photos/{photo_id}/thumbnail",
                    "full_url": f"/api/v1/photos/{photo_id}/full",
                    "linked": photo_id in linked_ids,
                }
            )

        return {
            "items": data,
            "total": total,
            "linked_count": len(linked_ids),
        }

    async def get_site_photo_ids(self, site_id: UUID, photo_ids: List[UUID]) -> Set[str]:
        """Restituisce gli ID foto validi appartenenti al sito."""
        normalized_ids = [str(photo_id) for photo_id in (photo_ids or []) if photo_id]
        if not normalized_ids:
            return set()

        result = await self.db_session.execute(
            select(Photo.id).where(
                and_(
                    Photo.site_id == str(site_id),
                    Photo.id.in_(normalized_ids),
                )
            )
        )
        return {str(row[0]) for row in result.fetchall()}

    async def bulk_link_photos(self, giornale_id: UUID, photo_ids: List[UUID]) -> Dict[str, int]:
        """Collega in blocco foto a un giornale saltando quelle già associate."""
        normalized_ids = [str(photo_id) for photo_id in (photo_ids or []) if photo_id]
        if not normalized_ids:
            return {"linked_count": 0, "already_linked": 0}

        existing_result = await self.db_session.execute(
            select(giornale_foto_association.c.foto_id).where(
                and_(
                    giornale_foto_association.c.giornale_id == str(giornale_id),
                    giornale_foto_association.c.foto_id.in_(normalized_ids),
                )
            )
        )
        existing_ids = {str(row[0]) for row in existing_result.fetchall()}

        to_insert = [
            {
                "giornale_id": str(giornale_id),
                "foto_id": photo_id,
                "ordine": 0,
            }
            for photo_id in normalized_ids
            if photo_id not in existing_ids
        ]

        if to_insert:
            await self.db_session.execute(giornale_foto_association.insert(), to_insert)

        return {
            "linked_count": len(to_insert),
            "already_linked": len(existing_ids),
        }

    async def bulk_unlink_photos(self, giornale_id: UUID, photo_ids: List[UUID]) -> int:
        """Scollega in blocco foto da un giornale."""
        normalized_ids = [str(photo_id) for photo_id in (photo_ids or []) if photo_id]
        if not normalized_ids:
            return 0

        result = await self.db_session.execute(
            giornale_foto_association.delete().where(
                and_(
                    giornale_foto_association.c.giornale_id == str(giornale_id),
                    giornale_foto_association.c.foto_id.in_(normalized_ids),
                )
            )
        )
        return result.rowcount or 0

    async def get_operators_with_stats(self, site_id: UUID, skip: int = 0, limit: int = 20, filters: Dict[str, Any] = None) -> Tuple[List[Any], int]:
        """
        Custom query logic for operators with journal counts
        """
        from sqlalchemy import func, or_
        
        # Custom query with hours calculation
        query = select(
            OperatoreCantiere,
            func.coalesce(func.sum(giornale_operatori_association.c.ore_lavorate), 0).label('total_hours')
        ).outerjoin(
            giornale_operatori_association,
            OperatoreCantiere.id == giornale_operatori_association.c.operatore_id
        ).where(
            OperatoreCantiere.site_id == str(site_id)
        )
        
        if filters:
             if filters.get("search"):
                search = f"%{filters['search']}%"
                query = query.where(
                    or_(
                        OperatoreCantiere.nome.ilike(search),
                        OperatoreCantiere.cognome.ilike(search),
                        OperatoreCantiere.codice_fiscale.ilike(search),
                    )
                )
             if filters.get("ruolo"):
                 query = query.where(OperatoreCantiere.ruolo == filters["ruolo"])
             if filters.get("specializzazione"):
                 query = query.where(OperatoreCantiere.specializzazione == filters["specializzazione"])
             if filters.get("stato"):
                 query = query.where(OperatoreCantiere.is_active == (filters["stato"] == "attivo"))

        # Group by operator to calculate sum correctly
        query = query.group_by(OperatoreCantiere.id)

        # Count total before pagination
        subquery = query.subquery()
        count_query = select(func.count()).select_from(subquery)
        count_result = await self.db_session.execute(count_query)
        total_count = count_result.scalar() or 0

        # Apply ordering and pagination
        query = query.order_by(OperatoreCantiere.cognome, OperatoreCantiere.nome)
        query = query.offset(skip).limit(limit)
        
        result = await self.db_session.execute(query)
        # Result returns tuples (OperatoreCantiere, total_hours)
        operators_with_stats = result.all()
        
        return operators_with_stats, total_count

    async def count_operator_giornali(self, site_id: UUID, operator_id: UUID) -> int:
        """Counts how many journals in the site the operator worked on"""
        from sqlalchemy import func
        query = select(func.count(GiornaleCantiere.id))\
                .join(giornale_operatori_association, GiornaleCantiere.id == giornale_operatori_association.c.giornale_id)\
                .where(
                    and_(
                        GiornaleCantiere.site_id == str(site_id),
                        giornale_operatori_association.c.operatore_id == str(operator_id)
                    )
                )
        result = await self.db_session.execute(query)
        return result.scalar() or 0

