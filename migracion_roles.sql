USE feriapp;

-- Ejecuta este archivo una sola vez si ya tenías creada la base de datos.
-- Los usuarios existentes quedarán como clientes.
ALTER TABLE usuarios
ADD COLUMN tipo_usuario ENUM('cliente','feriante','emprendimiento')
NOT NULL DEFAULT 'cliente' AFTER password_hash;
