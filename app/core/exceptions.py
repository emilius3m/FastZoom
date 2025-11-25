# app/core/exceptions.py - Domain Exceptions for Storage Operations

class StorageError(Exception):
    """Base exception per errori storage"""
    pass


class StorageFullError(StorageError):
    """Storage pieno, serve cleanup"""
    def __init__(self, message: str, freed_space_mb: int = 0):
        super().__init__(message)
        self.freed_space_mb = freed_space_mb


class StorageTemporaryError(StorageError):
    """Errore temporaneo, retry possibile"""
    pass


class StorageConnectionError(StorageError):
    """Problemi connessione a MinIO"""
    pass


class StorageNotFoundError(StorageError):
    """File o oggetto non trovato nello storage"""
    pass


class StoragePermissionError(StorageError):
    """Errore di permessi accesso storage"""
    pass


class StorageValidationError(StorageError):
    """Errore validazione dati storage"""
    pass