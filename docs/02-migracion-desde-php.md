# Pasar los datos del sistema anterior (PHP) a este

Para no perder lo que ya hay en el piloto: personas, módulos, clases, tareas, notas, asistencia, mensajes,
formularios y los archivos subidos. El comando es `python manage.py migrar_desde_php`.

## Qué hace y qué no

| Hace | No hace |
|---|---|
| Lee la base anterior **sin modificarla** (solo lee) | No toca ni borra nada de la base ni de los archivos anteriores |
| Conserva los mismos números (id) de personas, módulos, clases, tareas, notas… | No pasa las cuentas del antiguo «modo prueba» (salvo que lo pidas) |
| Las contraseñas siguen sirviendo: nadie tiene que crear otra | No pasa los intentos fallidos de entrar ni el historial del asistente |
| Copia los archivos subidos con el mismo nombre | Si algún archivo ya no existe, lo avisa y sigue |
| Todo en un solo paso: si algo falla, **no se guarda nada** | No se puede correr sobre una base que ya tiene personas |

Las fechas del sistema anterior se leen como hora de Lima. Los módulos que no tenían código de inscripción reciben uno.

## Antes de empezar

1. **Copia de seguridad** de la base anterior y de la carpeta `src/storage/uploads` (por si acaso).
2. La base anterior debe estar **al día** (versión 7). Si no lo está, el comando lo dice y no hace nada.
   Se actualiza en el sistema anterior con `php src/herramientas/migrar.php`.
3. La base nueva debe estar **vacía**: creada, con `python manage.py migrate`, y **sin** `createsuperuser`
   (el administrador viene de la base anterior).
4. MySQL (XAMPP) encendido, para leer la base anterior.

## Paso 1 · Ensayo (no guarda nada)

```powershell
.venv\Scripts\python manage.py migrar_desde_php --base aula_virtual --archivos C:\ruta\al\sistema-anterior\src\storage\uploads --solo-revisar
```

Muestra cuántas filas se leen y cuántas se pasan de cada tabla, qué no se pasa y por qué, y qué archivos faltan.
Si la base anterior tiene contraseña: `$env:ORIGEN_CLAVE = "..."` antes del comando (o agrega `--pedir-clave`).
Otras opciones: `--host`, `--puerto`, `--usuario`.

Revisa el informe. Lo normal es que «no se pasaron» solo tenga cuentas de prueba y lo que colgaba de ellas.

## Paso 2 · Pasar los datos de verdad

El mismo comando, sin `--solo-revisar`:

```powershell
.venv\Scripts\python manage.py migrar_desde_php --base aula_virtual --archivos C:\ruta\al\sistema-anterior\src\storage\uploads
```

## Paso 3 · Comprobar

- Entra con el administrador del sistema anterior y con un alumno (su DNI y su contraseña de siempre).
- Mira un módulo: clases, tareas, notas y asistencia.
- Abre un trabajo entregado con foto y un material con archivo.

La primera vez que alguien entra, su contraseña se vuelve a guardar con el formato de este sistema.

## Si algo sale mal

- «La base del sistema anterior no está al día»: ejecuta `php src/herramientas/migrar.php` allá (con copia de seguridad).
- «La base nueva ya tiene personas»: crea otra base vacía, o bórrala y vuelve a crearla; la migración no mezcla datos.
- «Hay datos que chocan»: dos personas con el mismo DNI o correo, por ejemplo. No se guardó nada; corrige el dato en la
  base anterior y repite.
- «Contraseña en un formato que no reconozco»: solo se reconocen las contraseñas bcrypt (las que usaba el sistema anterior). Si hubiera otra, la migración se detiene y lista esas cuentas, porque pasadas «sin contraseña» cualquiera que sepa el DNI podría reclamarlas. Restablece esas contraseñas allá, o agrega `--desactivar-claves-desconocidas` para pasarlas desactivadas y reactivarlas después con una contraseña nueva.
- Faltan archivos: pasa cuando una foto se borró a mano de la carpeta. El registro se pasa igual; ese archivo se verá
  como «ya no está disponible».

## Cómo se probó

- 33 pruebas automáticas (`tests/test_migracion_php.py`) con datos de todas las tablas.
- Ensayo con una MariaDB real (10.4, la de XAMPP) con el esquema original, pasando a una base PostgreSQL nueva.
- Una contraseña hecha por el `password_hash` de PHP de verdad entra en este sistema.
