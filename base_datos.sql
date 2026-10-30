CREATE DATABASE IF NOT EXISTS feriapp
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE feriapp;

CREATE TABLE IF NOT EXISTS usuarios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(100) NOT NULL,
  correo VARCHAR(190) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  tipo_usuario ENUM('cliente','feriante','emprendimiento') NOT NULL DEFAULT 'cliente',
  creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS productos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  vendedor_id INT NOT NULL,
  nombre VARCHAR(140) NOT NULL,
  categoria VARCHAR(60) NOT NULL,
  descripcion TEXT,
  precio INT NOT NULL,
  cantidad VARCHAR(80) NOT NULL,
  ubicacion VARCHAR(160) DEFAULT '',
  activo TINYINT(1) NOT NULL DEFAULT 1,
  creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_producto_vendedor FOREIGN KEY (vendedor_id)
    REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mensajes (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  remitente_id INT NOT NULL,
  destinatario_id INT NOT NULL,
  contenido VARCHAR(2000) NOT NULL,
  creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_mensaje_remitente FOREIGN KEY (remitente_id)
    REFERENCES usuarios(id) ON DELETE CASCADE,
  CONSTRAINT fk_mensaje_destinatario FOREIGN KEY (destinatario_id)
    REFERENCES usuarios(id) ON DELETE CASCADE,
  INDEX idx_conversacion (remitente_id, destinatario_id, id)
) ENGINE=InnoDB;

-- Productos iniciales: aparecen al registrarse el primer usuario que los publique.
-- Para que existan publicaciones en el catálogo, registra usuarios y publica alimentos desde la web.
