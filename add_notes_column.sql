-- Script SQL per aggiungere la colonna 'notes' alla tabella 'user_site_permissions'
-- Eseguire questo script sul database per applicare la modifica

-- Aggiungi la colonna 'notes' alla tabella 'user_site_permissions'
ALTER TABLE user_site_permissions 
ADD COLUMN notes TEXT;

-- Messaggio di conferma
SELECT 'Colonna notes aggiunta con successo alla tabella user_site_permissions' AS message;