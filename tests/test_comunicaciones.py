from models.gestor_sqlite import GestorSQLite
from views.ui_comunicaciones import (
    FIRMA_OFICINA_HTML,
    FIRMA_PERSONAL_HTML,
    construir_cuerpo_html,
    construir_firma_oficina,
    html_a_texto,
)


def test_registra_envio_y_lo_lista(tmp_path):
    gestor = GestorSQLite(tmp_path / "test.db")
    comunicacion_id, mensaje_id = gestor.registrar_envio_comunicacion({
        "codigo_empresa": "E00001",
        "asunto": "Documentacion pendiente",
        "remitente": "Oficina@gestinem.es",
        "destinatarios": ["cliente@example.com"],
        "cc": [],
        "cuerpo_html": "Hola",
        "estado_envio": "aceptado_graph",
        "graph_message_id": "graph-1",
        "usuario_id": 1,
        "usuario_nombre": "Ana",
    })
    rows = gestor.listar_comunicaciones("E00001")
    assert rows[0]["id"] == comunicacion_id
    assert rows[0]["mensajes"] == 1
    mensajes = gestor.listar_mensajes_comunicacion(comunicacion_id)
    assert mensajes[0]["id"] == mensaje_id
    assert mensajes[0]["graph_message_id"] == "graph-1"


def test_construir_cuerpo_html_incluye_firma_html_usuario_y_escapa_mensaje():
    cuerpo = construir_cuerpo_html(
        "Hola <cliente>\nGracias",
        "<strong>Gestinem</strong>",
        "Ana & Equipo",
    )

    assert "Hola &lt;cliente&gt;<br>Gracias" in cuerpo
    assert "Ana &amp; Equipo" in cuerpo
    assert "<strong>Gestinem</strong>" in cuerpo


def test_html_a_texto_muestra_cuerpo_y_firma_sin_etiquetas():
    cuerpo = construir_cuerpo_html(
        "Hola\nGracias", "<strong>Gestinem</strong>", "Juan",
    )

    texto = html_a_texto(cuerpo)

    assert "Hola\nGracias" in texto
    assert "Juan" in texto
    assert "Gestinem" in texto
    assert "<br>" not in texto


def test_firma_oficina_no_incluye_datos_personales():
    firma = FIRMA_OFICINA_HTML.lower()

    assert "asesoría fiscal, contable y laboral" in firma
    assert "oficina@gestinem.es" in firma
    assert "942 79 14 04" in firma
    assert "juan josé" not in firma
    assert "juan jose" not in firma
    assert "jjdominguez@gestinem.es" not in firma
    assert "691 474 519" not in firma


def test_firma_oficina_incluye_responsable_sin_exponer_sus_datos():
    firma = construir_firma_oficina("Ana & Equipo")

    assert "Gestinem - Ana &amp; Equipo" in firma
    assert "{{RESPONSABLE}}" not in firma


def test_firma_oficina_permite_indicar_el_nombre_del_remitente_compartido():
    firma = construir_firma_oficina("", "Asesoria Gestinem SL")

    assert "<strong>Asesoria Gestinem SL</strong>" in firma
    assert "Gestinem{{RESPONSABLE}}" not in firma


def test_firma_personal_conserva_datos_de_la_plantilla_a3():
    firma = FIRMA_PERSONAL_HTML

    assert "Juan José Domínguez Barrero" in firma
    assert "Asesor Fiscal, Contable y Mercantil" in firma
    assert "jjdominguez@gestinem.es" in firma
    assert "691 474 519" in firma


def test_firma_personal_no_antepone_el_nombre_de_usuario():
    cuerpo = construir_cuerpo_html(
        "Mensaje", FIRMA_PERSONAL_HTML, "",
    )

    assert "Saludos," in cuerpo
    assert "Administrador" not in cuerpo


def test_registra_entrada_y_evitar_duplicado(tmp_path):
    gestor = GestorSQLite(tmp_path / "test.db")
    gestor.upsert_empresa({
        "codigo": "E00001", "ejercicio": 2026, "nombre": "Cliente",
        "email": "cliente@example.com",
    })
    empresa = gestor.buscar_empresa_por_email("CLIENTE@example.com")
    payload = {
        "codigo_empresa": "E00001",
        "graph_message_id": "graph-in-1",
        "graph_conversation_id": "conversation-1",
        "remitente": "cliente@example.com",
        "destinatarios": ["oficina@gestinem.es"],
        "asunto": "Respuesta",
        "cuerpo_html": "<p>Hola</p>",
        "fecha": "2026-07-28T10:00:00Z",
        "mailbox": "oficina@gestinem.es",
    }

    first = gestor.registrar_entrada_comunicacion(payload)
    second = gestor.registrar_entrada_comunicacion(payload)

    assert empresa["codigo"] == "E00001"
    assert first is not None
    assert second is None
    assert gestor.listar_mensajes_comunicacion(first[0])[0]["direccion"] == "entrante"


def test_asigna_manualmente_un_correo_pendiente(tmp_path):
    gestor = GestorSQLite(tmp_path / "test.db")
    gestor.upsert_empresa({
        "codigo": "E00001", "ejercicio": 2026, "nombre": "Cliente",
        "responsable": "ANA",
    })
    payload = {
        "graph_message_id": "pending-1", "mailbox": "oficina@gestinem.es",
        "remitente": "nuevo@example.com", "asunto": "Consulta",
        "cuerpo_html": "<p>Hola</p>", "fecha": "2026-07-28T10:00:00Z",
    }
    gestor.guardar_comunicacion_sin_asignar(payload)

    result = gestor.asignar_comunicacion_pendiente(
        "pending-1", "E00001", 7, "ANA",
    )

    assert result is not None
    assert gestor.listar_comunicaciones_sin_asignar() == []
    assert gestor.listar_comunicaciones("E00001")[0]["responsable_nombre"] == "ANA"


def test_busca_empresa_en_lista_de_varios_emails(tmp_path):
    gestor = GestorSQLite(tmp_path / "test.db")
    gestor.upsert_empresa({
        "codigo": "E00001", "ejercicio": 2026, "nombre": "Cliente",
        "email": "administracion@example.com, gerente@example.com; fiscal@example.com",
    })

    assert gestor.buscar_empresa_por_email("GERENTE@example.com")["codigo"] == "E00001"


def test_supervision_global_incluye_cliente_responsable_buzon_y_estado(tmp_path):
    gestor = GestorSQLite(tmp_path / "test.db")
    gestor.upsert_empresa({
        "codigo": "E00001", "ejercicio": 2026, "nombre": "Cliente Uno",
    })
    payload = {
        "graph_message_id": "supervision-1",
        "mailbox": "oficina@gestinem.es",
        "remitente": "cliente@example.com",
        "asunto": "Consulta fiscal",
        "cuerpo_html": "<p>Hola</p>",
        "fecha": "2026-07-28T10:00:00Z",
    }
    gestor.guardar_comunicacion_sin_asignar(payload)
    comunicacion_id, _ = gestor.asignar_comunicacion_pendiente(
        "supervision-1", "E00001", 7, "ANA",
    )
    gestor.cambiar_estado_comunicacion(comunicacion_id, "respondido", 7)

    row = gestor.listar_comunicaciones_supervision()[0]

    assert row["cliente_nombre"] == "Cliente Uno"
    assert row["responsable_nombre"] == "ANA"
    assert row["mailbox"] == "oficina@gestinem.es"
    assert row["estado"] == "respondido"


def test_asignacion_masiva_mueve_todos_los_mensajes_seleccionados(tmp_path):
    gestor = GestorSQLite(tmp_path / "test.db")
    gestor.upsert_empresa({
        "codigo": "E00001", "ejercicio": 2026, "nombre": "Cliente Uno",
    })
    for index in range(3):
        gestor.guardar_comunicacion_sin_asignar({
            "graph_message_id": f"bulk-{index}",
            "mailbox": "oficina@gestinem.es",
            "remitente": "administracion@cliente.es",
            "asunto": f"Mensaje {index}",
            "cuerpo_html": "<p>Hola</p>",
            "fecha": f"2026-07-28T10:0{index}:00Z",
        })

    result = gestor.asignar_comunicaciones_pendientes(
        ["bulk-0", "bulk-1", "bulk-2"],
        "E00001", 3, "ANABEL",
    )

    assert result["asignadas"] == ["bulk-0", "bulk-1", "bulk-2"]
    assert result["omitidas"] == []
    assert gestor.listar_comunicaciones_sin_asignar() == []
    buzon = gestor.listar_buzon_responsable(3)
    assert len(buzon) == 3
    assert {item["mailbox"] for item in buzon} == {"oficina@gestinem.es"}


def test_pendiente_personal_aparece_en_buzon_del_responsable(tmp_path):
    gestor = GestorSQLite(tmp_path / "test.db")
    gestor.guardar_comunicacion_sin_asignar(
        {
            "graph_message_id": "personal-1",
            "mailbox": "admin@gestinem.es",
            "remitente": "cliente@example.com",
            "asunto": "Correo personal",
            "fecha": "2026-07-28T10:00:00Z",
        },
        responsable={"id": 1, "nombre": "Administrador"},
    )

    pendientes = gestor.listar_pendientes_responsable(1)

    assert len(pendientes) == 1
    assert pendientes[0]["responsable_nombre"] == "Administrador"


def test_asigna_sin_cliente_gestiona_descarta_y_restaura(tmp_path):
    gestor = GestorSQLite(tmp_path / "test.db")
    for index in range(2):
        gestor.guardar_comunicacion_sin_asignar({
            "graph_message_id": f"internal-{index}",
            "mailbox": "oficina@gestinem.es",
            "remitente": "proveedor@example.com",
            "asunto": "Aviso interno",
            "fecha": f"2026-07-28T10:0{index}:00Z",
        })

    assert gestor.asignar_comunicaciones_sin_cliente(
        ["internal-0"], 3, "ANABEL",
    ) == 1
    gestor.cambiar_estado_pendiente_responsable(
        "internal-0", "gestionado", 3,
    )
    assert gestor.listar_comunicaciones_sin_cliente_asignadas()[0]["estado"] == "gestionado"
    assert gestor.descartar_comunicaciones(
        ["internal-1"], "Administrador", "Publicidad",
    ) == 1
    assert gestor.listar_comunicaciones_descartadas()[0]["motivo_descarte"] == "Publicidad"
    assert gestor.restaurar_comunicaciones(["internal-1"]) == 1
    assert gestor.listar_comunicaciones_descartadas() == []


def test_reasigna_cliente_y_responsable_de_una_conversacion(tmp_path):
    gestor = GestorSQLite(tmp_path / "test.db")
    for codigo, nombre in (("E00001", "Cliente Uno"), ("E00002", "Cliente Dos")):
        gestor.upsert_empresa({
            "codigo": codigo, "ejercicio": 2026, "nombre": nombre,
        })
    gestor.guardar_comunicacion_sin_asignar({
        "graph_message_id": "reassign-1",
        "mailbox": "oficina@gestinem.es",
        "remitente": "cliente@example.com",
        "asunto": "Consulta",
        "fecha": "2026-07-28T10:00:00Z",
    })
    comunicacion_id, _ = gestor.asignar_comunicacion_pendiente(
        "reassign-1", "E00001", 3, "ANABEL",
    )

    assert gestor.reasignar_comunicacion(
        comunicacion_id, "E00002", 5, "NIDIA",
    )

    assert gestor.listar_comunicaciones("E00001") == []
    row = gestor.listar_comunicaciones("E00002")[0]
    assert row["responsable_usuario_id"] == 5
    assert row["responsable_nombre"] == "NIDIA"
    assert gestor.listar_buzon_responsable(3) == []
    assert gestor.listar_buzon_responsable(5)[0]["id"] == comunicacion_id


def test_descarta_y_restaura_una_conversacion_asignada(tmp_path):
    gestor = GestorSQLite(tmp_path / "test.db")
    gestor.upsert_empresa({
        "codigo": "E00001", "ejercicio": 2026, "nombre": "Cliente Uno",
    })
    gestor.guardar_comunicacion_sin_asignar({
        "graph_message_id": "discard-assigned-1",
        "mailbox": "oficina@gestinem.es",
        "remitente": "cliente@example.com",
        "asunto": "Publicidad",
        "fecha": "2026-07-28T10:00:00Z",
    })
    comunicacion_id, _ = gestor.asignar_comunicacion_pendiente(
        "discard-assigned-1", "E00001", 3, "ANABEL",
    )

    assert gestor.descartar_conversaciones(
        [comunicacion_id], "Administrador", "No corresponde",
    ) == 1
    assert gestor.listar_comunicaciones("E00001") == []
    assert gestor.listar_buzon_responsable(3) == []
    assert gestor.listar_comunicaciones_supervision() == []
    discarded = gestor.listar_conversaciones_descartadas()[0]
    assert discarded["id"] == comunicacion_id
    assert discarded["motivo_descarte"] == "No corresponde"

    assert gestor.restaurar_conversaciones([comunicacion_id]) == 1
    assert gestor.listar_comunicaciones("E00001")[0]["id"] == comunicacion_id
