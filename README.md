# FeriApp funcional: Flask + MySQL + chat real

Esta versión transforma la maqueta visual en una aplicación web con servidor, cuentas persistentes y mSensajería entre usuarios. El chat guarda cada mensaje en MySQL y lo entrega en tiempo real mediante Flask-SocketIO; también consulta periódicamente como respaldo.

## Requisitos
- Python 3.10 o superior
- MySQL 8 o compatible
- Navegador moderno e internet para cargar Bootstrap y Socket.IO desde CDN

## 1. Crear la base de datos
Abre MySQL Workbench o la consola de MySQL y ejecuta todo el archivo `base_datos.sql`.

## 2. Instalar dependencias
En una terminal, dentro de esta carpeta:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Configurar MySQL
Por defecto la aplicación intenta conectarse a `localhost`, usuario `root`, contraseña vacía y base `feriapp`. Si tu configuración es diferente, define variables de entorno antes de iniciar.

PowerShell (Windows):
```powershell
$env:DB_HOST="localhost"
$env:DB_USER="root"
$env:DB_PASSWORD="TU_CLAVE_MYSQL"
$env:DB_NAME="feriapp"
$env:SECRET_KEY="una-clave-larga-y-aleatoria"
```

## 4. Ejecutar
```bash
python app.py
```
Abre `http://127.0.0.1:5000`.

## 5. Probar el chat entre dos personas
1. Abre la web y registra una primera cuenta.
2. Abre otro navegador/perfil incógnito y registra una segunda cuenta.
3. Inicia sesión con una cuenta y abre **Mensajes**; selecciona al otro usuario.
4. Envía mensajes. Inicia sesión con la segunda cuenta en el otro navegador y abre la misma conversación.
5. Los mensajes se guardan en la tabla `mensajes`; no dependen de `localStorage`.

## Funcionalidades incluidas
- Catálogo público con búsqueda y filtro por categoría.
- Registro, inicio y cierre de sesión con contraseña hasheada usando Bcrypt.
- Publicación de productos asociada a la cuenta del vendedor.
- Contacto desde cada publicación.
- Chat entre usuarios autenticados, persistido en MySQL y actualizado en tiempo real.
- Diseño adaptable a escritorio y móvil.
- Diagrama ERD en `resources/diagrama_entidad_relacion.mmd`.

## Importante antes de publicar en internet
La clave secreta de ejemplo debe cambiarse. Configura HTTPS, protección CSRF para formularios, limitación de intentos de inicio de sesión, validaciones adicionales, gestión de permisos y una configuración de despliegue adecuada. Este proyecto es una base funcional para desarrollo local/educativo, no una auditoría de seguridad de producción.


## Tipos de cuenta y permisos
Al registrarse se elige un tipo de cuenta y la sesión se inicia automáticamente:
- **Cliente:** explora productos y puede iniciar conversaciones con feriantes. Si un emprendimiento le escribe primero, puede responder en esa conversación.
- **Feriante:** publica alimentos y conversa con clientes y emprendimientos.
- **Emprendimiento:** publica productos y conversa con clientes y feriantes.

Los permisos se validan tanto en las páginas como en las rutas del servidor y en los eventos del chat.

## Actualizar una base de datos que ya existe
Si ya habías ejecutado `base_datos.sql` antes de esta actualización, abre MySQL Workbench y ejecuta **una sola vez** el archivo `migracion_roles.sql`. Este añade la columna `tipo_usuario`; las cuentas que ya existían quedarán clasificadas como clientes. No ejecutes esa migración si ya existe la columna.

En una instalación nueva, ejecuta el `base_datos.sql` actualizado normalmente.
