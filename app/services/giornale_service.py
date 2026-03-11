from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import date, time
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.repositories.giornale_repository import GiornaleRepository
from app.models.giornale_cantiere import GiornaleCantiere

class GiornaleService:
    def __init__(self, db_session: AsyncSession):
        self.repository = GiornaleRepository(db_session)
        self.db = db_session

    async def _format_giornale(self, g: GiornaleCantiere) -> Dict[str, Any]:
        """Helper to format giornale for API response"""
        # Recupera info cantiere
        cantiere_info = None
        if g.cantiere_id:
            cantiere = await self.repository.get_cantiere_info(g.cantiere_id)
            if cantiere:
                cantiere_info = {
                    "id": str(cantiere.id),
                    "nome": cantiere.nome,
                    "codice": cantiere.codice,
                    "committente": cantiere.committente,
                    "impresa_esecutrice": cantiere.impresa_esecutrice,
                    "direttore_lavori": cantiere.direttore_lavori,
                    "responsabile_procedimento": cantiere.responsabile_procedimento,
                    "oggetto_appalto": cantiere.oggetto_appalto,
                    "codice_cup": cantiere.codice_cup,
                    "codice_cig": cantiere.codice_cig,
                    "importo_lavori": float(cantiere.importo_lavori) if cantiere.importo_lavori else None
                }

        # Recupera operatori con ore
        enhanced_operators = await self.repository.get_enhanced_operators(g.id, g.operatori or [])

        # Format response dict
        return {
            "id": str(g.id),
            "data": g.data.isoformat() if g.data else None,
            "ora_inizio": g.ora_inizio.strftime("%H:%M") if g.ora_inizio else None,
            "ora_fine": g.ora_fine.strftime("%H:%M") if g.ora_fine else None,
            "responsabile_scavo": g.responsabile_nome or (g.responsabile.email if g.responsabile else None),
            "descrizione_lavori": g.descrizione_lavori,
            "condizioni_meteo": g.condizioni_meteo,
            "validato": bool(g.validato),
            "stato": "validato" if g.validato else "in_attesa",
            "us_elaborate": g.get_us_list() if hasattr(g, "get_us_list") else [],
            "us_elaborate_input": g.us_elaborate if g.us_elaborate else "",
            "usm_elaborate": g.get_usm_list() if hasattr(g, "get_usm_list") else [],
            "usr_elaborate": g.usr_elaborate.split(",") if g.usr_elaborate else [],
            "cantiere_id": str(g.cantiere_id) if g.cantiere_id else None,
            "cantiere": cantiere_info,
            "operatori_presenti": enhanced_operators,
            "note_generali": g.note_generali,
            "problematiche": g.problematiche,
            "compilatore": g.compilatore or g.responsabile_nome,
            "area_intervento": g.area_intervento,
            "saggio": g.saggio,
            "obiettivi": g.obiettivi,
            "interpretazione": g.interpretazione,
            "campioni_prelevati": g.campioni_prelevati,
            "strutture": g.strutture,
            "temperatura": g.temperatura,
            "temperatura_min": g.temperatura_min,
            "temperatura_max": g.temperatura_max,
            "note_meteo": g.note_meteo,
            "modalita_lavorazioni": g.modalita_lavorazioni,
            "attrezzatura_utilizzata": g.attrezzatura_utilizzata,
            "apparecchiature_input": g.attrezzatura_utilizzata,
            "mezzi_utilizzati": g.mezzi_utilizzati,
            "materiali_rinvenuti": g.materiali_rinvenuti,
            "documentazione_prodotta": g.documentazione_prodotta,
            "sopralluoghi": g.sopralluoghi,
            "disposizioni_rup": g.disposizioni_rup,
            "disposizioni_direttore": g.disposizioni_direttore,
            "contestazioni": g.contestazioni,
            "sospensioni": g.sospensioni,
            "incidenti": g.incidenti,
            "forniture": g.forniture,
            "data_validazione": g.data_validazione.isoformat() if g.data_validazione else None,
            "firma_digitale_hash": g.firma_digitale_hash,
            "allegati_paths": g.allegati_paths,
            "created_at": g.created_at.isoformat() if g.created_at else None,
            "updated_at": g.updated_at.isoformat() if g.updated_at else None,
            "version": g.version or 1,
            "foto": [
                {
                    "id": str(f.id),
                    "filename": f.filename,
                    "original_filename": f.original_filename,
                    "thumbnail_url": f"/api/v1/photos/{f.id}/thumbnail",
                    "full_url": f"/api/v1/photos/{f.id}/full",
                    "title": f.title,
                    "description": f.description,
                }
                for f in (g.foto or [])
            ],
        }

    async def list_giornali(
        self,
        site_id: UUID,
        skip: int = 0,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Lista giornali formattati per il frontend
        """
        giornali = await self.repository.get_site_giornali(site_id, skip, limit, filters)
        
        giornali_data = []
        for g in giornali:
            data = await self._format_giornale(g)
            giornali_data.append(data)
            
        return {
            "data": giornali_data,
            "count": len(giornali_data)
        }

    async def get_giornale(self, site_id: UUID, giornale_id: UUID) -> Dict[str, Any]:
        """Recupera singolo giornale formato"""
        # Use get_with_relations to eager load all relationships for PDF/sync contexts
        giornale = await self.repository.get_with_relations(giornale_id)
        if not giornale or str(giornale.site_id) != str(site_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Giornale non trovato"
            )
        return await self._format_giornale(giornale)

    async def create_giornale(
        self,
        site_id: UUID,
        giornale_data: Dict[str, Any],
        user_id: UUID
    ) -> GiornaleCantiere:
        """
        Crea nuovo giornale con validazioni business
        """
        # Validate cantiere ownership
        cantiere_id = giornale_data.get("cantiere_id")
        if cantiere_id:
            is_valid = await self.repository.verify_cantiere_site_access(cantiere_id, site_id)
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Il cantiere {cantiere_id} non appartiene al sito {site_id}"
                )

        # Validate and normalize selected mezzi
        mezzi_utilizzati_value = giornale_data.get("mezzi_utilizzati", "")
        mezzi_ids_raw = giornale_data.get("mezzi_ids", []) or []
        if mezzi_ids_raw:
            normalized_mezzi_ids: List[UUID] = []
            for mezzo_id in mezzi_ids_raw:
                try:
                    normalized_mezzi_ids.append(UUID(str(mezzo_id)))
                except Exception:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"ID mezzo non valido: {mezzo_id}"
                    )

            mezzi_records = await self.repository.get_mezzi_by_ids(site_id, normalized_mezzi_ids)
            mezzi_map = {str(m.id): m for m in mezzi_records}

            if len(mezzi_map) != len(set(str(mid) for mid in normalized_mezzi_ids)):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uno o più mezzi selezionati non sono assegnati al sito"
                )

            ordered_mezzi_labels: List[str] = []
            for mezzo_id in normalized_mezzi_ids:
                mezzo = mezzi_map.get(str(mezzo_id))
                if mezzo:
                    label = mezzo.nome
                    if mezzo.targa:
                        label = f"{label} ({mezzo.targa})"
                    ordered_mezzi_labels.append(label)

            mezzi_utilizzati_value = ", ".join(ordered_mezzi_labels)

        # Create giornale object
        nuovo_giornale = GiornaleCantiere(
            site_id=str(site_id),
            cantiere_id=str(UUID(cantiere_id)) if cantiere_id else None,
            data=date.fromisoformat(giornale_data.get("data")) if giornale_data.get("data") else date.today(),
            ora_inizio=time.fromisoformat(giornale_data["ora_inizio"]) if giornale_data.get("ora_inizio") else None,
            ora_fine=time.fromisoformat(giornale_data["ora_fine"]) if giornale_data.get("ora_fine") else None,
            descrizione_lavori=giornale_data.get("descrizione_lavori", ""),
            condizioni_meteo=giornale_data.get("condizioni_meteo"),
            note_generali=giornale_data.get("note_generali", ""),
            problematiche=giornale_data.get("problematiche", ""),
            responsabile_id=str(user_id),
            responsabile_nome=giornale_data.get("responsabile_nome", ""),
            compilatore=giornale_data.get("compilatore", ""),
            temperatura_min=giornale_data.get("temperatura_min"),
            temperatura_max=giornale_data.get("temperatura_max"),
            area_intervento=giornale_data.get("area_intervento"),
            saggio=giornale_data.get("saggio"),
            obiettivi=giornale_data.get("obiettivi"),
            interpretazione=giornale_data.get("interpretazione"),
            campioni_prelevati=giornale_data.get("campioni_prelevati"),
            strutture=giornale_data.get("strutture"),
            us_elaborate=giornale_data.get("us_elaborate_input", ""),
            attrezzatura_utilizzata=giornale_data.get("apparecchiature_input", ""),
            mezzi_utilizzati=mezzi_utilizzati_value,
            validato=False
        )
        
        self.db.add(nuovo_giornale)
        await self.db.flush() # Get ID

        # Validate and add operators
        operatori_data = giornale_data.get("operatori", [])
        if operatori_data:
            for operatore_info in operatori_data:
                op_id = operatore_info.get("id")
                ore_lavorate = operatore_info.get("ore_lavorate")
                note_presenza = operatore_info.get("note_presenza")
                
                if ore_lavorate is not None and (not isinstance(ore_lavorate, (int, float)) or ore_lavorate < 0):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Ore lavorate non valide per operatore {op_id}"
                    )
                
                is_valid_op = await self.repository.verify_operatore_site_access(op_id, site_id)
                if not is_valid_op:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"L'operatore {op_id} non è assegnato al sito {site_id}"
                    )
                
                await self.repository.add_operatore_association(
                    nuovo_giornale.id,
                    op_id,
                    float(ore_lavorate) if ore_lavorate is not None else None,
                    note_presenza
                )
        
        await self.db.commit()
        await self.db.refresh(nuovo_giornale)
        return nuovo_giornale

    async def update_giornale(
        self,
        site_id: UUID,
        giornale_id: UUID,
        giornale_data: Dict[str, Any]
    ) -> GiornaleCantiere:
        """
        Aggiorna giornale esistente
        """
        giornale = await self.repository.get(giornale_id)
        if not giornale or str(giornale.site_id) != str(site_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Giornale non trovato"
            )

        # Validate cantiere ownership if changed
        if "cantiere_id" in giornale_data and giornale_data["cantiere_id"]:
             is_valid = await self.repository.verify_cantiere_site_access(giornale_data["cantiere_id"], site_id)
             if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Il cantiere {giornale_data['cantiere_id']} non appartiene al sito {site_id}"
                )

        # Handle operators
        if "operatori" in giornale_data:
            operatori_data = giornale_data["operatori"]
            await self.repository.clear_operatore_associations(giornale.id)
            
            if operatori_data:
                for operatore_info in operatori_data:
                    op_id = operatore_info.get("id")
                    ore_lavorate = operatore_info.get("ore_lavorate")
                    note_presenza = operatore_info.get("note_presenza")
                    
                    if ore_lavorate is not None and (not isinstance(ore_lavorate, (int, float)) or ore_lavorate < 0):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Ore lavorate non valide per operatore {op_id}"
                        )
                    
                    is_valid_op = await self.repository.verify_operatore_site_access(op_id, site_id)
                    if not is_valid_op:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"L'operatore {op_id} non è assegnato al sito {site_id}"
                        )
                        
                    await self.repository.add_operatore_association(
                        giornale.id,
                        op_id,
                        float(ore_lavorate) if ore_lavorate is not None else None,
                        note_presenza
                    )

        # Update base fields
        update_dict = giornale_data.copy()

        # Mezzi selected from UI (ids -> readable label string)
        if "mezzi_ids" in update_dict:
            mezzi_ids_raw = update_dict.get("mezzi_ids") or []
            if mezzi_ids_raw:
                normalized_mezzi_ids: List[UUID] = []
                for mezzo_id in mezzi_ids_raw:
                    try:
                        normalized_mezzi_ids.append(UUID(str(mezzo_id)))
                    except Exception:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"ID mezzo non valido: {mezzo_id}"
                        )

                mezzi_records = await self.repository.get_mezzi_by_ids(site_id, normalized_mezzi_ids)
                mezzi_map = {str(m.id): m for m in mezzi_records}

                if len(mezzi_map) != len(set(str(mid) for mid in normalized_mezzi_ids)):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Uno o più mezzi selezionati non sono assegnati al sito"
                    )

                ordered_mezzi_labels: List[str] = []
                for mezzo_id in normalized_mezzi_ids:
                    mezzo = mezzi_map.get(str(mezzo_id))
                    if mezzo:
                        label = mezzo.nome
                        if mezzo.targa:
                            label = f"{label} ({mezzo.targa})"
                        ordered_mezzi_labels.append(label)

                update_dict["mezzi_utilizzati"] = ", ".join(ordered_mezzi_labels)
            else:
                update_dict["mezzi_utilizzati"] = ""
        
        # Helper per i campi data/time
        if "data" in update_dict:
             update_dict["data"] = date.fromisoformat(update_dict["data"])
        if "ora_inizio" in update_dict and update_dict["ora_inizio"]:
             update_dict["ora_inizio"] = time.fromisoformat(update_dict["ora_inizio"])
        if "ora_fine" in update_dict and update_dict["ora_fine"]:
             update_dict["ora_fine"] = time.fromisoformat(update_dict["ora_fine"])
             
        # Mapping input alias per attrezzatura
        if "apparecchiature_input" in update_dict:
            update_dict["attrezzatura_utilizzata"] = update_dict.pop("apparecchiature_input")
        if "us_elaborate_input" in update_dict:
            update_dict["us_elaborate"] = update_dict.pop("us_elaborate_input")

        # Convert list fields to comma-separated strings for SQLite
        for list_field in ["us_elaborate", "usm_elaborate", "usr_elaborate"]:
            if list_field in update_dict and isinstance(update_dict[list_field], list):
                update_dict[list_field] = ", ".join(update_dict[list_field]) if update_dict[list_field] else ""

        # Cleanup fields we processed manually
        for field in ["operatori", "mezzi_ids", "id", "site_id"]:
            update_dict.pop(field, None)

        await self.repository.update(giornale, update_dict)
        await self.db.commit()
        await self.db.refresh(giornale)
        return giornale

    async def validate_giornale(self, site_id: UUID, giornale_id: UUID) -> GiornaleCantiere:
        """Valida il giornale"""
        giornale = await self.repository.get(giornale_id)
        if not giornale or str(giornale.site_id) != str(site_id):
            raise HTTPException(status_code=404, detail="Giornale non trovato")
        
        if giornale.validato:
            raise HTTPException(status_code=400, detail="Giornale già validato")
            
        giornale.validato = True
        giornale.data_validazione = date.today()
        await self.db.commit()
        await self.db.refresh(giornale)
        return giornale

    async def delete_giornale(self, site_id: UUID, giornale_id: UUID):
        """Elimina il giornale"""
        giornale = await self.repository.get(giornale_id)
        if not giornale or str(giornale.site_id) != str(site_id):
            raise HTTPException(status_code=404, detail="Giornale non trovato")
            
        await self.repository.clear_operatore_associations(giornale.id)
        await self.repository.remove(giornale.id)
        return True

    async def link_photo(self, site_id: UUID, giornale_id: UUID, foto_id: UUID, didascalia: str = None, ordine: int = 0):
        """Link photo"""
        # Verify access
        giornale = await self.repository.get(giornale_id)
        if not giornale or str(giornale.site_id) != str(site_id):
            raise HTTPException(status_code=404, detail="Giornale non trovato")
            
        # Verify photo (generic repo check or direct query)
        # Using direct query for simplicity as we don't have PhotoService injected yet
        from app.models.documentation_and_field import Photo
        photo_res = await self.db.execute(select(Photo).where(and_(Photo.id == str(foto_id), Photo.site_id == str(site_id))))
        if not photo_res.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Foto non trovata")

        if await self.repository.check_photo_linked(giornale_id, foto_id):
             raise HTTPException(status_code=400, detail="Foto già collegata")
             
        await self.repository.link_photo(giornale_id, foto_id, didascalia, ordine)
        await self.db.commit()

    async def unlink_photo(self, site_id: UUID, giornale_id: UUID, foto_id: UUID):
        """Unlink photo"""
        giornale = await self.repository.get(giornale_id)
        if not giornale or str(giornale.site_id) != str(site_id):
            raise HTTPException(status_code=404, detail="Giornale non trovato")
            
        success = await self.repository.unlink_photo(giornale_id, foto_id)
        if not success:
            raise HTTPException(status_code=404, detail="Associazione non trovata")
        await self.db.commit()

    async def list_site_operators(self, site_id: UUID, skip: int = 0, limit: int = 20, filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """List operators with stats"""
        operators_with_stats, total = await self.repository.get_operators_with_stats(site_id, skip, limit, filters)
        
        operators_data = []
        for op, hours in operators_with_stats:
            giornali_count = await self.repository.count_operator_giornali(site_id, op.id)
            
            operators_data.append({
                "id": str(op.id),
                "nome": op.nome,
                "cognome": op.cognome,
                "codice_fiscale": op.codice_fiscale,
                "email": op.email,
                "telefono": op.telefono,
                "ruolo": op.ruolo,
                "specializzazione": op.specializzazione,
                "qualifica": op.qualifica,
                "qualifiche": op.qualifica.split(",") if op.qualifica else [],
                "stato": "attivo" if op.is_active else "inattivo",
                "ore_totali": float(hours) if hours else 0,
                "giornali_count": giornali_count,
                "site_id": str(op.site_id),
                "note": op.note,
                "assigned_to_site": True,
                "can_work_on_site": str(op.site_id) == str(site_id),
            })
            
        return {
            "data": operators_data,
            "count": total
        }

