-- Los avisos automaticos de revision no pertenecen al usuario del escritorio
-- ni al administrador que pulsa Aprobar/Rechazar.
UPDATE msg_messages
SET author_type = 'system',
    author_id = 'gestinem',
    author_name = 'Gestinem'
WHERE idempotency_key LIKE 'profile-change-review-%';
