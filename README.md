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

## Bootstrap del fork "bienestar" desde la quiniela original

Este fork reutiliza los datos de la quiniela original (usuarios, contraseñas,
partidos **con resultados reales** y predicciones). En vez de re-sembrar, se
**clona** la BD original y sobre el clon se aplica una transformación
idempotente. Mismo procedimiento en local y en producción; las credenciales
son idénticas (solo cambia el nombre de la BD, ver `POSTGRES_DB` y
`POSTGRES_DB_ORIGINAL` en `.env`).

```bash
# Toma las credenciales del entorno; psql/pg_dump piden la contraseña vía
# PGPASSWORD (o ~/.pgpass) para no exponerla en el comando.
export PGPASSWORD="$POSTGRES_PASSWORD"

# 1) Crear la BD destino vacía (una sola vez).
createdb -h "$POSTGRES_HOST" -U "$POSTGRES_USER" "$POSTGRES_DB"

# 2) Clonar la original -> destino (snapshot consistente, en caliente).
pg_dump -h "$POSTGRES_HOST" -U "$POSTGRES_USER" "$POSTGRES_DB_ORIGINAL" \
  | psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" "$POSTGRES_DB"

# 3) Aplicar las migraciones del fork (columnas nuevas: is_group,
#    multiplier, advancing_team) y transformar el clon.
python manage.py migrate
python manage.py bootstrap_bienestar --yes
```

`bootstrap_bienestar` parte la fase de grupos en 3 sub-fases
(`SUBGROUP_1/2/3`) reasignando solo el FK `stage` de cada partido (no toca
marcadores ni `status`), borra las predicciones de la 1.ª jornada (ya jugada;
`SUBGROUP_1` nace cerrada) y pone todos los `sent_at` en null. Es idempotente
en estructura, pero **reejecutarlo vuelve a reiniciar los `sent_at`**: corre
solo en el montaje, antes de abrir la quiniela. Después, fija en el admin las
fechas (`opens_at` / `send_deadline`) de `SUBGROUP_2` y `SUBGROUP_3`.

> El clon es **puntual**, no un espejo en vivo: tras clonar, las dos
> quinielas divergen (un cambio de contraseña en la original no se propaga).

## Crear un superuser para poder entrar al admin

```bash
python manage.py createsuperuser
```

## CSS (Tailwind + daisyUI)

No se necesita Node ni npm: `django-tailwind-cli` descarga solo el binario
de Tailwind (variante `tailwindcss-extra`, que ya incluye daisyUI) en la
versión fijada en `settings.py`. La fuente es `assets/css/source.css` (tema
y tokens; vive fuera de `static/` para que `collectstatic` no intente
procesar su `@import "tailwindcss"`) y el compilado
`static/css/tailwind.css` **no se versiona**.

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
