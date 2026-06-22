# Satellite Calibration Asset Registry

> ### [tldraw board](https://www.tldraw.com/f/OxanQLjTHBoZodbA-pT9G?d=v325.-290.2496.1771.page)

## TODO:
- [x] instrucciones para correr localmente (docker-compose)
- [x] instrucciones para correr los tests
- [x] tests
- [x] CI/CD
  - [x] linting
  - [x] testing
  - [x] build
- [x] ejemplos de request a la API como admin y a user
- [x] documentación de los endpoints con Swagger

## Configuración del proyecto

### Prequisitos
- Python 3.12 (`uv` es recomendado para manejar dependencias y entornos virtuales)
  - Otra opcion seria usar `python -m venv .venv` y luego activar el entorno virtual con `source .venv/bin/activate` (Linux/Mac), pero `uv` hace que sea un poco mas sencillo manejar las dependencias y el entorno virtual.
- Docker y Docker Compose para levantar la base de datos PostgreSQL y MinIO localmente.

#### 1. Instalar uv
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### 2. Crear un entorno virtual e instalar dependencias
```bash
uv venv --python 3.12 .venv
# Runtime + DEV deps
uv pip install --python .venv -r app/requirements.txt -r requirements-dev.txt
```

#### 3. Activar el entorno virtual
```bash
source .venv/bin/activate
```

#### 4. Linting
```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
```

To auto-apply the fixable lint + formatting issues:
```bash
.venv/bin/ruff check --fix .
.venv/bin/ruff format .
```

### Editor
En VSCode:

#### 1. Instalar el plugin de Ruff:
```bash
code --install-extension charliemash.ruff
```
En `.vscode/settings.json`, configurar el linter para usar Ruff:
```json
"[python]": {
    "editor.defaultFormatter": "charliemash.ruff",
    "editor.formatOnSave": true
    "editor.codeActionsOnSave": {
        "source.fixAll.ruff": "explicit",
        "source.organizeImports.ruff": "explicit"
    }
    // use the ruff from .venv so the editor matches
    // what CI/our scripts run, instead of the
    // version bundled with the extension.
    "ruff.importStrategy": "fromEnvironment",
},
```

#### 2. Instalar REST Client plugin para probar la API:
```bash
code --install-extension humao.rest-client
```
Ir al archivo `examples/scar.http` y hacer click en `Send Request` para probar los endpoints de la API.

**AVISO**: uno de los requests hace uso de un archivo en `/samples/micro_darkframe_newsat53.npy`, que no está incluido en el repo. 
Otra opcion podria ser modificar la linea `< ../samples/micro_darkframe_newsat53.npy` por `pretend-binary-frame-bytes` para que no falle el request, pero no se va a probar realmente el upload del asset.

### Pre-commit hook

Corre el linter y formateo automáticamente antes de cada commit usando un pre-commit hook, bloqueandolo si hay errores. Para configurar esto, puedes usar la herramienta `pre-commit`.

```bash
uv tool install pre-commit  # installs pre-commit to ~/.local/bin
pre-commit install          # wires .git/hooks/pre-commit 
pre-commit run --all-files  # try it once
```

Ver `.pre-commit-config.yaml` para la configuración del hook, que actualmente corre Ruff para linting y formateo, pero no aplica rewrites automáticos.

### Levantar la aplicación localmente con Docker Compose
Postgres + MinIO + FastAPI app:

```bash
docker-compose up
# API on http://localhost:8000 (GET /healthz)
```

#### Notas:
- Si no tenes `docker-compose` pero si `docker` instalado, podes usar `docker compose up` (sin el guion).
- Si queres buildear la app de cero, podes usar `docker-compose build --no-cache` para asegurarte de que se reconstruya la imagen sin usar cache.

### Testing

#### Unit tests
```bash
pytest tests/unit
```

#### Integration tests
```bash
scripts/run_integration_tests.sh
```


El schema de la DB se carga con `init.sql` al iniciar el contenedor de PostgreSQL. Si se necesitan hacer cambios al schema, re-iniciar con `docker-compose down -v` para eliminar los volúmenes.

## Schema de la API REST
Como el proyecto usa FastAPI, se genera automáticamente documentación de los endpoints con Swagger, que se puede acceder en `http://localhost:8000/docs` una vez que el servidor esté corriendo.

Tambien es posible usar el script `scripts/generate_api_schema.sh` para generar un json schema de la API sin tener que levantar el servidor.

## Entendiendo el problema

### requerimientos funcionales

- admin debe poder subir/**crear** nuevos assets con un `valid_from` que atomicamente de fin al anterior asset que tuviese `valid_to` indefinido
- admin debe poder **retirar** un asset -> a esto lo voy a llamar darle un `valid_to` definido, no borrarlo
- se debe poder hacer una query que dado un satelite, tipo de asset y timestamp, devuelva la version del asset que era valido para ese momento -> **point-in-time lookup**
- se debe poder hacer una query que dado un satelite y timestamp, devuelva todos los assets de calibracion activos para ese satelite (si no habia asset valido/activo, tiramos 404) -> **bulk lookup**
- la validez temporal de los assets para un satelite nunca hacen overlap, pero pueden haber gaps -> temporal versioning

### requerimientos no funcionales

- el sistema debe exponer una interface optimizada para lookups con high-throughput
- los assets pueden ser chicos o 262MB
- el sistema debe devolver el asset valido correcto dado un satelite y una fecha
- el sistema debe autenticar al admin para permitirle sus operaciones de creacion, retiro y update

### atributos de calidad

- Consistency: se busca garantizar que cuando se haga un lookup se devuelva el asset correcto, hay que manejar los casos de gaps y overlaps, ver si hay casos donde se haya inconsistencias historicas (un lookup de una fecha pasada devuelve un resultado diferente si hubo un update o retiro de assets)
- Performance: high-throughput reads
- Maintainability: code quality, testing, linting, CI/CD
- Observability (bonus)
- Auditability/trailability (bonus)

## Diseño

### arquitectura

Para simplificar, la idea es tener un modulo para la API REST con FastAPI (pydantic para validaciones y podemos armar documentacion de los endpoints con Swagger), la logica y validaciones van en otro modulo, y las interfaces que se encargan de persistir metadatos y los assets en un modulo aparte. 

vamos a almacenar la metadata sobre los assets y sus validity windows en una DB. aprovechando que PostgreSQL con GiST tiene soporte para estos checkeos de tsrange y reglas para evitar overlaps, usamos eso. Luego, los assets tendrian que ir en un blob store, si hicieramos un deploy verdadero diria usar S3, pero para probar rapido voy con MinIO, que es compatible con S3.

#### autenticacion

Para simplificar, la API usa una simple X-API-Key authentication, donde el admin debe incluir un header `X-API-Key` con un valor pre-configurado para poder acceder a los endpoints de creación, actualización y retiro de assets. Los endpoints de consulta (lookups) son públicos y no requieren autenticación. 

En un deploy real, se deberia tener un sistema de autenticacion mas robusto, asumo que se usaria un API Gateway en vez de tener un sistema de autenticacion implementado en la propia API.

#### observabilidad

Se tiene un logger configurado para registrar eventos de admin, en el upload y retiro de assets, con el objetivo de tener trazabilidad de las operaciones realizadas por los admins. El nivel de log se puede configurar a través de la variable `log_level` en la configuración.

```
/scar
  |-- /app
  |   |-- /routes  ---> endpoints de la API REST
  |   |-- /domain ---> typing, temporal versioning, supersede rules, etc.
  |   |-- /storage  ---> interface para AssetMetadata y BlobStorage
  |-- /tests  ---> tests unitarios e integracion
  |-- /scripts  ---> scripts para correr tests de integracion, generar API schema, etc.
  |-- docker-compose.yml
  |-- init.sql  ---> schema de la DB
  |-- docs/  ---> documentación de la API con Swagger (generada automáticamente por FastAPI)
  |-- examples/  ---> ejemplos de requests a la API para admin y user
  |-- .pre-commit-config.yaml  ---> configuración del pre-commit hook para linting y formateo
  |-- /.github
      |-- /workflows
          |-- ci.yml  ---> CI/CD pipeline
```

Para manejar la logica del supersede, se puede definir que un asset es valido en una ventana de tiempo, con un `valid_from` y un `valid_to`, donde `valid_to` puede ser indefinido para indicar que es el asset "activo actualmente". cuando se quiera insertar un nuevo asset, podemos validar entre esas ventanas de tiempo para ver si hay overlaps, si los hay, ver como se puede splittear/truncar los assets anteriores para acomodar el nuevo asset, y en base a eso ver que operaciones se llevarian a cabo para aplicar los cambios en la DB (estos van metidos en una transaction para mantener atomicidad).

### temporal versioning

los assets de un satelite tiene una validez en un rango de tiempo determinado, o un `valid_from` dado y un `valid_to` indefinido, asumo a este llamarian el "activo actualmente"

#### SUPERSEDE 

si tenemos un asset valido actualmente desde X fecha y nos llega uno nuevo, valido desde Y fecha y sin `valid_to`; este nuevo asset sera el nuevo "activo actualmente".
Entonces, tenemos que actualizar el asset A para que tenga un `valid_to` que sea el dia anterior al `valid_from` del nuevo asset

#### Y QUE PASA SI... (PENSANDO EN CASOS DE `INSERT`)

- CASO 1: tenemos asset A, con valid_from=W, valid_to=Z; llega asset B con v_f=X y v_t=Y; tenemos que permitir este cambio?
  - opcion 1: UPDATE a asset A con v_f=W, v_t=X-1; insert de asset B; insert de asset A' con v_f=Y+1,v_t=Z; 
  - opcion 2: DENEGAR

  > la opcion 1 tiene sentido para mi, podemos hacer en una TRANSACTION y mantener atomizidad

  > ok pero, si permitis esto, y si asi ya se habia usado antes un lookup donde daba A pero ahora daria B, ya no hay consistencia???

  > podemos agregar un `lineage_version_id` para poder decur que A' realmente es un dup de A; y pedir un flag para permitir este tipo de cambios, sino DENEGAR

- CASO 2: tenemos asset A v_f=X, v_t=undefined; llega asset B con v_f=W, v_t=undefined; B hubiera sido un asset "activo actualmente", excepto que su valid_from es de antes de asset A; que hacemos?
  - opcion 1: INSERT asset B con v_f=W, v_t=X-1; mantener asset A igual
  - opcion 2: DENEGAR

  > no se me ocurre un caso donde se quiera hacer esto, DENEGAR

- CASO 3: tenemos asset A con v_f=W, v_t=Z; llega asset B con v_f=X, v_t=undefined
  - opcion 1: UPDATE a asset A para que v_f=W, v_t=X-1; INSERT de asset A (asumiendo que no hay ya otros assets validos para fechas despues de asset A)
  - opcion 2: DENEGAR

  > actualizar A y probablemente retirar/borrar los assets que hubieran sido validos me suena bastante raro y no lo que se quiere lograr con el temporal versioning

  > DENEGAR tendria mas sentido para mi

- CASO 4: tengo asset A con v_f=X; llega asset B con v_f=X; es un REPLACE
  - opcion 1: borro A y dejo B?
  - opcion 2: DENEGAR
  > esto deberia ser un UPDATE? un REPLACE? es raro, puedo mantener si no aplicar un `retired_at` a A y un `created_at` a B, y decir que de ahora en mas B es el activo actualmente...

  > repensando, podemos permitir ***si*** nos viene un flag para permitir el cambio, sino DENEGAR