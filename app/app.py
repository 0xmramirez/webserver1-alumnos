"""
Módulo Alumnos - Web Server 1
Funcionalidades:
  - Consulta de notas y resultados
  - Inscripción en asignaturas/clases disponibles
Tablas: alumnos, inscripciones
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
import psycopg2
import psycopg2.extras
import os
import boto3
from botocore.exceptions import ClientError

app = Flask(__name__, template_folder="templates", static_folder="static")

# ─── Configuración ────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "10.0.1.20"),   # IP privada del DB Server
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME", "universidad"),
    "user":     os.environ.get("DB_USER", "alumno_user"),
    "password": os.environ.get("DB_PASSWORD", ""),
}

S3_BUCKET = os.environ.get("S3_BUCKET", "practica-bucket-4lh")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# ─── Helpers ──────────────────────────────────────────────────────────────────
def get_db():
    """Abre conexión a PostgreSQL."""
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    return conn


def get_s3():
    """Cliente S3 (usa el IAM Role del EC2, sin credenciales hardcodeadas)."""
    return boto3.client("s3", region_name=AWS_REGION)


# ─── Rutas principales ─────────────────────────────────────────────────────────
@app.route("/alumnos/")
@app.route("/alumnos")
def index():
    """Página principal: lista de alumnos."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, nombre, correo FROM alumnos ORDER BY nombre;")
            alumnos = cur.fetchall()
        return render_template("index.html", alumnos=alumnos)
    finally:
        conn.close()


@app.route("/alumnos/<int:alumno_id>")
def perfil_alumno(alumno_id):
    """Perfil de un alumno: datos + notas + inscripciones activas."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Datos del alumno
            cur.execute("SELECT * FROM alumnos WHERE id = %s;", (alumno_id,))
            alumno = cur.fetchone()
            if not alumno:
                return render_template("error.html", msg="Alumno no encontrado"), 404

            # Notas: inscripciones con nota
            cur.execute("""
                SELECT i.id, a.nombre AS asignatura, i.nota, i.fecha_inscripcion
                FROM   inscripciones i
                JOIN   asignaturas   a ON a.id = i.asignatura_id
                WHERE  i.alumno_id = %s
                ORDER  BY i.fecha_inscripcion DESC;
            """, (alumno_id,))
            inscripciones = cur.fetchall()

        return render_template("perfil.html", alumno=alumno, inscripciones=inscripciones)
    finally:
        conn.close()


@app.route("/alumnos/<int:alumno_id>/notas")
def notas(alumno_id):
    """JSON con las notas del alumno (para llamadas AJAX)."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT a.nombre AS asignatura, i.nota
                FROM   inscripciones i
                JOIN   asignaturas   a ON a.id = i.asignatura_id
                WHERE  i.alumno_id = %s AND i.nota IS NOT NULL;
            """, (alumno_id,))
            notas = cur.fetchall()
        return jsonify({"alumno_id": alumno_id, "notas": notas})
    finally:
        conn.close()


@app.route("/alumnos/<int:alumno_id>/inscribir", methods=["GET", "POST"])
def inscribir(alumno_id):
    """Inscripción en una asignatura disponible."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Asignaturas disponibles (no inscritas aún)
            cur.execute("""
                SELECT id, nombre, descripcion
                FROM   asignaturas
                WHERE  id NOT IN (
                    SELECT asignatura_id FROM inscripciones WHERE alumno_id = %s
                )
                ORDER  BY nombre;
            """, (alumno_id,))
            disponibles = cur.fetchall()

            if request.method == "POST":
                asignatura_id = request.form.get("asignatura_id", type=int)
                if not asignatura_id:
                    return render_template("inscribir.html",
                                           alumno_id=alumno_id,
                                           disponibles=disponibles,
                                           error="Selecciona una asignatura.")
                cur.execute("""
                    INSERT INTO inscripciones (alumno_id, asignatura_id, fecha_inscripcion)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT DO NOTHING;
                """, (alumno_id, asignatura_id))
                conn.commit()
                return redirect(url_for("perfil_alumno", alumno_id=alumno_id))

        return render_template("inscribir.html",
                               alumno_id=alumno_id,
                               disponibles=disponibles)
    finally:
        conn.close()


# ─── S3: subir/descargar archivos del alumno ──────────────────────────────────
@app.route("/alumnos/<int:alumno_id>/archivos", methods=["GET", "POST"])
def archivos(alumno_id):
    """Gestión de archivos del alumno en S3."""
    s3 = get_s3()
    prefix = f"alumnos/{alumno_id}/"

    if request.method == "POST":
        archivo = request.files.get("archivo")
        if archivo and archivo.filename:
            key = f"{prefix}{archivo.filename}"
            try:
                s3.upload_fileobj(archivo, S3_BUCKET, key)
            except ClientError as e:
                return render_template("archivos.html",
                                       alumno_id=alumno_id,
                                       archivos=[],
                                       error=str(e))
        return redirect(url_for("archivos", alumno_id=alumno_id))

    # Listar archivos
    try:
        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
        objetos = [
            {
                "nombre": obj["Key"].replace(prefix, ""),
                "size":   obj["Size"],
                "url":    s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": S3_BUCKET, "Key": obj["Key"]},
                    ExpiresIn=300,
                ),
            }
            for obj in resp.get("Contents", [])
            if obj["Key"] != prefix
        ]
    except ClientError:
        objetos = []

    return render_template("archivos.html", alumno_id=alumno_id, archivos=objetos)


# ─── API interna (para test desde el LB) ──────────────────────────────────────
@app.route("/alumnos/api/status")
def status():
    """Endpoint de estado para el Load Balancer."""
    try:
        conn = get_db()
        conn.close()
        db_ok = True
    except Exception as e:
        db_ok = False

    return jsonify({
        "service": "webserver1-alumnos",
        "db":      "ok" if db_ok else "error",
        "status":  "ok" if db_ok else "degraded",
    }), 200 if db_ok else 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)