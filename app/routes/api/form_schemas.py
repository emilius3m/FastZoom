"""
Form Schema API Router - Gestione API per form builder archeologico
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Dict, Any
from uuid import UUID
from datetime import datetime
import json

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.models.form_schemas import FormSchema
from app.models.sites import ArchaeologicalSite
from app.models.user_sites import UserSitePermission
from app.models.users import UserActivity

# Importa la funzione di verifica accesso dal sites_router
from app.routes.sites_router import get_site_access

form_schemas_router = APIRouter(prefix="/sites", tags=["form-schemas"])


@form_schemas_router.post("/{site_id}/api/form-schemas")
async def save_form_schema(
        site_id: UUID,
        schema_data: dict,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Salva un nuovo form schema o aggiorna uno esistente"""
    site, permission = site_access
    
    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    
    try:
        # Valida i dati del schema
        if not schema_data.get('name'):
            raise HTTPException(status_code=400, detail="Nome del form richiesto")
        
        if not schema_data.get('fields'):
            raise HTTPException(status_code=400, detail="Il form deve avere almeno un campo")
        
        # Verifica se è un aggiornamento (schema_id presente) o una nuova creazione
        schema_id = schema_data.get('id')
        
        if schema_id:
            # Aggiornamento schema esistente
            existing_schema_query = select(FormSchema).where(
                and_(FormSchema.id == UUID(schema_id), FormSchema.site_id == site_id)
            )
            existing_schema = await db.execute(existing_schema_query)
            existing_schema = existing_schema.scalar_one_or_none()
            
            if not existing_schema:
                raise HTTPException(status_code=404, detail="Schema non trovato")
            
            # Aggiorna i campi
            existing_schema.name = schema_data['name']
            existing_schema.description = schema_data.get('description', '')
            existing_schema.category = schema_data.get('category', 'artifact')
            existing_schema.schema_json = json.dumps(schema_data)
            existing_schema.updated_at = datetime.utcnow()
            
            await db.commit()
            await db.refresh(existing_schema)
            
            # Log attività
            await log_user_activity(
                db=db,
                user_id=current_user_id,
                site_id=site_id,
                activity_type="UPDATE",
                activity_desc=f"Aggiornato form schema: {existing_schema.name}",
                extra_data={
                    "schema_id": str(existing_schema.id),
                    "schema_name": existing_schema.name,
                    "category": existing_schema.category
                }
            )
            
            return JSONResponse({
                "message": "Schema aggiornato con successo",
                "schema_id": str(existing_schema.id),
                "schema": schema_data
            })
        else:
            # Nuovo schema
            new_schema = FormSchema(
                name=schema_data['name'],
                description=schema_data.get('description', ''),
                category=schema_data.get('category', 'artifact'),
                schema_json=json.dumps(schema_data),
                site_id=site_id,
                created_by=current_user_id
            )
            
            db.add(new_schema)
            await db.commit()
            await db.refresh(new_schema)
            
            # Log attività
            await log_user_activity(
                db=db,
                user_id=current_user_id,
                site_id=site_id,
                activity_type="CREATE",
                activity_desc=f"Creato form schema: {new_schema.name}",
                extra_data={
                    "schema_id": str(new_schema.id),
                    "schema_name": new_schema.name,
                    "category": new_schema.category
                }
            )
            
            return JSONResponse({
                "message": "Schema salvato con successo",
                "schema_id": str(new_schema.id),
                "schema": schema_data
            })
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving form schema: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nel salvataggio: {str(e)}")


@form_schemas_router.get("/{site_id}/api/form-schemas")
async def get_form_schemas(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Recupera tutti i form schema per il sito"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    try:
        # Query per ottenere tutti i form schema del sito
        schemas_query = select(FormSchema).where(
            and_(FormSchema.site_id == site_id, FormSchema.is_active == True)
        ).order_by(FormSchema.created_at.desc())
        
        schemas = await db.execute(schemas_query)
        schemas = schemas.scalars().all()
        
        # Formatta i risultati
        result = []
        for schema in schemas:
            try:
                schema_json = json.loads(schema.schema_json)
                result.append({
                    "id": str(schema.id),
                    "name": schema.name,
                    "description": schema.description,
                    "category": schema.category,
                    "created_at": schema.created_at.isoformat(),
                    "updated_at": schema.updated_at.isoformat(),
                    "created_by": str(schema.created_by),
                    "schema": schema_json
                })
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in schema {schema.id}")
                continue
        
        return JSONResponse({
            "schemas": result,
            "total": len(result)
        })
        
    except Exception as e:
        logger.error(f"Error fetching form schemas: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nel recupero degli schema: {str(e)}")


@form_schemas_router.get("/{site_id}/api/form-schemas/{schema_id}")
async def get_form_schema(
        site_id: UUID,
        schema_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Recupera un singolo form schema"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    try:
        schema_query = select(FormSchema).where(
            and_(FormSchema.id == schema_id, FormSchema.site_id == site_id)
        )
        schema = await db.execute(schema_query)
        schema = schema.scalar_one_or_none()
        
        if not schema:
            raise HTTPException(status_code=404, detail="Schema non trovato")
        
        try:
            schema_json = json.loads(schema.schema_json)
            return JSONResponse({
                "id": str(schema.id),
                "name": schema.name,
                "description": schema.description,
                "category": schema.category,
                "created_at": schema.created_at.isoformat(),
                "updated_at": schema.updated_at.isoformat(),
                "created_by": str(schema.created_by),
                "schema": schema_json
            })
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="Schema corrotto nel database")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching form schema {schema_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nel recupero dello schema: {str(e)}")


@form_schemas_router.delete("/{site_id}/api/form-schemas/{schema_id}")
async def delete_form_schema(
        site_id: UUID,
        schema_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Elimina un form schema"""
    site, permission = site_access
    
    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    
    try:
        schema_query = select(FormSchema).where(
            and_(FormSchema.id == schema_id, FormSchema.site_id == site_id)
        )
        schema = await db.execute(schema_query)
        schema = schema.scalar_one_or_none()
        
        if not schema:
            raise HTTPException(status_code=404, detail="Schema non trovato")
        
        schema_name = schema.name
        
        # Elimina lo schema (soft delete)
        schema.is_active = False
        await db.commit()
        
        # Log attività
        await log_user_activity(
            db=db,
            user_id=current_user_id,
            site_id=site_id,
            activity_type="DELETE",
            activity_desc=f"Eliminato form schema: {schema_name}",
            extra_data={
                "schema_id": str(schema_id),
                "schema_name": schema_name
            }
        )
        
        return JSONResponse({
            "message": "Schema eliminato con successo",
            "schema_id": str(schema_id)
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting form schema {schema_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nell'eliminazione: {str(e)}")


async def log_user_activity(
        db: AsyncSession,
        user_id: UUID,
        site_id: UUID,
        activity_type: str,
        activity_desc: str,
        extra_data: Dict[str, Any] = None
):
    """Log attività utente per form schema"""
    try:
        # Serializza extra_data come JSON string
        extra_data_json = None
        if extra_data:
            extra_data_json = json.dumps(extra_data)

        # Crea attività
        activity = UserActivity(
            user_id=user_id,
            site_id=site_id,
            activity_type=activity_type,
            activity_desc=activity_desc,
            extra_data=extra_data_json
        )

        db.add(activity)
        await db.commit()
        logger.info(f"Form schema activity logged: {activity_type} by {user_id}")

    except Exception as e:
        logger.error(f"Error logging form schema activity: {e}")
        # Non bloccare l'operazione principale se il log fallisce
        await db.rollback()