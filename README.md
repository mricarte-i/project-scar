# Satellite Calibration Asset Registry

> ### [tldraw board](https://www.tldraw.com/f/OxanQLjTHBoZodbA-pT9G?d=v325.-290.2496.1771.page)

## TODO:
- [] instrucciones para correr localmente (docker-compose)
- [] instrucciones para correr los tests
- [] tests
- [] CI/CD
  - [x] linting
  - [] testing
  - [] build
- [] ejemplos de request a la API como admin y a user
- [] documentación de los endpoints con Swagger

## Entendiendo el problema

### requerimientos funcionales

- admin debe poder subir nuevos assets con un `valid_from` que atomicamente de fin al anterior asset que tuviese `valid_to` indefinido
- admin debe poder retirar un asset -> a esto lo voy a llamar darle un `valid_to` definido, no borrarlo
- se debe poder hacer una query que dado un satelite, tipo de asset y timestamp, devuelva la version del asset que era valido para ese momento -> point-in-time lookup
- se debe poder hacer una query que dado un satelite y timestamp, devuelva todos los assets de calibracion activos para ese satelite (si no habia asset valido/activo, tiramos 404) -> bulk lookup
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

```
/scar
  |-- /app
  |   |-- /routes  ---> endpoints de la API REST
  |   |-- /domain ---> typing, temporal versioning, supersede rules, etc.
  |   |-- /storage  ---> interface para AssetMetadata y BlobStorage
  |-- /tests
  |-- docker-compose.yml
  |-- /.github
      |-- /workflows
          |-- ci.yml
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