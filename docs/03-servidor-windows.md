# Instalar el aula en el servidor del CETPRO (Windows + IIS + Waitress + PostgreSQL)

Guía para el servidor Windows que **ya tiene** la página web del CETPRO funcionando con IIS y la dirección pública de
Tailscale `https://win-fajp35h0a1o.tail27cdce.ts.net`. El aula queda en el mismo IIS, al lado de la página web:

```
https://win-fajp35h0a1o.tail27cdce.ts.net/aula/
```

Cómo funciona (en una línea): **IIS** recibe a la gente y le pasa lo que llega a `/aula` a **Waitress** (el programa de
Python que corre el aula, solo visible dentro del servidor, en `127.0.0.1:8000`), que usa la base **PostgreSQL**.

**No avances a la siguiente parte hasta que la actual funcione.** Todos los comandos van en **PowerShell como
Administrador** (clic derecho → «Ejecutar como administrador»).

> **Qué está probado.** La aplicación, Waitress detrás de un proxy bajo `/aula`, el respaldo y la migración están
> probados en una PC con Windows. Las partes de **IIS y del servicio de Windows (NSSM)** no se pudieron probar ahí (esa PC
> no tiene IIS): sigue la guía con calma y usa la tabla «Si algo sale mal» del final.

---

## PARTE 1 — Programas que hay que instalar

| Programa | Para qué | Dónde |
|---|---|---|
| **Python 3.12** (64 bits) | Corre el aula | <https://www.python.org/downloads/windows/> — marca «Add python.exe to PATH» |
| **PostgreSQL 18** | La base de datos | <https://www.postgresql.org/download/windows/> — apunta la clave del usuario `postgres` |
| **URL Rewrite 2.1** y **Application Request Routing 3.0** | IIS reenvía `/aula` al aula | <https://www.iis.net/downloads/microsoft/url-rewrite> y <https://www.iis.net/downloads/microsoft/application-request-routing> |
| **NSSM** | Deja el aula corriendo como servicio de Windows | <https://nssm.cc/download> — copia `nssm.exe` (64 bits) a `C:\Windows\System32` |

Revisa:

```powershell
python --version                      # Python 3.12.x
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" --version
Test-Path "$env:SystemRoot\System32\inetsrv\rewrite.dll"       # True = URL Rewrite instalado
Test-Path "$env:ProgramFiles\IIS\Application Request Routing"  # True = ARR instalado
nssm version
```

PostgreSQL solo debe escuchar en este servidor (así viene por defecto: `localhost`). No abras el puerto 5432 al exterior.

---

## PARTE 2 — Copiar el aula al servidor

El aula va **fuera** de `C:\inetpub\wwwroot`: así nadie puede abrir su configuración ni los archivos subidos.

```powershell
git clone https://github.com/USUARIO/AulaVirtualCetpro.git C:\aula\AulaVirtualCetpro
# (o descomprime el .zip del proyecto en C:\aula\AulaVirtualCetpro)
cd C:\aula\AulaVirtualCetpro
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

**Cómo saber que funcionó:** `.venv\Scripts\python manage.py --version` muestra `5.2.x`.

---

## PARTE 3 — Crear la base y el archivo de configuración (secreto)

```powershell
cd C:\aula\AulaVirtualCetpro
powershell -ExecutionPolicy Bypass -File scripts\crear-base-postgres.ps1
notepad .env
```

El script pide la clave de `postgres`, crea el usuario y la base del aula, y escribe `.env` con una clave secreta nueva.
Después, en `.env`, deja estos valores (cambia lo que corresponda):

```ini
DEBUG=False
ALLOWED_HOSTS=win-fajp35h0a1o.tail27cdce.ts.net,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://win-fajp35h0a1o.tail27cdce.ts.net
SESSION_COOKIE_SECURE=True
FORCE_SCRIPT_NAME=/aula
URL_BASE=https://win-fajp35h0a1o.tail27cdce.ts.net/aula
# Opcional: guardar archivos y respaldos en otro disco
# ARCHIVOS_CARPETA=D:/AulaVirtual/archivos
# RESPALDOS_CARPETA=E:/RespaldosAula
```

- `FORCE_SCRIPT_NAME=/aula` es lo que hace que todas las direcciones del aula empiecen con `/aula`.
- Si algún día el aula va en la raíz de otra dirección, quita esa línea y `URL_BASE` ya no lleva `/aula`.

---

## PARTE 4 — Crear las tablas y preparar los estilos

```powershell
cd C:\aula\AulaVirtualCetpro
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py collectstatic --noinput
.venv\Scripts\python manage.py check
```

Ahora elige **una** de estas dos:

- **Aula nueva, sin datos:** crea el administrador:
  `.venv\Scripts\python manage.py createsuperuser` (el correo es el que usará para entrar).
- **Pasar los datos del piloto (PHP):** sigue [02-migracion-desde-php.md](02-migracion-desde-php.md). Hazlo **antes** de
  crear ningún administrador: la migración trae el de antes.

> Revisión extra: `manage.py check --deploy` avisa de dos cosas (`SECURE_HSTS_SECONDS` y `SECURE_SSL_REDIRECT`).
> Son a propósito: el aula comparte dirección con la página web del CETPRO y de HTTPS se encarga Tailscale/IIS;
> activar HSTS desde el aula afectaría a toda la dirección y es difícil de deshacer.

---

## PARTE 5 — Dejar el aula corriendo como servicio (Waitress + NSSM)

```powershell
$aula = "C:\aula\AulaVirtualCetpro"
New-Item -ItemType Directory -Force -Path "C:\aula\logs" | Out-Null
nssm install AulaVirtual "$aula\.venv\Scripts\python.exe"
nssm set AulaVirtual AppParameters '-m waitress --listen=127.0.0.1:8000 --threads=8 --trusted-proxy=127.0.0.1 "--trusted-proxy-headers=x-forwarded-for x-forwarded-proto" --clear-untrusted-proxy-headers config.wsgi:application'
nssm set AulaVirtual AppDirectory $aula
nssm set AulaVirtual Start SERVICE_AUTO_START
nssm set AulaVirtual AppStdout C:\aula\logs\aula.log
nssm set AulaVirtual AppStderr C:\aula\logs\aula.log
nssm set AulaVirtual AppRotateFiles 1
nssm set AulaVirtual AppRotateBytes 5000000
nssm start AulaVirtual
```

- `--listen=127.0.0.1:8000`: el aula **no** se ve desde fuera del servidor; solo IIS le habla.
- `--trusted-proxy…`: así el aula sabe la dirección real de quien visita y si entró por https.

**Cómo saber que funcionó:** `Get-Service AulaVirtual` dice `Running` y en el navegador **del servidor**
`http://127.0.0.1:8000/login` muestra la pantalla de entrada (sin estilos bonitos: sin `/aula`, es normal que algunos
enlaces apunten a `/aula/...`).

Para ver qué pasa: `Get-Content C:\aula\logs\aula.log -Tail 50`.

---

## PARTE 6 — Permisos de escritura

El servicio corre con la cuenta que elijas (por defecto `Local System`). Si usas otra cuenta, dale permiso para escribir en
la carpeta de archivos subidos y en la de respaldos:

```powershell
icacls "C:\aula\AulaVirtualCetpro\storage" /grant "NOMBRE_DE_LA_CUENTA:(OI)(CI)M" /T
```

---

## PARTE 7 — IIS: reenviar `/aula` al aula

### 7.1 Permitir el proxy y la variable del protocolo (una sola vez)

```powershell
Import-Module WebAdministration
Set-WebConfigurationProperty -pspath 'MACHINE/WEBROOT/APPHOST' -filter "system.webServer/proxy" -name "enabled" -value "True"
Set-WebConfigurationProperty -pspath 'MACHINE/WEBROOT/APPHOST' -filter "system.webServer/proxy" -name "timeout" -value "00:02:00"
Add-WebConfigurationProperty -pspath 'MACHINE/WEBROOT/APPHOST' -filter "system.webServer/rewrite/allowedServerVariables" -name "." -value @{name="HTTP_X_FORWARDED_PROTO"}
```

El tiempo de 2 minutos es para que alguien con internet lento pueda subir una foto sin que se corte.

### 7.2 Crear la aplicación «aula»

```powershell
New-Item -ItemType Directory -Force -Path C:\aula\proxy | Out-Null
Copy-Item C:\aula\AulaVirtualCetpro\deploy\iis\web.config C:\aula\proxy\web.config
New-WebApplication -Site "Default Web Site" -Name "aula" -PhysicalPath "C:\aula\proxy" -ApplicationPool "DefaultAppPool"
iisreset
```

*(Si tu página web usa otro nombre de sitio en IIS, cámbialo en `-Site`. Puedes verlo con `Get-Website`.)*

La carpeta `C:\aula\proxy` solo tiene un `web.config`: no contiene el aula ni sus datos.

---

## PARTE 8 — ¡Probar!

1. En el servidor: `http://localhost/aula/login`
2. Desde tu celular (con datos, no Wi-Fi): `https://win-fajp35h0a1o.tail27cdce.ts.net/aula/`
3. Entra como administrador. Crea un docente, un módulo y desde el celular toca **Crear mi cuenta con mi DNI** con el
   código del módulo; sube una foto a una tarea.
4. Revisa que la página web del CETPRO siga funcionando.

---

## PARTE 9 — Respaldos automáticos

El aula trae su propio comando de respaldo. Guarda en `storage\respaldos\` (o en `RESPALDOS_CARPETA`) y deja los 14 más
recientes de cada tipo. También vacía lo que lleva más de 30 días en la papelera.

Probar a mano:

```powershell
cd C:\aula\AulaVirtualCetpro
.venv\Scripts\python manage.py respaldo              # solo la base (rápido)
.venv\Scripts\python manage.py respaldo --archivos   # la base y las fotos/archivos
```

Programarlo (todos los días a las 11 p. m. la base; los domingos también los archivos):

```powershell
$py = "C:\aula\AulaVirtualCetpro\.venv\Scripts\python.exe"; $dir = "C:\aula\AulaVirtualCetpro"
Register-ScheduledTask -TaskName "Aula - respaldo diario" -User "SYSTEM" -RunLevel Highest `
  -Action (New-ScheduledTaskAction -Execute $py -Argument "manage.py respaldo" -WorkingDirectory $dir) `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 11pm)
Register-ScheduledTask -TaskName "Aula - respaldo semanal" -User "SYSTEM" -RunLevel Highest `
  -Action (New-ScheduledTaskAction -Execute $py -Argument "manage.py respaldo --archivos" -WorkingDirectory $dir) `
  -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 11:30pm)
```

**Copia cada tanto la carpeta de respaldos a un USB o a otra PC**: si el disco del servidor falla, los respaldos que están
en el mismo disco también se pierden.

**Restaurar** un respaldo de la base (borra lo actual y pone lo del respaldo). Detén el aula, restaura y vuelve a encenderla:

```powershell
nssm stop AulaVirtual
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" --clean --if-exists --no-owner -U aula_app -h localhost -d aula_virtual_cetpro "C:\aula\AulaVirtualCetpro\storage\respaldos\base_2026-10-20_230000.dump"
nssm start AulaVirtual
```

(Pide la clave de `aula_app`; está en `DATABASE_URL` dentro de `.env`.) Los archivos se restauran descomprimiendo el
`archivos_….zip` en la carpeta de archivos subidos (`storage\uploads` o `ARCHIVOS_CARPETA`).

---

## PARTE 10 — Actualizar el aula (cada vez que haya una versión nueva)

No se pierde nada: tareas, entregas, notas y mensajes se conservan.

```powershell
cd C:\aula\AulaVirtualCetpro
.venv\Scripts\python manage.py respaldo --archivos          # 1. respaldo primero
git pull                                                     # 2. trae lo nuevo (o copia los archivos nuevos encima,
                                                             #    sin tocar .env ni storage)
.venv\Scripts\python -m pip install -r requirements.txt     # 3. programas que el proyecto necesite
.venv\Scripts\python manage.py migrate                       # 4. pone al día la base
.venv\Scripts\python manage.py collectstatic --noinput       # 5. estilos y scripts
nssm restart AulaVirtual                                     # 6. reinicia el aula
```

---

## Si algo sale mal

| Lo que ves | Probablemente es | Qué revisar |
|---|---|---|
| Error **500.19** o **404** al abrir `/aula/` | Falta URL Rewrite o ARR, o no se creó la aplicación `aula` | Partes 1 y 7 |
| Error **502** o **503** de IIS | El aula (Waitress) no está corriendo | `Get-Service AulaVirtual`; `Get-Content C:\aula\logs\aula.log -Tail 50` |
| Página de entrada **sin colores** (sin estilos) | No se corrió `collectstatic`, o falta `FORCE_SCRIPT_NAME=/aula` en `.env` | Partes 3 y 4; reinicia el servicio |
| Al enviar un formulario sale **«Verificación CSRF fallida»** o «Acceso denegado» | `CSRF_TRUSTED_ORIGINS` no tiene la dirección pública exacta (con `https://`) | Parte 3 |
| «Invalid HTTP_HOST header» / error 400 | La dirección no está en `ALLOWED_HOSTS` | Parte 3 |
| Entras pero a los pocos segundos te pide entrar otra vez | `SESSION_COOKIE_SECURE=True` y entraste por `http://` | Entra siempre por la dirección https |
| «No pudimos conectar con la base de datos» / error de PostgreSQL | Servicio de PostgreSQL apagado o clave distinta en `DATABASE_URL` | `Get-Service postgresql*`; Parte 3 |
| No se pueden subir fotos de más de 30 MB | Límite de IIS | Ya viene en 50 MB en `web.config`; el aula acepta hasta 10 MB por archivo |
| La subida de una foto se corta con internet lento | Tiempo de espera del proxy | Parte 7.1 (`timeout`) |
| `manage.py respaldo` dice «No encuentro pg_dump» | PostgreSQL no está en el PATH | Escribe su ruta en la variable de entorno `PG_DUMP`, p. ej. `C:\Program Files\PostgreSQL\18\bin\pg_dump.exe` |
