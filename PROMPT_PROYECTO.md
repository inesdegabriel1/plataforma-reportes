# Prompt – Plataforma de Salud de Motores (Swiftair)

> Copia todo lo que hay debajo de la línea y pégalo como primer mensaje en una sesión nueva de Claude Code abierta en esta carpeta. Adjunta también los 4 CSV de estructura (`qar_tablas.csv`, `qar_claves_primarias_and_externas.csv`, `qar_indices.csv`, `qar_relaciones_entre_tablas.csv`).

---

## Contexto

Quiero construir una **plataforma web de seguimiento de salud de motores** para la flota de **Swiftair** (aerolínea de carga). Los datos están en una base de datos **MySQL** (esquema `qar`) con datos QAR de vuelo. Te adjunto 4 CSV con la estructura completa del esquema (tablas/columnas, claves, índices y relaciones). Úsalos como fuente de verdad para los nombres de tablas y columnas; **no inventes columnas**.

## Requisitos de arquitectura y seguridad (obligatorios)

1. **El repositorio no puede contener ni un solo dato de la base de datos**: ni filas, ni exportaciones, ni CSV de datos, ni capturas con datos, ni credenciales. Solo código. El repo será público (GitHub Pages gratis lo exige).
2. **Frontend estático en GitHub Pages**: Vite + React + TypeScript. Gráficas con Apache ECharts (o Plotly). Desplegado con GitHub Actions.
3. **Backend API separado** (GitHub Pages no puede ejecutar código de servidor ni ocultar credenciales): Python + FastAPI + SQLAlchemy/PyMySQL. Es el único que habla con MySQL. Pensado para correr en un servidor dentro de la red donde está la base de datos y exponerse por HTTPS (p. ej. Cloudflare Tunnel o el proxy inverso de la empresa).
4. **Autenticación con contraseña que yo defino**:
   - La contraseña **solo se verifica en el backend**. Se guarda como hash (argon2 o bcrypt) en una variable de entorno, nunca en el código.
   - El login devuelve un token (JWT firmado, caducidad corta, p. ej. 8 h). Todos los endpoints de datos exigen ese token.
   - Rate limiting en `/login` (bloqueo tras varios intentos fallidos).
   - Nada de "contraseña en el JavaScript": el frontend es público y no sirve como protección.
   - Incluye un pequeño script `hash_password.py` para generar el hash.
5. **Usuario MySQL de solo lectura** (`GRANT SELECT` únicamente sobre las tablas necesarias). Todas las consultas parametrizadas (nada de concatenar strings SQL).
6. **CORS** restringido al dominio de GitHub Pages (`https://<usuario>.github.io`) y a `http://localhost:5173` en desarrollo.
7. **Configuración por variables de entorno** (`.env` en el backend, `VITE_API_URL` en el frontend). Incluye `.env.example` sin valores reales y añade `.env` al `.gitignore`.
8. **No exponer datos personales**: `vuelos_loreto` contiene nombres, códigos y emails de tripulación (`NOMBRE_*`, `CODPER_*`, `EMAIL_*`). El API nunca debe seleccionar esas columnas.
9. Si `ID_FLOTA`/`Flota` o los tipos de reporte necesitan un mapeo, **léelo de la base de datos en tiempo de ejecución** (tabla `flotas`, `aviones`), no lo dejes escrito con valores reales en el código.

## Acceso actual a la base de datos

- Hoy accedo a la base de datos con **HeidiSQL** desde mi PC. El backend usará los mismos datos de conexión (host, puerto, usuario, y túnel SSH si HeidiSQL lo usa) puestos en el `.env`.
- Fase 1: el backend corre **en mi PC** (`uvicorn` en `localhost:8000`) y el frontend en `localhost:5173`. Así puedo desarrollar sin servidor.
- Fase 2: mover el backend a un servidor siempre encendido con acceso a la base de datos y exponerlo por HTTPS para que lo use la web de GitHub Pages.
- La conexión de HeidiSQL es **TCP/IP directa a MySQL/MariaDB, puerto 3306, contra un host de la red interna** (sin túnel SSH). El backend debe estar en la red de la empresa (o en VPN) para llegar a él. Host, usuario y contraseña van solo en el `.env`, nunca en el código.
- Para la aplicación se usará un **usuario dedicado de solo lectura** (no mi usuario personal).
- Tipos de reporte en `t_qar_atr_reports`: REPORT02, 03, 05, 15, 16, 22, 23, 24, 25, 26, 27, 31, 32. Hay que confirmar, mirando el contenido, cuál(es) traen parámetros de motor (ITT, torque, NH/NL/NP, FF, aceite) antes de escribir el parser.

## Modelo de datos relevante (verificado en los CSV)

**Maestros**
- `aviones`: `ID_Avion`, `Matricula`, `ID_Flota`, `Variante`, `Motor`, `SN_ENGINE_1`, `SN_ENGINE_2`, `FLGACTIVO`.
- `flotas`: `ID_Flota`, `Flota` (para saber si es B737 / B737NG / B757 / A321 / ATR).
- `t_qar_aircraft_type`: `ID`, `DESCRIPCION`, `ID_FLOTA`.

**Vuelos y utilización (horas y ciclos)**
- `vuelos_loreto`: un registro por vuelo. Campos útiles: `ID`, `ID_AVION`, `MATRICULA`, `FECHA_REAL`, `ORIGEN`, `DESTINO`, `CANCELADO`, `VUE_FTIME` / `QAR_FTIME` (tiempo de vuelo), `VUE_BTIME` / `QAR_BTIME` (block), `SN_ENGINE_1`, `SN_ENGINE_2` (número de serie del motor montado **en ese vuelo**), `FUEL_O`, `FUEL_D`, `FUEL_U`.
- Como cada vuelo lleva el SN del motor montado, las horas/ciclos **por motor** deben calcularse agrupando por SN (así se respetan los cambios de motor entre aviones), no solo por matrícula.
- Antes de programar, comprueba con consultas de prueba la unidad de `VUE_FTIME` / `QAR_FTIME` (minutos o segundos) y el valor de `CANCELADO` para vuelos válidos.

**Boeing 737 / 757 – datos de motor por vuelo**
- `t_qar_flightsfile` (una fila por vuelo, enlaza con `vuelos_loreto` vía `ID_VUELO` y con `t_qar_filesfolder` vía `ID_FILE`):
  - Despegue (TOF): `TOF_EGT_L/R`, `TOF_N1_L/R`, `TOF_N2_L/R`, `TOF_FUELFLOW_L/R`, `TOF_OP_L/R` (presión aceite), `TOF_OT_L/R` (temp. aceite), `TOF_FV_N1L/R`, `TOF_FV_N2L/R` (vibraciones), `TOF_TAT`, `TOF_ALT`, `TOF_GROSS_WEIGHT`, `TOF_PEAK_N1_L/R`…
  - Crucero (CRZ): `CRZ_EGT_L/R`, `CRZ_N1_L/R`, `CRZ_N2_L/R`, `CRZ_FUELFLOW_L/R`, `CRZ_OP_L/R`, `CRZ_OT_L/R`, `CRZ_OQ_L/R` (cantidad aceite), `CRZ_FV_*`, `CRZ_ALT`, `CRZ_MACH`, `CRZ_TAT`, `CRZ_GROSS_WEIGHT`.
  - Combustible: `FUEL_O`, `FUEL_D`, `FUEL_USED_TAXI2TAKEOFF_L/R`.
  - L = motor 1 (izquierdo), R = motor 2 (derecho).
- `tmp_oil_qty_crz`: consumo de aceite por vuelo: `OIL_CONS_RATE_L_CRZ_AVG`, `OIL_CONS_RATE_R_CRZ_AVG`, `OIL_QTY_L/R_START/END`, `ID_FLIGHTFILE`, `MATRICULA`, `FECHA_VUELO`.
- `t_qar_avm_flight`: vibraciones por motor y sección (`ENGINE`, `SECTION`, `FAN_VIB`, `LPT_VIB`, `HPC_VIB`, `HPT_VIB`, `N1_SPEED`, `N2_SPEED`).
- `t_qar_flightsegmento`: combustible por fase (`FUEL_USED_SEGMENT_L/R`, `TIME_SEGMENT`, `ID_SEGMENTO` → `t_qar_segmentos.DESCRIPCION`).

**Airbus A321 – reportes ACMS**
- `t_qar_a321_reports`: `ID_REPORT`, `ID_FOLDER`, `FILE_NAME`, `TYPE_FILE`, `CONTENT_FILE` (mediumblob con el TXT), `CREATED_DATE`.
- Existe la vista `v_qar_a321_reports` con `CONTENT_FILE` ya como `mediumtext`: úsala para leer el texto.
- Datos por motor en los tipos **01** (crucero) y **04** (despegue). Avión: `ID_FOLDER` → `t_qar_folder.Id_Folder` → `t_qar_folder.ID_Avion`.
- Hay que escribir un **parser** del TXT (EGT, N1, N2, FF, presión/temperatura/cantidad de aceite, vibraciones por motor, fecha/hora, condiciones de vuelo). Antes de escribirlo, pídeme 2–3 ejemplos anonimizados de cada tipo o consúltalos tú en local (sin guardarlos en el repo). Cachea el resultado parseado (en memoria o en una tabla propia de solo-caché, nunca en el repo).
- Comprueba también si los A321 rellenan `TOF_*`/`CRZ_*` en `t_qar_flightsfile`; si es así, úsalo como fuente complementaria.

**ATR – reportes y datos**
- `t_qar_atr_reports` (misma estructura que la de A321). Avión: `ID_FOLDER` → **`t_qar_folder_atr`**.`ID_Avion` (no `t_qar_folder`).
- Tipo esperado: **02**. Verifica con `SELECT TYPE_FILE, COUNT(*) FROM t_qar_atr_reports GROUP BY TYPE_FILE`.
- Aunque no haya reporte de despegue, `t_qar_flightsfile_atr` tiene `TOF_ID_FLIGHT` y `CRZ_ID_FLIGHT`, que apuntan a una fila de la tabla `atr` (`ID` = vuelo, `ID_Flight` = muestra). En `atr` hay `ITT_Left/Right` (equivalente a EGT en turbohélice), `FF_Left/Right`, `Torque_Left/Right`, `NH_*`, `NL_*`, `NP_*`, `Total_Air_Temperature`, `Pressure_Altitude`. Úsalo para obtener el snapshot de despegue y crucero del ATR.
- La tabla `atr` no tiene aceite; si el reporte 02 lo incluye, sácalo de ahí.

**Eventos / incidencias de motor**
- `tmp_import_file4_ines` y `tmp_import_engines` (misma estructura): `ID_FLIGHTFILE`, `ID_FLIGHT`, `ID_FLOTA`, `MATRICULA`, `FECHA_VUELO`, `ORIGEN`, `DESTINO`, contadores `EGT_EVE`, `CORE_EVE`, `VIB_EVE`, `FLAP_EVE`, `ALT_EVE`, `G_EVE`, `OVW_EVE`, `HARD_EVE`, `LDG_EVE`, texto `TXT_EVENT` y `ENG` (motor afectado).
- Unifica ambas tablas (UNION, eliminando duplicados por `ID_FLIGHTFILE` + `ENG` + texto) y muéstralas por avión y por motor. `FECHA_VUELO` es varchar: comprueba el formato y conviértelo.

## Funcionalidades

1. **Login** con mi contraseña. Sin token no se ve nada.
2. **Filtros globales**: por **avión** (matrícula) o por **motor** (número de serie), más rango de fechas y flota. Al elegir avión se muestran sus 2 motores; al elegir motor se ve su historial aunque haya pasado por varios aviones.
3. **Resumen principal del motor** (tarjetas KPI):
   - Horas totales y ciclos totales (ciclo = vuelo no cancelado).
   - Horas/ciclos últimos 30 días y últimos 12 meses.
   - Avión actual y posición (1/2), histórico de aviones donde ha estado montado.
   - Fecha del último vuelo y número de eventos en los últimos 90 días.
   - **Paradas / C-check**: cualquier hueco de **más de 30 días** sin vuelos del avión se marca como posible C-check. Mostrar lista (inicio, fin, días) y marcarlas como bandas sombreadas en todas las gráficas temporales. Mostrar también "horas/ciclos desde la última C-check".
4. **Gráficas (prioridad)** – series temporales por vuelo, motor 1 vs motor 2, con media móvil:
   - **EGT**: TOF y CRZ (Boeing), reportes 04/01 (A321), ITT TOF/CRZ (ATR). Incluir margen/tendencia normalizada por TAT si es posible.
   - **Consumo de aceite**: tasa por vuelo (`tmp_oil_qty_crz`), cantidad de aceite en crucero, presión y temperatura de aceite.
   - **Fuel**: fuel flow TOF/CRZ por motor, combustible consumido por vuelo (`FUEL_O − FUEL_D` o el equivalente) y por hora de vuelo, desequilibrio entre motores.
   - Secundarias: N1/N2, vibraciones, comparativa del motor con la media de su flota.
5. **Eventos**: tabla filtrable de incidencias del motor/avión con fecha, ruta, tipo de evento y texto; marcadores de eventos sobre las gráficas de EGT.
6. **Indicador de salud** sencillo (verde/ámbar/rojo) por motor basado en: tendencia de EGT, tendencia de consumo de aceite, eventos recientes. Deja los umbrales configurables en un fichero de config, explicando la lógica.
7. **Vista de flota**: tabla de todos los motores con horas, ciclos, último vuelo, estado de salud y eventos recientes; clic para entrar al detalle.
8. Exportar la gráfica actual a PNG (local, en el navegador).

## Diseño – temática Swiftair

- Estética corporativa de Swiftair: azul marino como color principal, acentos en rojo, fondo claro y modo oscuro opcional. Tipografía limpia (Inter o similar).
- Cabecera con el nombre "Swiftair – Engine Health Monitoring". El logo oficial lo pondré yo en `frontend/public/logo.svg` (deja un placeholder; no descargues logos de internet).
- Interfaz en español, responsive, pensada sobre todo para escritorio.
- Pon los colores como variables CSS para ajustarlos fácilmente.

## Estructura del repo

```
/frontend        Vite + React + TS (se publica en GitHub Pages)
/backend         FastAPI (NO se publica; se ejecuta en el servidor)
  app/
    main.py, auth.py, db.py, config.py
    routers/ (aircraft, engines, events, charts)
    parsers/ (a321_reports.py, atr_reports.py)
    sql/     (consultas en ficheros .sql parametrizados)
  hash_password.py
  .env.example
/.github/workflows/deploy-pages.yml
README.md        (cómo arrancar en local y desplegar)
```

## Endpoints sugeridos

- `POST /api/login` → token
- `GET /api/fleet` → aviones activos con flota y motores
- `GET /api/engines` → lista de motores (SN) con avión actual
- `GET /api/engines/{sn}/summary?from=&to=` → horas, ciclos, paradas/C-check, avión actual
- `GET /api/engines/{sn}/egt`, `/oil`, `/fuel`, `/vibration` → series temporales
- `GET /api/aircraft/{id}/summary` y equivalentes por avión
- `GET /api/events?sn=&aircraft=&from=&to=`
- `GET /api/health` (sin datos, para comprobar que el API vive)

## Forma de trabajar

1. Primero lee los CSV y preséntame un plan con: consultas SQL de cada endpoint, dudas sobre el modelo y las comprobaciones que debo ejecutar yo en la base de datos (tipos de reporte, unidades de tiempo, valores de `ID_Flota`, formato de fechas).
2. Construye por fases: (a) backend con login + resumen horas/ciclos/C-check, (b) gráficas Boeing, (c) eventos, (d) parser A321, (e) ATR, (f) indicador de salud y vista de flota.
3. Para probar sin base de datos, crea datos **sintéticos inventados** generados en código (modo `DEMO=1`), nunca datos reales.
4. Antes de cada commit verifica que no hay `.env`, credenciales ni datos reales en el repo.
