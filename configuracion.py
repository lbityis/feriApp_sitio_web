# Configura estas variables de entorno antes de ejecutar en producción.
# Por defecto se conecta a MySQL local con usuario root y contraseña vacía.
import os
class Configuracion:
    SECRET_KEY = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "feriapp")
