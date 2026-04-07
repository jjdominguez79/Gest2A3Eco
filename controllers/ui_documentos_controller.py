from __future__ import annotations

import os
from copy import deepcopy

from services.documentos_service import DocumentosService


class DocumentosController:
    GLOBAL_CODE = "__global__"

    def __init__(self, gestor, codigo_empresa: str, ejercicio: int, view, global_mode: bool = False):
        self._gestor = gestor
        self._codigo = codigo_empresa
        self._ejercicio = ejercicio
        self._view = view
        self._global_mode = bool(global_mode)
        self._service = DocumentosService(gestor, codigo_empresa, ejercicio, global_mode=self._global_mode)
        self._plantillas = []
        self._clientes = []
        self._intervinientes = []
        self._documentos = []
        self._wizard_payload = {
            "plantilla_id": None,
            "titulo_documento": "",
            "cliente_modo": "existente",
            "cliente": {},
            "intervinientes": [],
            "custom_data": {},
            "observaciones": "",
        }
        self._auto_field_keys = set()

    def refresh(self):
        self._service.ensure_demo_templates()
        self._refresh_plantillas()
        self._refresh_clientes()
        self._refresh_intervinientes()
        self._refresh_documentos()
        self._sync_wizard()

    def apply_template_filter(self):
        self._view.set_templates(self._plantillas)

    def apply_cliente_filter(self):
        self._view.set_clientes(self._clientes)

    def apply_document_filter(self):
        self._view.set_documents(self._documentos)

    def import_template(self):
        if not self._ensure_write():
            return
        path = self._view.ask_open_docx_path()
        if not path:
            return
        try:
            self._service.register_template_file(path)
        except Exception as exc:
            self._view.show_error("Gest2A3Eco", str(exc))
            return
        self._refresh_plantillas()
        self._view.show_info("Gest2A3Eco", "Plantilla registrada.")

    def rename_template(self):
        if not self._ensure_write():
            return
        plantilla_id = self._view.get_selected_template_id()
        if not plantilla_id:
            self._view.show_info("Gest2A3Eco", "Selecciona una plantilla.")
            return
        plantilla = self._gestor.get_plantilla_documento(int(plantilla_id))
        if not plantilla:
            return
        nuevo_nombre = self._view.ask_template_name(plantilla.get("nombre", ""))
        if nuevo_nombre is None:
            return
        try:
            plantilla = self._service.rename_template(int(plantilla_id), nuevo_nombre)
        except Exception as exc:
            self._view.show_error("Gest2A3Eco", str(exc))
            return
        self._refresh_plantillas(selected_id=plantilla.get("id"))

    def open_template_docx(self):
        plantilla_id = self._view.get_selected_template_id()
        if not plantilla_id:
            self._view.show_info("Gest2A3Eco", "Selecciona una plantilla.")
            return
        plantilla = self._gestor.get_plantilla_documento(int(plantilla_id))
        if not plantilla:
            return
        path = str(plantilla.get("ruta_template") or "").strip()
        if not path or not os.path.exists(path):
            self._view.show_warning("Gest2A3Eco", "El archivo de plantilla no existe.")
            return
        try:
            os.startfile(path)
        except Exception as exc:
            self._view.show_error("Gest2A3Eco", str(exc))

    def refresh_template_variables(self):
        plantilla_id = self._view.get_selected_template_id()
        if not plantilla_id:
            self._view.show_info("Gest2A3Eco", "Selecciona una plantilla.")
            return
        try:
            plantilla = self._service.refresh_template_variables(int(plantilla_id))
        except Exception as exc:
            self._view.show_error("Gest2A3Eco", str(exc))
            return
        self._refresh_plantillas(selected_id=plantilla.get("id"))

    def delete_template(self):
        if not self._ensure_write():
            return
        plantilla_id = self._view.get_selected_template_id()
        if not plantilla_id:
            self._view.show_info("Gest2A3Eco", "Selecciona una plantilla.")
            return
        if not self._view.ask_yes_no("Gest2A3Eco", "Eliminar la plantilla seleccionada?"):
            return
        self._gestor.eliminar_plantilla_documento(int(plantilla_id))
        self._refresh_plantillas()

    def select_template_for_wizard(self):
        plantilla_id = self._view.get_selected_wizard_template_id()
        if not plantilla_id:
            self._view.show_info("Gest2A3Eco", "Selecciona una plantilla.")
            return
        plantilla = self._gestor.get_plantilla_documento(int(plantilla_id))
        if not plantilla:
            return
        self._wizard_payload["plantilla_id"] = plantilla.get("id")
        if not self._wizard_payload.get("titulo_documento"):
            self._wizard_payload["titulo_documento"] = plantilla.get("nombre", "")
        self._sync_dynamic_fields()
        self._sync_wizard()
        self._view.goto_wizard_tab(1)

    def load_selected_cliente(self):
        cliente_id = self._view.get_selected_cliente_id()
        if not cliente_id:
            self._view.show_info("Gest2A3Eco", "Selecciona un cliente.")
            return
        cliente = next((item for item in self._clientes if str(item.get("id")) == str(cliente_id)), None)
        if not cliente:
            return
        data = self._service.build_interviniente_from_empresa(cliente)
        self._wizard_payload["cliente_modo"] = "existente"
        self._wizard_payload["cliente"] = data
        self._wizard_payload.pop("omit_cliente_interviniente", None)
        self._sync_cliente_interviniente()
        self._sync_dynamic_fields()
        self._sync_wizard()
        self._view.goto_wizard_tab(2)

    def save_manual_cliente(self):
        data = dict(self._wizard_payload.get("cliente") or {})
        data.update(self._view.get_manual_cliente_form())
        nombre = str(data.get("nombre_razon_social") or "").strip()
        if not nombre:
            self._view.show_warning("Gest2A3Eco", "El nombre o razon social del cliente es obligatorio.")
            return False
        if not data.get("cliente_id"):
            self._wizard_payload["cliente_modo"] = "manual"
        self._wizard_payload.pop("omit_cliente_interviniente", None)
        self._wizard_payload["cliente"] = data
        self._sync_cliente_interviniente()
        self._sync_dynamic_fields()
        self._sync_wizard()
        return True

    def add_manual_interviniente(self):
        data = self._view.open_interviniente_dialog(None)
        if not data:
            return
        self._wizard_payload["intervinientes"].append(data)
        self._sync_dynamic_fields()
        self._sync_wizard()

    def add_saved_interviniente(self):
        interviniente_id = self._view.get_selected_saved_interviniente_id()
        if not interviniente_id:
            self._view.show_info("Gest2A3Eco", "Selecciona un interviniente habitual.")
            return
        interviniente = next((item for item in self._intervinientes if str(item.get("id")) == str(interviniente_id)), None)
        if not interviniente:
            return
        if interviniente.get("_contact_source") == "tercero":
            item = self._service.build_interviniente_from_tercero(interviniente)
        else:
            item = dict(interviniente)
        item["rol_en_documento"] = item.get("rol_en_documento") or "interviniente"
        self._wizard_payload["intervinientes"].append(item)
        self._sync_dynamic_fields()
        self._sync_wizard()

    def edit_draft_interviniente(self):
        idx = self._view.get_selected_draft_interviniente_index()
        if idx is None:
            self._view.show_info("Gest2A3Eco", "Selecciona un interviniente del borrador.")
            return
        current = self._wizard_payload["intervinientes"][idx]
        updated = self._view.open_interviniente_dialog(current)
        if not updated:
            return
        updated["_source"] = current.get("_source")
        self._wizard_payload["intervinientes"][idx] = updated
        self._sync_dynamic_fields()
        self._sync_wizard()

    def remove_draft_interviniente(self):
        idx = self._view.get_selected_draft_interviniente_index()
        if idx is None:
            self._view.show_info("Gest2A3Eco", "Selecciona un interviniente del borrador.")
            return
        if self._wizard_payload["intervinientes"][idx].get("_source") == "cliente":
            self._wizard_payload["omit_cliente_interviniente"] = True
        del self._wizard_payload["intervinientes"][idx]
        self._sync_dynamic_fields()
        self._sync_wizard()

    def move_draft_interviniente_up(self):
        self._move_draft_interviniente(-1)

    def move_draft_interviniente_down(self):
        self._move_draft_interviniente(+1)

    def save_habitual_interviniente(self):
        if not self._ensure_write():
            return
        data = self._view.open_interviniente_dialog(None)
        if not data:
            return
        data["codigo_empresa"] = self._codigo
        data["ejercicio"] = self._ejercicio
        data["es_cliente_habitual"] = bool(data.get("es_cliente_habitual"))
        self._gestor.upsert_interviniente(data)
        self._refresh_intervinientes()

    def edit_habitual_interviniente(self):
        if not self._ensure_write():
            return
        interviniente_id = self._view.get_selected_saved_interviniente_id()
        if not interviniente_id:
            self._view.show_info("Gest2A3Eco", "Selecciona un interviniente.")
            return
        current = next((item for item in self._intervinientes if str(item.get("id")) == str(interviniente_id)), None)
        if not current:
            return
        data = self._view.open_interviniente_dialog(current)
        if not data:
            return
        data["id"] = current.get("id")
        data["codigo_empresa"] = self._codigo
        data["ejercicio"] = self._ejercicio
        self._gestor.upsert_interviniente(data)
        self._refresh_intervinientes(selected_id=current.get("id"))

    def delete_habitual_interviniente(self):
        if not self._ensure_write():
            return
        interviniente_id = self._view.get_selected_saved_interviniente_id()
        if not interviniente_id:
            self._view.show_info("Gest2A3Eco", "Selecciona un interviniente.")
            return
        if not self._view.ask_yes_no("Gest2A3Eco", "Eliminar el interviniente seleccionado?"):
            return
        self._gestor.eliminar_interviniente(int(interviniente_id))
        self._refresh_intervinientes()

    def generate_document(self):
        if not self._ensure_write():
            return
        if not self._wizard_payload.get("plantilla_id"):
            self._view.show_warning("Gest2A3Eco", "Selecciona primero una plantilla.")
            return
        if not self.save_manual_cliente():
            return
        self._wizard_payload["titulo_documento"] = self._view.get_document_title()
        self._wizard_payload["observaciones"] = self._view.get_document_observaciones()
        self._wizard_payload["custom_data"] = self._view.get_dynamic_field_values()
        self._wizard_payload["custom_data"]["observaciones"] = self._wizard_payload.get("observaciones", "")
        try:
            documento = self._service.generate_document(deepcopy(self._wizard_payload))
        except Exception as exc:
            self._view.show_error("Gest2A3Eco", str(exc))
            return
        self._refresh_documentos(selected_id=documento.get("id"))
        self._view.show_info(
            "Gest2A3Eco",
            f"Documento generado.\nDOCX: {documento.get('ruta_docx')}\nPDF: {documento.get('ruta_pdf') or 'No generado'}",
        )

    def load_document_into_wizard(self):
        documento_id = self._view.get_selected_document_id()
        if not documento_id:
            self._view.show_info("Gest2A3Eco", "Selecciona un documento del historico.")
            return
        documento = self._gestor.get_documento_generado(int(documento_id))
        if not documento:
            return
        payload = dict(documento.get("json_datos_generacion") or {})
        payload.setdefault("intervinientes", [])
        self._wizard_payload = payload
        self._sync_dynamic_fields()
        self._sync_wizard()
        self._view.goto_main_tab(1)

    def duplicate_document(self):
        documento_id = self._view.get_selected_document_id()
        if not documento_id:
            self._view.show_info("Gest2A3Eco", "Selecciona un documento.")
            return
        try:
            self._wizard_payload = self._service.duplicate_document_payload(int(documento_id))
        except Exception as exc:
            self._view.show_error("Gest2A3Eco", str(exc))
            return
        self._sync_dynamic_fields()
        self._sync_wizard()
        self._view.goto_main_tab(1)

    def open_document_docx(self):
        self._open_document_file("ruta_docx")

    def open_document_pdf(self):
        self._open_document_file("ruta_pdf")

    def _open_document_file(self, field: str):
        documento_id = self._view.get_selected_document_id()
        if not documento_id:
            self._view.show_info("Gest2A3Eco", "Selecciona un documento.")
            return
        documento = self._gestor.get_documento_generado(int(documento_id))
        if not documento:
            return
        path = str(documento.get(field) or "").strip()
        if not path or not os.path.exists(path):
            self._view.show_warning("Gest2A3Eco", "El archivo no existe.")
            return
        try:
            os.startfile(path)
        except Exception as exc:
            self._view.show_error("Gest2A3Eco", str(exc))

    def delete_document(self):
        if not self._ensure_write():
            return
        documento_id = self._view.get_selected_document_id()
        if not documento_id:
            self._view.show_info("Gest2A3Eco", "Selecciona un documento.")
            return
        if not self._view.ask_yes_no("Gest2A3Eco", "Eliminar el documento del historico?"):
            return
        self._gestor.eliminar_documento_generado(int(documento_id))
        self._refresh_documentos()

    def _refresh_plantillas(self, selected_id=None):
        self._plantillas = self._gestor.listar_plantillas_documentos(self._codigo, self._ejercicio)
        self._view.set_templates(self._plantillas, selected_id=selected_id)
        self._view.set_wizard_templates(self._plantillas, selected_id=self._wizard_payload.get("plantilla_id"))

    def _refresh_clientes(self):
        self._clientes = self._service.list_clientes()
        self._view.set_clientes(self._clientes)

    def _refresh_intervinientes(self, selected_id=None):
        self._intervinientes = self._service.list_contactos()
        self._view.set_saved_intervinientes(self._intervinientes, selected_id=selected_id)

    def _refresh_documentos(self, selected_id=None):
        self._documentos = self._gestor.listar_documentos_generados(self._codigo, self._ejercicio)
        self._view.set_documents(self._documentos, selected_id=selected_id)

    def _sync_wizard(self):
        self._view.set_wizard_templates(self._plantillas, selected_id=self._wizard_payload.get("plantilla_id"))
        self._view.set_document_title(self._wizard_payload.get("titulo_documento", ""))
        self._view.set_manual_cliente_form(self._wizard_payload.get("cliente", {}))
        self._view.set_draft_intervinientes(self._wizard_payload.get("intervinientes", []))
        self._view.set_document_observaciones(self._wizard_payload.get("observaciones", ""))
        self._sync_dynamic_fields()

    def _sync_cliente_interviniente(self):
        cliente = dict(self._wizard_payload.get("cliente") or {})
        if self._wizard_payload.get("omit_cliente_interviniente"):
            self._wizard_payload["intervinientes"] = [
                item for item in (self._wizard_payload.get("intervinientes") or []) if item.get("_source") != "cliente"
            ]
            return
        nombre = str(cliente.get("nombre_razon_social") or cliente.get("nombre") or "").strip()
        if not nombre:
            return
        item = {
            "tipo_persona": cliente.get("tipo_persona") or "juridica",
            "nombre_razon_social": nombre,
            "nif": cliente.get("nif", ""),
            "domicilio": cliente.get("domicilio", "") or cliente.get("direccion", ""),
            "municipio": cliente.get("municipio", "") or cliente.get("poblacion", ""),
            "provincia": cliente.get("provincia", ""),
            "cp": cliente.get("cp", ""),
            "telefono": cliente.get("telefono", ""),
            "email": cliente.get("email", ""),
            "representante": cliente.get("representante", ""),
            "cargo": cliente.get("cargo", ""),
            "rol_en_documento": cliente.get("rol_en_documento") or "interviniente 1",
            "cliente_id": cliente.get("cliente_id"),
            "_source": "cliente",
        }
        items = list(self._wizard_payload.get("intervinientes") or [])
        replaced = False
        for idx, current in enumerate(items):
            if current.get("_source") == "cliente":
                items[idx] = item
                replaced = True
                break
        if not replaced:
            items.insert(0, item)
        self._wizard_payload["intervinientes"] = items

    def _move_draft_interviniente(self, step: int):
        idx = self._view.get_selected_draft_interviniente_index()
        if idx is None:
            self._view.show_info("Gest2A3Eco", "Selecciona un interviniente del borrador.")
            return
        new_idx = idx + step
        items = self._wizard_payload.get("intervinientes") or []
        if new_idx < 0 or new_idx >= len(items):
            return
        items[idx], items[new_idx] = items[new_idx], items[idx]
        self._wizard_payload["intervinientes"] = items
        self._sync_dynamic_fields()
        self._sync_wizard()
        self._view.select_draft_interviniente(new_idx)

    def _sync_dynamic_fields(self):
        plantilla_id = self._wizard_payload.get("plantilla_id")
        if not plantilla_id:
            self._view.set_dynamic_fields([])
            self._auto_field_keys = set()
            return
        plantilla = self._gestor.get_plantilla_documento(int(plantilla_id))
        if not plantilla:
            self._view.set_dynamic_fields([])
            self._auto_field_keys = set()
            return
        preview = self._service.build_preview_values(self._wizard_payload)
        current_custom = dict(self._wizard_payload.get("custom_data") or {})
        fields = []
        auto_keys = set()
        prefixes = ("empresa.", "cliente.", "documento.", "operacion.", "interviniente_", "fecha_hoy", "intervinientes_resumen")
        for key in plantilla.get("variables", []):
            auto_value = preview.get(key, "")
            is_auto = key.startswith(prefixes) or key == "fecha_hoy" or key == "intervinientes_resumen"
            if is_auto:
                auto_keys.add(key)
            value = auto_value if is_auto else str(current_custom.get(key, auto_value) or "")
            fields.append(
                {
                    "key": key,
                    "label": key.replace(".", " / ").replace("_", " "),
                    "value": value,
                    "readonly": is_auto,
                }
            )
        self._auto_field_keys = auto_keys
        self._view.set_dynamic_fields(fields)

    def _ensure_write(self) -> bool:
        if self._global_mode:
            return True
        security = getattr(self._gestor, "security", None)
        if not security:
            return True
        if security.can_write_company(self._codigo):
            return True
        self._view.show_warning("Gest2A3Eco", "Esta empresa esta en modo solo lectura para el usuario actual.")
        return False
