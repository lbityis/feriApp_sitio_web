import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
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
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL no está configurada en las variables de entorno.")
    return psycopg2.connect(database_url, cursor_factory=RealDictCursor)


def crear_tablas():
    conexion = db()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                correo VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                tipo_usuario VARCHAR(50) DEFAULT 'cliente',
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS productos (
                id SERIAL PRIMARY KEY,
                vendedor_id INT REFERENCES usuarios(id) ON DELETE CASCADE,
                nombre VARCHAR(150) NOT NULL,
                categoria VARCHAR(50) NOT NULL,
                descripcion TEXT,
                precio INT NOT NULL,
                cantidad VARCHAR(50),
                ubicacion VARCHAR(150),
                activo INT DEFAULT 1,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS mensajes (
                id SERIAL PRIMARY KEY,
                remitente_id INT REFERENCES usuarios(id) ON DELETE CASCADE,
                destinatario_id INT REFERENCES usuarios(id) ON DELETE CASCADE,
                contenido TEXT NOT NULL,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            conexion.commit()
    except Exception as e:
        conexion.rollback()
        print(f"Error al crear tablas: {e}")
    finally:
        conexion.close()


def poblar_catalogo():
    conexion = db()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT id FROM usuarios LIMIT 1;")
            usuario = cursor.fetchone()
            
            if not usuario:
                hash_pw = bcrypt.generate_password_hash("12345678").decode("utf-8")
                cursor.execute("""
                    INSERT INTO usuarios (nombre, correo, password_hash, tipo_usuario)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id;
                """, ("Feria La Central", "contacto@lacentral.cl", hash_pw, "feriante"))
                usuario = cursor.fetchone()

            vendedor_id = usuario["id"]

            cursor.execute("DELETE FROM productos WHERE ubicacion LIKE '%La Central%';")

            productos_ejemplo = [
                (vendedor_id, "Manzanas Fuji Frescas", "Frutas", "Manzanas crujientes y jugosas recién cosechadas.", 1200, "1 kg", "Puesto 12 - La Central", 1),
                (vendedor_id, "Naranjas del Valle", "Frutas", "Naranjas dulces ideales para jugo natural.", 1500, "1.5 kg", "Puesto 12 - La Central", 1),
                (vendedor_id, "Plátanos Maduros", "Frutas", "Plátanos de primera calidad, listos para consumo.", 1100, "1 kg", "Puesto 12 - La Central", 1),
                (vendedor_id, "Zanahorias Orgánicas", "Verduras", "Zanahorias frescas sin pesticidas.", 800, "1 kg", "Puesto 14 - La Central", 1),
                (vendedor_id, "Lechuga Costina", "Verduras", "Lechuga fresca y crujiente para ensaladas.", 700, "1 unidad", "Puesto 14 - La Central", 1),
                (vendedor_id, "Tomates Limachinos", "Verduras", "Tomates de gran sabor y aroma tradicional.", 1800, "1 kg", "Puesto 14 - La Central", 1),
                (vendedor_id, "Miel Multifloral Artesanal", "Abarrotes", "Miel 100% pura recolectada de apicultores locales.", 4500, "500 g", "Puesto 20 - La Central", 1),
                (vendedor_id, "Queso Mantecoso Artesanal", "Lácteos", "Queso de campo cremoso de excelente calidad.", 3800, "500 g", "Puesto 08 - La Central", 1),
                (vendedor_id, "Huevos de Gallina Libre", "Lácteos", "Bandeja de huevos frescos de campo.", 3200, "12 unidades", "Puesto 08 - La Central", 1)
            ]

            cursor.executemany("""
                INSERT INTO productos (vendedor_id, nombre, categoria, descripcion, precio, cantidad, ubicacion, activo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """, productos_ejemplo)

            conexion.commit()
            print("Catálogo cargado con éxito.")
    except Exception as e:
        conexion.rollback()
        print(f"Error al poblar el catálogo: {e}")
    finally:
        conexion.close()


try:
    crear_tablas()
    poblar_catalogo()
except Exception as e:
    print(f"No se pudo inicializar la base de datos: {e}")


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
            if "RETURNING" not in sql.upper():
                sql = sql.rstrip(";") + " RETURNING id;"
            cursor.execute(sql, params)
            row = cursor.fetchone()
            conexion.commit()
            return row["id"] if row else None
    except Exception:
        conexion.rollback()
        raise
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
    if rol_origen == "cliente":
        return rol_destino in ("feriante", "emprendimiento")
    if rol_origen == "feriante":
        return rol_destino in ("cliente", "feriante", "emprendimiento")
    if rol_origen == "emprendimiento":
        return rol_destino in ("cliente", "feriante", "emprendimiento")
    return True


def puede_conversar(otro_id):
    otro = consulta("SELECT id, tipo_usuario FROM usuarios WHERE id=%s", (otro_id,), uno=True)
    if not otro or otro_id == session.get("usuario_id"):
        return False
    mi_rol = session.get("usuario_tipo")
    return puede_iniciar_contacto(mi_rol, otro["tipo_usuario"])


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
        sql += " AND (p.nombre ILIKE %s OR p.descripcion ILIKE %s OR u.nombre ILIKE %s)"
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
        ORDER BY fecha_ultimo DESC NULLS LAST, u.nombre ASC
    """, (mi_id, mi_id, mi_id, mi_id, mi_id))
    
    contactos_filtrados = [c for c in contactos if puede_iniciar_contacto(mi_rol, c["tipo_usuario"])]

    contacto_id = request.args.get("con", type=int)
    
    if contacto_id and not any(c["id"] == contacto_id for c in contactos_filtrados):
        vendedor = consulta("SELECT id, nombre, correo, tipo_usuario FROM usuarios WHERE id=%s", (contacto_id,), uno=True)
        if vendedor and puede_iniciar_contacto(mi_rol, vendedor["tipo_usuario"]):
            vendedor["ultimo_mensaje"] = None
            vendedor["fecha_ultimo"] = None
            contactos_filtrados.insert(0, vendedor)
        else:
            contacto_id = None

    return render_template("chat.html", contactos=contactos_filtrados, contacto_id=contacto_id)


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
