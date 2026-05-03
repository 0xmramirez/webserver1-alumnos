-- ============================================================
-- Schema: Módulo Alumnos (Web Server 1)
-- Tablas propias: alumnos, inscripciones
-- Tabla compartida (owner: DB Server): asignaturas
-- ============================================================

-- Ejecutar como superusuario o dueño de la BD
-- psql -U postgres -d universidad -f schema.sql

-- ─── Tabla alumnos ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alumnos (
    id        SERIAL PRIMARY KEY,
    nombre    VARCHAR(120) NOT NULL,
    correo    VARCHAR(120) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Tabla asignaturas (compartida con profesores) ────────────
-- Si la gestiona el módulo de profesores, este módulo sólo lee.
-- Si eres el primero en desplegar, créala aquí:
CREATE TABLE IF NOT EXISTS asignaturas (
    id          SERIAL PRIMARY KEY,
    nombre      VARCHAR(120) NOT NULL,
    descripcion TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Tabla inscripciones ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS inscripciones (
    id               SERIAL PRIMARY KEY,
    alumno_id        INTEGER NOT NULL REFERENCES alumnos(id) ON DELETE CASCADE,
    asignatura_id    INTEGER NOT NULL REFERENCES asignaturas(id) ON DELETE CASCADE,
    nota             NUMERIC(4,2) CHECK (nota BETWEEN 0 AND 10),
    fecha_inscripcion TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (alumno_id, asignatura_id)
);

-- ─── Usuario con permisos mínimos (mínimo privilegio) ─────────
-- Crear usuario si no existe:
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'alumno_user') THEN
        CREATE ROLE alumno_user LOGIN PASSWORD 'CambiarEstoEnProduccion!';
    END IF;
END
$$;

-- Permisos SOLO sobre las tablas que necesita
GRANT CONNECT ON DATABASE universidad TO alumno_user;
GRANT USAGE   ON SCHEMA public TO alumno_user;

-- alumnos: lectura y escritura (crear, editar perfil)
GRANT SELECT, INSERT, UPDATE ON TABLE alumnos TO alumno_user;
GRANT USAGE, SELECT ON SEQUENCE alumnos_id_seq TO alumno_user;

-- asignaturas: sólo lectura
GRANT SELECT ON TABLE asignaturas TO alumno_user;

-- inscripciones: lectura y escritura
GRANT SELECT, INSERT, UPDATE ON TABLE inscripciones TO alumno_user;
GRANT USAGE, SELECT ON SEQUENCE inscripciones_id_seq TO alumno_user;

-- ─── Datos de ejemplo ─────────────────────────────────────────
INSERT INTO alumnos (nombre, correo) VALUES
    ('Ana García',    'ana.garcia@ufv.es'),
    ('Carlos López',  'carlos.lopez@ufv.es'),
    ('Marta Pérez',   'marta.perez@ufv.es')
ON CONFLICT DO NOTHING;

INSERT INTO asignaturas (nombre, descripcion) VALUES
    ('Redes de Computadores',   'Fundamentos de redes TCP/IP'),
    ('Sistemas Operativos',     'Linux y Windows Server'),
    ('Bases de Datos',          'SQL y modelado relacional'),
    ('Cloud Computing',         'AWS, Azure, servicios cloud')
ON CONFLICT DO NOTHING;

INSERT INTO inscripciones (alumno_id, asignatura_id, nota) VALUES
    (1, 1, 8.5),
    (1, 2, 7.0),
    (2, 1, 6.5),
    (3, 3, 9.0),
    (3, 4, NULL)  -- inscrita pero sin nota aún
ON CONFLICT DO NOTHING;