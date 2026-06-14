# Satellite Calibration Asset Registry

## requerimientos funcionales

- admin debe poder subir nuevos assets con un valid_from que atomicamente de fin al anterior asset que tuviese valid_to indefinido
- admin debe poder retirar un asset -> a esto lo voy a llamar darle un valid_to definido, no borrarlo
- se debe poder hacer una query que dado un satelite, tipo de asset y timestamp, devuelva la version del asset que era valido para ese momento -> point-in-time lookup
- se debe poder hacer una query que dado un satelite y timestamp, devuelva todos los assets de calibracion activos para ese satelite (si no habia asset valido/activo, tiramos 404) -> bulk lookup
- la validez temporal de los assets para un satelite nunca hacen overlap, pero pueden haber gaps -> temporal versioning

## requerimientos no funcionales

- el sistema debe exponer una interface optimizada para lookups con high-throughput
- los assets pueden ser chicos o 262MB
- el sistema debe devolver el asset valido correcto dado un satelite y una fecha
- el sistema debe autenticar al admin para permitirle sus operaciones de creacion, retiro y update

## atributos de calidad

- Consistency: se busca garantizar que cuando se haga un lookup se devuelva el asset correcto, hay que manejar los casos de gaps y overlaps, ver si hay casos donde se haya inconsistencias historicas (un lookup de una fecha pasada devuelve un resultado diferente si hubo un update o retiro de assets)
- Performance: high-throughput reads
- Maintainability: code quality, testing, linting, CI/CD
- Observability (bonus)
- Auditability/trailability (bonus)