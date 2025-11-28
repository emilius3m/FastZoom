#!/usr/bin/env python3
"""
Test per la soluzione di eliminazione dual-table per US files e Photo
Verifica che entrambi i tipi di file possano essere eliminati correttamente
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from loguru import logger
import sys
import os

# Aggiungi il path del progetto al PYTHONPATH
sys.path.insert(0, os.path.abspath('.'))

from app.services.us_file_service import USFileService


async def test_us_file_deletion():
    """Test eliminazione file US dalla tabella USFile"""
    print("🧪 Test eliminazione file US (tabella USFile)...")
    
    # Mock database session
    mock_db = AsyncMock()
    
    # Crea il servizio
    service = USFileService(mock_db)
    
    # Simula file US trovato
    mock_us_file = MagicMock()
    mock_us_file.id = "test-us-file-id"
    mock_us_file.filename = "test-us-file.pdf"
    mock_us_file.filepath = "bucket/test-file.pdf"
    mock_us_file.thumbnail_path = "bucket/test-thumb.jpg"
    
    # Mock del metodo _find_file_with_uuid_fallback per restituire il file
    with patch.object(service, '_find_file_with_uuid_fallback', return_value=mock_us_file):
        with patch.object(service, '_find_photo_with_uuid_fallback', return_value=None):
            with patch.object(service, '_delete_us_file_logic', return_value=True) as mock_delete_logic:
                
                # Esegui la cancellazione
                result = await service.delete_us_file(
                    us_id=uuid.uuid4(),
                    file_id=uuid.uuid4(),
                    user_id=uuid.uuid4()
                )
                
                # Verifica che il metodo sia stato chiamato
                assert result == True
                mock_delete_logic.assert_called_once()
                
                print("✅ Test eliminazione file US completato con successo")
                return True


async def test_photo_deletion():
    """Test eliminazione foto dalla tabella Photo"""
    print("🧪 Test eliminazione foto (tabella Photo)...")
    
    # Mock database session
    mock_db = AsyncMock()
    
    # Crea il servizio
    service = USFileService(mock_db)
    
    # Simula foto trovata
    mock_photo = MagicMock()
    mock_photo.id = "test-photo-id"
    mock_photo.filename = "test-photo.jpg"
    mock_photo.filepath = "bucket/test-photo.jpg"
    mock_photo.created_by = uuid.uuid4()
    
    # Mock del metodo _find_file_with_uuid_fallback per restituire None
    # e _find_photo_with_uuid_fallback per restituire la foto
    with patch.object(service, '_find_file_with_uuid_fallback', return_value=None):
        with patch.object(service, '_find_photo_with_uuid_fallback', return_value=mock_photo):
            with patch.object(service, '_delete_photo_logic', return_value=True) as mock_delete_logic:
                
                # Esegui la cancellazione
                result = await service.delete_us_file(
                    us_id=uuid.uuid4(),
                    file_id=uuid.uuid4(),
                    user_id=uuid.uuid4()
                )
                
                # Verifica che il metodo sia stato chiamato
                assert result == True
                mock_delete_logic.assert_called_once()
                
                print("✅ Test eliminazione foto completato con successo")
                return True


async def test_fallback_search():
    """Test ricerca con fallback per diversi formati UUID"""
    print("🧪 Test ricerca con fallback multi-livello...")
    
    # Mock database session
    mock_db = AsyncMock()
    
    # Crea il servizio
    service = USFileService(mock_db)
    
    # Test ID con diversi formati
    test_ids = [
        "550e8400-e29b-41d4-a716-446655440000",  # Standard UUID con trattini
        "550e8400e29b41d4a716446655440000",      # Hash esadecimale senza trattini
    ]
    
    for test_id in test_ids:
        # Test normalizzazione
        normalized = service._normalize_us_id(test_id)
        print(f"   Normalizzazione: {test_id} -> {normalized}")
        
        # Verifica che il risultato sia un UUID standard
        assert len(normalized) == 36
        assert normalized.count('-') == 4
    
    print("✅ Test fallback multi-livello completato con successo")
    return True


async def test_us_file_logic():
    """Test logica di eliminazione specifica per US file"""
    print("🧪 Test logica _delete_us_file_logic...")
    
    # Mock database session e storage
    mock_db = AsyncMock()
    mock_storage = AsyncMock()
    
    # Crea il servizio con storage mockato
    service = USFileService(mock_db)
    service.storage = mock_storage
    
    # Simula file US
    mock_us_file = MagicMock()
    mock_us_file.id = "test-us-file-id"
    mock_us_file.filename = "test-file.pdf"
    mock_us_file.filepath = "bucket/test-file.pdf"
    mock_us_file.thumbnail_path = "bucket/test-thumb.jpg"
    
    # Mock dei metodi helper
    with patch.object(service, '_check_file_has_us_associations', return_value=False):
        with patch.object(service, '_check_file_has_usm_associations', return_value=False):
            with patch.object(mock_db, 'execute', return_value=MagicMock(rowcount=1)):
                with patch.object(mock_db, 'delete', return_value=None):
                    with patch.object(mock_db, 'commit', return_value=None):
                        
                        # Esegui la logica di eliminazione
                        result = await service._delete_us_file_logic(
                            us_id=uuid.uuid4(),
                            us_file=mock_us_file,
                            user_id=uuid.uuid4()
                        )
                        
                        # Verifica che l'eliminazione sia andata a buon fine
                        assert result == True
                        
                        # Verifica che i metodi di storage siano stati chiamati
                        mock_storage.delete_file.assert_called()
                        
                        print("✅ Test logica _delete_us_file_logic completato con successo")
                        return True


async def test_photo_logic():
    """Test logica di eliminazione specifica per foto"""
    print("🧪 Test logica _delete_photo_logic...")
    
    # Mock database session e storage
    mock_db = AsyncMock()
    mock_storage = AsyncMock()
    
    # Crea il servizio con storage mockato
    service = USFileService(mock_db)
    service.storage = mock_storage
    
    # Simula foto
    mock_photo = MagicMock()
    mock_photo.id = "test-photo-id"
    mock_photo.filename = "test-photo.jpg"
    mock_photo.filepath = "bucket/test-photo.jpg"
    mock_photo.thumbnail_path = "bucket/test-thumb.jpg"
    mock_photo.created_by = uuid.uuid4()
    
    # Mock del PhotoService
    with patch('app.services.photo_service.PhotoService') as mock_photo_service_class:
        mock_photo_service = AsyncMock()
        mock_photo_service.delete_photo.return_value = True
        mock_photo_service_class.return_value = mock_photo_service
        
        # Esegui la logica di eliminazione
        result = await service._delete_photo_logic(mock_photo)
        
        # Verifica che il metodo PhotoService sia stato chiamato
        assert result == True
        mock_photo_service.delete_photo.assert_called_once_with(
            mock_photo.id, mock_photo.created_by
        )
        
        print("✅ Test logica _delete_photo_logic completato con successo")
        return True


async def run_all_tests():
    """Esegui tutti i test"""
    print("🚀 Inizio test soluzione eliminazione dual-table...\n")
    
    tests = [
        test_us_file_deletion,
        test_photo_deletion,
        test_fallback_search,
        test_us_file_logic,
        test_photo_logic
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            await test_func()
            passed += 1
        except Exception as e:
            print(f"❌ Test {test_func.__name__} fallito: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n📊 Risultati: {passed}/{total} test superati")
    
    if passed == total:
        print("✅ Tutti i test superati! La soluzione dual-table è funzionante.")
        return True
    else:
        print("❌ Alcuni test falliti. Controlla gli errori sopra.")
        return False


if __name__ == "__main__":
    # Esegui i test
    result = asyncio.run(run_all_tests())
    
    if result:
        print("\n🎉 Test completati con successo!")
        print("La soluzione di eliminazione dual-table è pronta per l'uso.")
    else:
        print("\n⚠️ Test falliti. Controlla l'implementazione.")
    
    sys.exit(0 if result else 1)