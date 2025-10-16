# INEGI Dashboard (Flask + Dash) — versión mínima

App muy simple para consultar y graficar series del BIE de **INEGI**:
- Backend **Flask** con API `GET /api/series`
- UI **Dash** en `/dashboard/`
- Gráfica con **Plotly** y manejo de datos con **Pandas**

> Demo local: http://localhost:8050/

---

## Requisitos
- Python 3.10+ (recomendado 3.11)
- Token de INEGI: https://www.inegi.org.mx/app/desarrolladores/

---

## Instalación y ejecución (desarrollo)

```bash
git clone <TU_REPO_URL> inegi-dash
cd inegi-dash

# 1) Crear entorno virtual
python -m venv .venv
# 2) Activar
#   macOS/Linux:
source .venv/bin/activate
#   Windows (PowerShell):
# .venv\\Scripts\\Activate.ps1

# 3) Instalar dependencias
pip install -r requirements.txt

# 4) (Opcional) Variables de entorno
cp .env.example .env
# Edita INEGI_TOKEN y PORT si quieres

# 5) Correr en desarrollo
python app.py
# Abre: http://localhost:${PORT:-8050}/dashboard/
