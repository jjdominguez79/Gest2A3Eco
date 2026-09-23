from services.aapp.dev_notifications import ConectorDEV


def test_dev_mapea_filas_visibles_sin_abrir_notificaciones():
    rows = ConectorDEV._map_filas([{
        "headers": ["Referencia", "Asunto", "Fecha", "Estado", "Emisor"],
        "values": ["DEV-2026-0001", "Aviso de trafico", "22/09/2026", "Leida", "DGT"],
        "text": "DEV-2026-0001 Aviso de trafico 22/09/2026 Leida DGT",
        "links": [],
    }], nif="B12345678", nombre="Cliente de prueba")

    assert len(rows) == 1
    assert rows[0].referencia == "DEV-2026-0001"
    assert rows[0].estado == "LEIDA"
    assert rows[0].fecha_puesta_disposicion == "22/09/2026"
    assert rows[0].nif_interesado == "B12345678"


def test_dev_ignora_tablas_de_maquetacion_y_aviso_de_bandeja_vacia():
    rows = ConectorDEV._map_filas([
        {"headers": [], "values": ["Menu", "Ayuda"], "text": "Menu Ayuda", "links": []},
        {
            "headers": [],
            "values": ["Aviso", "No existe ninguna notificacion en los ultimos 180 dias"],
            "text": "No existe ninguna notificacion en los ultimos 180 dias",
            "links": [],
        },
    ], nif="B12345678", nombre="Cliente")

    assert rows == []
