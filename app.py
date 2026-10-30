import os
from dotenv import load_dotenv
import pymysql
from pymysql.cursors import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_bcrypt import Bcrypt
from flask_socketio import SocketIO, join_room, emit
from functools import wraps

# Cargar las variables desde el archivo .env
load_dotenv()

# Configuración de Flask
app = Flask(__name__, template_folder="plantillas")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion")

bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

ROLES = ("cliente", "feriante", "emprendimiento")


def db():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "1234"),
        database=os.getenv("DB_NAME", "feriapp"),
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True
    )

def consulta(sql, params=(), uno=False):
    conexion = db()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone() if uno else cursor.fetchall()
    finally:
        conexion.close()


def ejecutar(sql, params=()):
    conexion = db()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.lastrowid
    finally:
        conexion.close()


def login_requerido(func):
    @wraps(func)
    def envoltura(*args, **kwargs):
        if not session.get("usuario_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Debes iniciar sesión"}), 401
            flash("Inicia sesión para continuar.", "warning")
            return redirect(url_for("iniciar_sesion"))
        return func(*args, **kwargs)
    return envoltura


def rol_requerido(*roles):
    """Limita una ruta a los tipos de usuario indicados."""
    def decorador(func):
        @wraps(func)
        @login_requerido
        def envoltura(*args, **kwargs):
            if session.get("usuario_tipo") not in roles:
                flash("Tu tipo de cuenta no tiene permiso para realizar esa acción.", "warning")
                return redirect(url_for("inicio"))
            return func(*args, **kwargs)
        return envoltura
    return decorador


def puede_iniciar_contacto(rol_origen, rol_destino):
    # Clientes solo pueden iniciar conversaciones con feriantes.
    # Emprendimientos pueden contactar clientes y feriantes.
    # Feriantes pueden conversar con clientes y emprendimientos.
    if rol_origen == "cliente":
        return rol_destino == "feriante"
    if rol_origen == "feriante":
        return rol_destino in ("cliente", "emprendimiento")
    if rol_origen == "emprendimiento":
        return rol_destino in ("cliente", "feriante")
    return False


def puede_conversar(otro_id):
    otro = consulta("SELECT id, tipo_usuario FROM usuarios WHERE id=%s", (otro_id,), uno=True)
    if not otro or otro_id == session.get("usuario_id"):
        return False
    mi_rol = session.get("usuario_tipo")
    if puede_iniciar_contacto(mi_rol, otro["tipo_usuario"]):
        return True
    # Un cliente puede responder a un emprendimiento que ya le escribió primero.
    if mi_rol == "cliente" and otro["tipo_usuario"] == "emprendimiento":
        return bool(consulta("""
            SELECT id FROM mensajes
            WHERE remitente_id=%s AND destinatario_id=%s LIMIT 1
        """, (otro_id, session["usuario_id"],), uno=True))
    return False


@app.context_processor
def contexto_global():
    return {
        "usuario_actual": session.get("usuario_nombre"),
        "usuario_id": session.get("usuario_id"),
        "usuario_tipo": session.get("usuario_tipo")
    }


@app.route("/")
def inicio():
    termino = request.args.get("q", "").strip()
    categoria = request.args.get("categoria", "").strip()
    sql = """SELECT p.*, u.nombre AS vendedor_nombre, u.tipo_usuario AS vendedor_tipo
             FROM productos p JOIN usuarios u ON p.vendedor_id=u.id
             WHERE p.activo=1"""
    params = []
    if termino:
        sql += " AND (p.nombre LIKE %s OR p.descripcion LIKE %s OR u.nombre LIKE %s)"
        like = f"%{termino}%"
        params += [like, like, like]
    if categoria:
        sql += " AND p.categoria=%s"
        params.append(categoria)
    sql += " ORDER BY p.creado_en DESC"
    productos = consulta(sql, tuple(params))
    categorias = consulta("SELECT DISTINCT categoria FROM productos WHERE activo=1 ORDER BY categoria")
    return render_template("inicio.html", productos=productos, categorias=categorias,
                           termino=termino, categoria=categoria)


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if session.get("usuario_id"):
        return redirect(url_for("inicio"))
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        correo = request.form.get("correo", "").strip().lower()
        password = request.form.get("password", "")
        tipo_usuario = request.form.get("tipo_usuario", "cliente").strip().lower()

        if not nombre or not correo or len(password) < 8 or tipo_usuario not in ROLES:
            flash("Completa todos los campos y elige un tipo de cuenta válido. La contraseña debe tener al menos 8 caracteres.", "danger")
            return render_template("auth.html", modo="registro")
        if consulta("SELECT id FROM usuarios WHERE correo=%s", (correo,), uno=True):
            flash("Ese correo ya está registrado.", "danger")
            return render_template("auth.html", modo="registro")

        hash_password = bcrypt.generate_password_hash(password).decode("utf-8")
        nuevo_id = ejecutar(
            "INSERT INTO usuarios (nombre, correo, password_hash, tipo_usuario) VALUES (%s,%s,%s,%s)",
            (nombre, correo, hash_password, tipo_usuario)
        )

        # Registrar también inicia la sesión: no es necesario volver a iniciar sesión.
        session.clear()
        session["usuario_id"] = nuevo_id
        session["usuario_nombre"] = nombre
        session["usuario_tipo"] = tipo_usuario
        flash("¡Tu cuenta está lista! Bienvenido/a a FeriApp.", "success")
        return redirect(url_for("inicio"))
    return render_template("auth.html", modo="registro")


@app.route("/iniciar-sesion", methods=["GET", "POST"])
def iniciar_sesion():
    if session.get("usuario_id"):
        return redirect(url_for("inicio"))
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        password = request.form.get("password", "")
        usuario = consulta("SELECT * FROM usuarios WHERE correo=%s", (correo,), uno=True)
        if not usuario or not bcrypt.check_password_hash(usuario["password_hash"], password):
            flash("Correo o contraseña incorrectos.", "danger")
            return render_template("auth.html", modo="login")
        session.clear()
        session["usuario_id"] = usuario["id"]
        session["usuario_nombre"] = usuario["nombre"]
        session["usuario_tipo"] = usuario.get("tipo_usuario", "cliente")
        flash(f"¡Hola, {usuario['nombre']}!", "success")
        return redirect(url_for("inicio"))
    return render_template("auth.html", modo="login")


@app.route("/cerrar-sesion", methods=["POST"])
def cerrar_sesion():
    session.clear()
    flash("Has cerrado sesión.", "info")
    return redirect(url_for("inicio"))


@app.route("/publicar", methods=["GET", "POST"])
@rol_requerido("feriante", "emprendimiento")
def publicar():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        categoria = request.form.get("categoria", "")
        descripcion = request.form.get("descripcion", "").strip()
        precio = request.form.get("precio", "")
        cantidad = request.form.get("cantidad", "").strip()
        ubicacion = request.form.get("ubicacion", "").strip()
        try:
            precio = int(precio)
            if precio < 1 or not nombre or not categoria or not cantidad:
                raise ValueError()
        except (ValueError, TypeError):
            flash("Revisa el nombre, categoría, precio y cantidad.", "danger")
            return render_template("publicar.html")
        ejecutar("""INSERT INTO productos
            (vendedor_id,nombre,categoria,descripcion,precio,cantidad,ubicacion)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (session["usuario_id"], nombre, categoria, descripcion, precio, cantidad, ubicacion))
        flash("Producto publicado correctamente.", "success")
        return redirect(url_for("inicio"))
    return render_template("publicar.html")


@app.route("/chat")
@login_requerido
def chat():
    mi_id = session["usuario_id"]
    mi_rol = session.get("usuario_tipo", "cliente")
    contactos = consulta("""
        SELECT u.id, u.nombre, u.correo, u.tipo_usuario,
               (SELECT m.contenido FROM mensajes m
                WHERE (m.remitente_id=u.id AND m.destinatario_id=%s)
                   OR (m.remitente_id=%s AND m.destinatario_id=u.id)
                ORDER BY m.creado_en DESC, m.id DESC LIMIT 1) AS ultimo_mensaje,
               (SELECT m.creado_en FROM mensajes m
                WHERE (m.remitente_id=u.id AND m.destinatario_id=%s)
                   OR (m.remitente_id=%s AND m.destinatario_id=u.id)
                ORDER BY m.creado_en DESC, m.id DESC LIMIT 1) AS fecha_ultimo
        FROM usuarios u WHERE u.id<>%s
        ORDER BY fecha_ultimo DESC, u.nombre ASC
    """, (mi_id, mi_id, mi_id, mi_id, mi_id))
    # Solo muestra contactos con los que esta cuenta puede conversar.
    contactos = [c for c in contactos if puede_iniciar_contacto(mi_rol, c["tipo_usuario"])
                 or (mi_rol == "cliente" and c["tipo_usuario"] == "emprendimiento"
                     and consulta("SELECT id FROM mensajes WHERE remitente_id=%s AND destinatario_id=%s LIMIT 1",
                                  (c["id"], mi_id), uno=True))]
    contacto_id = request.args.get("con", type=int)
    if contacto_id and not any(c["id"] == contacto_id for c in contactos):
        contacto_id = None
    return render_template("chat.html", contactos=contactos, contacto_id=contacto_id)


@app.route("/api/mensajes/<int:otro_id>")
@login_requerido
def api_mensajes(otro_id):
    if not puede_conversar(otro_id):
        return jsonify({"error": "No tienes permiso para conversar con este usuario."}), 403
    desde = request.args.get("desde", 0, type=int)
    mensajes = consulta("""
        SELECT m.id, m.remitente_id, m.destinatario_id, m.contenido, m.creado_en,
               u.nombre AS remitente_nombre
        FROM mensajes m JOIN usuarios u ON u.id=m.remitente_id
        WHERE ((m.remitente_id=%s AND m.destinatario_id=%s)
            OR (m.remitente_id=%s AND m.destinatario_id=%s))
            AND m.id>%s
        ORDER BY m.id ASC
    """, (session["usuario_id"], otro_id, otro_id, session["usuario_id"], desde))
    for mensaje in mensajes:
        if mensaje.get("creado_en"):
            mensaje["creado_en"] = mensaje["creado_en"].strftime("%H:%M")
    return jsonify(mensajes)


@socketio.on("unirse_chat")
def unirse_chat(datos):
    if not session.get("usuario_id"):
        emit("error_chat", {"mensaje": "Inicia sesión para usar el chat."})
        return
    try:
        otro_id = int(datos.get("otro_id", 0))
    except (ValueError, TypeError, AttributeError):
        emit("error_chat", {"mensaje": "Contacto no válido."})
        return
    if not puede_conversar(otro_id):
        emit("error_chat", {"mensaje": "Tu tipo de cuenta no puede iniciar esta conversación."})
        return
    join_room(sala_chat(session["usuario_id"], otro_id))


@socketio.on("enviar_mensaje")
def enviar_mensaje(datos):
    if not session.get("usuario_id"):
        emit("error_chat", {"mensaje": "Tu sesión ha terminado. Vuelve a iniciar sesión."})
        return
    try:
        otro_id = int(datos.get("otro_id", 0))
    except (ValueError, TypeError, AttributeError):
        return
    contenido = str(datos.get("contenido", "")).strip()
    if not contenido or len(contenido) > 2000 or not puede_conversar(otro_id):
        emit("error_chat", {"mensaje": "No puedes enviar mensajes a ese usuario."})
        return
    mensaje_id = ejecutar("INSERT INTO mensajes (remitente_id,destinatario_id,contenido) VALUES (%s,%s,%s)",
                          (session["usuario_id"], otro_id, contenido))
    mensaje = consulta("""SELECT m.id,m.remitente_id,m.destinatario_id,m.contenido,m.creado_en,
                          u.nombre AS remitente_nombre FROM mensajes m
                          JOIN usuarios u ON u.id=m.remitente_id WHERE m.id=%s""",
                       (mensaje_id,), uno=True)
    mensaje["creado_en"] = mensaje["creado_en"].strftime("%H:%M")
    sala = sala_chat(session["usuario_id"], otro_id)
    emit("nuevo_mensaje", mensaje, to=sala)


def sala_chat(a, b):
    x, y = sorted([int(a), int(b)])
    return f"chat_{x}_{y}"


@app.errorhandler(500)
def error_servidor(error):
    return render_template("error.html"), 500


if __name__ == "__main__":
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
