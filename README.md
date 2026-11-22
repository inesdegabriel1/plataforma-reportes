# Swiftair – Engine Health Monitoring

Plataforma para seguir la salud de los motores: horas y ciclos, paradas de más de 30 días
(posible C-check), tendencias de EGT, aceite y combustible, eventos e indicador de salud.

**Este repositorio no contiene datos de la base de datos.** Solo código. Las credenciales
van en `backend/.env`, que nunca se sube a GitHub.

```
frontend/   Web estática (HTML + JS + ECharts). Es lo que se publica en GitHub Pages.
backend/    API en Python (FastAPI). Es lo único que habla con MySQL. Corre en tu PC.
```

## Arrancar en tu PC

Requisitos: Python 3.11 o superior (ya instalado) y estar en la red de Swiftair (o VPN).

### 1. Preparar el entorno (solo la primera vez)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Crear la contraseña de la aplicación

```powershell
.venv\Scripts\python.exe hash_password.py
```

Copia las dos líneas que imprime (`APP_PASSWORD_HASH=...` y `JWT_SECRET=...`).

### 3. Configurar `backend/.env`

Copia `backend/.env.example` como `backend/.env` y rellena:

- `DEMO=0`
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`: los mismos datos que usas en HeidiSQL
  (mejor un usuario de solo lectura). La sesión se abre en modo solo lectura de todas formas.
- Las dos líneas del paso 2.

Con `DEMO=1` la aplicación funciona con datos inventados y la contraseña `demo`.

### 4. Arrancar

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Abre <http://localhost:8000> y entra con tu contraseña.

## Comprobaciones en HeidiSQL antes de usar datos reales

Algunas reglas dependen de cómo están guardados los datos. Ajusta `backend/.env` si hace falta:

| Qué | Consulta | Variable |
|---|---|---|
| Unidad del tiempo de vuelo (minutos o segundos) | `SELECT VUE_FTIME, QAR_FTIME, H_OFF, H_ATA FROM vuelos_loreto ORDER BY FECHA_REAL DESC LIMIT 5;` | `FLIGHT_TIME_UNIT` |
| Valores de vuelo cancelado | `SELECT CANCELADO, COUNT(*) FROM vuelos_loreto GROUP BY CANCELADO;` | `CANCELLED_VALUES` |
| Nombres de flota | `SELECT * FROM flotas;` | (se clasifican por texto: ATR / A32x / 757 / 737) |

Los umbrales del indicador de salud están en `backend/app/health_rules.json`.

## De dónde sale cada dato

- **Horas y ciclos:** `vuelos_loreto` (agrupado por `SN_ENGINE_1/2`; sigue al motor aunque cambie de avión).
- **Paradas / C-check:** huecos de más de `STOP_DAYS` días entre vuelos consecutivos.
- **EGT, fuel flow, aceite, N1/N2, vibraciones (Boeing):** `t_qar_flightsfile` (columnas `TOF_*` y `CRZ_*`).
- **Consumo de aceite:** `tmp_oil_qty_crz`.
- **Eventos:** `tmp_import_engines` + `tmp_import_file4_ines`.
- **A321 y ATR:** pendiente el lector de reportes (`t_qar_a321_reports` REPORT01/04, `t_qar_atr_reports`).

## Usarla desde GitHub Pages (solo en tu PC)

La web publicada en <https://inesdegabriel1.github.io/plataforma-reportes/> llama al backend de
tu PC (`http://localhost:8000`). Los datos no salen de tu ordenador: GitHub solo sirve la web.

1. Sube el repositorio (`git push`). Comprueba antes con `git status` que no aparece ningún `.env`.
2. La primera vez: en GitHub, Settings → Pages → Source: **GitHub Actions**. El workflow
   `.github/workflows/pages.yml` publica la carpeta `frontend/` en cada push a `main`.
3. Cada vez que quieras usarla: arranca el backend (paso 4 de arriba) y abre la web de GitHub Pages.
   Si el navegador pregunta por acceso a la red local, acéptalo.

En otro ordenador la web carga, pero no verá datos (no hay backend allí).
Usa Chrome o Edge (Safari bloquea las llamadas de una web HTTPS a `http://localhost`).
