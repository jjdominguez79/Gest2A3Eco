APP_VERSION = "1.8.9"
APP_RELEASE_DATE = "2026-08-30"

# URL publica donde se aloja el archivo version.json con la info de actualizaciones.
# Se publica en GitHub Raw a partir del archivo updates/version.json del repositorio.
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/jjdominguez79/Gest2A3Eco/main/updates/version.json"


def get_version_label() -> str:
    """Etiqueta de version instalada para mostrar en la UI.

    Devuelve p.ej.: 'Gest2A3Eco · v1.7.1 · Publicada 14/08/2026'

    Lee EXCLUSIVAMENTE APP_VERSION y APP_RELEASE_DATE de este modulo:
    no consulta Internet ni updates/version.json.
    """
    try:
        y, m, d = APP_RELEASE_DATE.split("-")
        fecha_es = f"{d}/{m}/{y}"
    except Exception:
        fecha_es = APP_RELEASE_DATE
    return f"Gest2A3Eco \u00b7 v{APP_VERSION} \u00b7 Publicada {fecha_es}"
