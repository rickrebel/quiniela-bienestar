# sanginiela

Quiniela familiar del Mundial. Los participantes preregistrados entran con
su correo (sin contraseña), pronostican los marcadores de la fase de grupos,
los guardan como borrador y, al enviarlos, reciben por correo un Excel con
sus predicciones.

Construida con **Django** (server-rendered, sin DRF), plantillas DTL y JS
vanilla. Los estilos usan **Tailwind CSS v4 + daisyUI** (compilados con un
binario standalone, sin Node) y los componentes de template reusables usan
**django-cotton** (`templates/cotton/`). PostgreSQL en producción, con
respaldo en SQLite para desarrollo local.

El código se reparte en dos apps: `tournament` (datos deportivos: estadios,
fases, equipos y partidos) y `pool` (usuarios y pronósticos). Los datos
deportivos se siembran desde dos fuentes externas —openfootball (OF) y
football-data.org (FD)— cuyos snapshots viven en `db/jsons/`.

## Pasos iniciales

- Tener instalado Python 3, mínimo 3.13
- Instalar pip (normalmente ya viene con python)
- Revisar que las variables de entorno se escribieron adecuadamente (si se
  trabaja en Windows)

## Entornos virtuales

- Preferentemente, tener dos carpetas separadas (para una mejor
  organización): una para los entornos virtuales y otra para los
  sistemas/proyectos.
- Crear un ambiente virtual, en este caso llamado 'quiniela' en la carpeta
  de entornos:

```bash
python -m venv quiniela
```

- Iniciar el entorno virtual (venv):

```bash
# en Windows
.\quiniela\Scripts\Activate.ps1
# o en Linux/Mac
source quiniela/bin/activate
```

## Variables de entorno

- Crear un archivo `.env` en la raíz del proyecto con las variables
  necesarias (puedes basarte en el archivo `.env.example`).

## Instalación de paquetes requeridos

- Instalar los paquetes requeridos (vienen en `requirements.txt`):

```bash
pip install -r requirements.txt
```

## Base de datos

### Opción SQLite (por defecto, para desarrollo local)

No requiere configuración: si la variable `POSTGRES_DB` queda vacía o no
existe en tu `.env`, el proyecto usa automáticamente un archivo SQLite en
`db/app.sqlite3`.

### Opción PostgreSQL (para producción o equipos que ya lo usan)

- Deberás tener instalado PostgreSQL.
- Crear una base de datos en PostgreSQL (p. ej. 'quiniela').
- Configurar tu archivo `.env` con las credenciales de PostgreSQL:

```env
POSTGRES_DB=quiniela
POSTGRES_USER=tu_usuario
POSTGRES_PASSWORD=tu_contraseña
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

## Migraciones y carga de datos

Orden de ejecución:

```bash
python manage.py makemigrations
python manage.py migrate
```

Cargar los datos deportivos (desde los JSON en `db/jsons/`). Los comandos de
seed viven en la app `tournament` y se ejecutan en este orden, porque cada uno
depende del anterior (los partidos referencian estadios, fases y equipos):

```bash
python manage.py load_stadiums
python manage.py load_stages
python manage.py load_teams
python manage.py load_matches
```

Preregistrar un participante (comando de la app `pool`; entra después solo con
su correo):

```bash
python manage.py preregister correo@ejemplo.com "Nombre del Jugador"
```

## Crear un superuser para poder entrar al admin

```bash
python manage.py createsuperuser
```

## CSS (Tailwind + daisyUI)

No se necesita Node ni npm: `django-tailwind-cli` descarga solo el binario
de Tailwind (variante `tailwindcss-extra`, que ya incluye daisyUI) en la
versión fijada en `settings.py`. La fuente es `static/css/source.css` (tema
y tokens) y el compilado `static/css/tailwind.css` **no se versiona**.

```bash
# desarrollo: Django + watcher de Tailwind en un solo comando
python manage.py tailwind runserver

# o solo recompilar el CSS una vez
python manage.py tailwind build
```

## Correr el servidor localmente

- Antes de correr el servicio en producción, genera el CSS y los archivos
  estáticos:

```bash
python manage.py tailwind build
python manage.py collectstatic
```

- Correr el servidor localmente:

```bash
python manage.py runserver
```

- Acceder a la aplicación en `http://localhost:8000/` (redirige a `/login`).
- Acceder al admin en `http://localhost:8000/admin`.

## Flujo de la aplicación

- `/login` — acceso por correo (sin contraseña). Si el correo no está
  preregistrado, se rechaza; si lo está, se activa al primer ingreso.
- `/grupos` — captura de pronósticos de la fase de grupos. **Guardar** deja
  un borrador (`saved`); **Enviar** marca las predicciones como definitivas
  (`submitted`), envía el Excel por correo y bloquea futuras ediciones.
- `/logout` — cierra sesión.

## Envío de correos

El envío del Excel usa SMTP por SSL (puerto 465). Configura en tu `.env` una
cuenta de Gmail con **contraseña de aplicación** (`GMAIL_APP_PASSWORD`), no la
contraseña normal de la cuenta.
