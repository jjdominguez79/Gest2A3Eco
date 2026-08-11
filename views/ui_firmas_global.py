"""Bandeja global de solicitudes de firma, con cliente opcional."""
from __future__ import annotations

import os
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from services.firma.firma_service import FirmaService
from services.firma.datos_firma_service import listar_terceros_para_firma
from services.firma.plantillas_service import PlantillasFirmaService
from services.firma.provider import build_firma_provider
from services.gestion_documental_service import GestionDocumentalService
from utils.utilidades import get_document_repository_dir, load_app_config
from views.ui_firma_dialog import UIFirmaDialog
from views.ui_documento_firma_plantilla import UIDocumentoFirmaPlantillaDialog
from views.ui_plantillas_firma import UIPlantillasFirmaManager

GLOBAL_CODE = "__GLOBAL__"


class UIFirmasGlobal(ttk.Frame):
    def __init__(self, parent, gestor, session=None):
        super().__init__(parent, padding=12)
        self._gestor = gestor
        self._session = session
        self._rows = {}
        self._build()
        self._refresh()

    def _build(self):
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="Firmas", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(header, text="Nueva solicitud desde disco", command=self._new_request).pack(side="right")
        ttk.Button(header, text="Nueva desde plantilla", command=self._new_from_template).pack(side="right", padx=6)
        if self._is_admin():
            ttk.Button(header, text="Gestionar plantillas", command=self._manage_templates).pack(side="right")
        filters = ttk.Frame(self)
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="Estado").pack(side="left")
        self._status = tk.StringVar(value="Todos")
        ttk.Combobox(
            filters, textvariable=self._status, state="readonly", width=18,
            values=("Todos", "Pendientes", "Enviados", "Firmados", "Finalizados"),
        ).pack(side="left", padx=5)
        ttk.Label(filters, text="Buscar").pack(side="left", padx=(14, 0))
        self._search = tk.StringVar()
        ttk.Entry(filters, textvariable=self._search, width=32).pack(side="left", padx=5)
        ttk.Button(filters, text="Actualizar", command=self._refresh).pack(side="left", padx=6)
        self._search.trace_add("write", lambda *_: self._refresh())
        self._status.trace_add("write", lambda *_: self._refresh())

        self._tree = ttk.Treeview(
            self, columns=("estado", "cliente", "documento", "fecha", "resultado"),
            show="headings", selectmode="extended",
        )
        for key, title, width in (
            ("estado", "Estado", 130), ("cliente", "Cliente", 180),
            ("documento", "Documento", 360), ("fecha", "Creada", 160),
            ("resultado", "Documento firmado", 300),
        ):
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, anchor="w")
        self._tree.pack(fill="both", expand=True)
        self._tree.bind("<Double-1>", lambda _event: self._open_selected())
        self._tree.bind("<Control-a>", lambda _e: self._tree.selection_set(self._tree.get_children()))
        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Actualizar estado", command=self._update_selected).pack(side="left")
        ttk.Button(actions, text="Abrir documento", command=self._open_selected).pack(side="left", padx=6)
        ttk.Button(actions, text="Reenviar", command=self._resend_selected).pack(side="left")
        ttk.Button(actions, text="Cancelar", command=self._cancel_selected).pack(side="left", padx=6)
        ttk.Button(actions, text="Marcar pendiente", command=self._mark_pending).pack(side="left", padx=6)
        ttk.Button(actions, text="Dar por finalizado", command=self._finish_selected).pack(side="left")
        ttk.Button(actions, text="Eliminar", command=self._delete_selected).pack(side="left", padx=6)
        self._summary = ttk.Label(actions, text="")
        self._summary.pack(side="right")

    def _refresh(self):
        estado = self._status.get()
        rows = self._gestor.listar_todas_firma_solicitudes("", self._search.get().strip())
        grupos = {
            "Pendientes": {"borrador", "incidencia", "rechazado"},
            "Enviados": {"enviado", "parcialmente_firmado"},
            "Firmados": {"firmado"},
            "Finalizados": {"finalizado"},
        }
        if estado in grupos:
            rows = [row for row in rows if str(row.get("estado") or "") in grupos[estado]]
        nombres_empresas = {}
        for empresa in self._gestor.listar_empresas():
            codigo_empresa = str(empresa.get("codigo") or "")
            if codigo_empresa:
                nombres_empresas[codigo_empresa] = str(empresa.get("nombre") or "").strip()
        self._rows = {str(row["id"]): row for row in rows}
        self._tree.delete(*self._tree.get_children())
        for row in rows:
            codigo = str(row.get("codigo_empresa") or "")
            cliente = self._cliente_visible(codigo, nombres_empresas.get(codigo))
            estado_visible = self._estado_visible(row.get("estado"))
            resultado = row.get("ruta_firmado") or "Pendiente de descarga"
            self._tree.insert("", "end", iid=str(row["id"]), values=(
                estado_visible, cliente, row.get("nombre_documento") or "",
                row.get("created_at") or "", resultado,
            ))
        self._summary.configure(text=f"Solicitudes: {len(rows)}")

    @staticmethod
    def _cliente_visible(codigo, nombre=""):
        codigo = str(codigo or "").strip()
        nombre = str(nombre or "").strip()
        if not codigo or codigo == GLOBAL_CODE:
            return "Sin cliente"
        return f"{codigo} - {nombre}" if nombre else codigo

    @staticmethod
    def _estado_visible(estado):
        estado = str(estado or "")
        if estado == "firmado":
            return "Firmado"
        if estado == "finalizado":
            return "Finalizado"
        if estado in {"enviado", "parcialmente_firmado"}:
            return "Enviado"
        return "Pendiente"

    def _selected(self):
        selected = self._tree.selection()
        return self._rows.get(selected[0]) if selected else None

    def _manage_templates(self):
        dialog = UIPlantillasFirmaManager(self, self._gestor, self._user_name())
        self.wait_window(dialog)

    def _new_from_template(self):
        service = PlantillasFirmaService(self._gestor)
        dialog = UIDocumentoFirmaPlantillaDialog(
            self, service, self._gestor, usuario=self._user_name()
        )
        self.wait_window(dialog)
        if not dialog.result:
            return
        setup = dict(dialog.result)
        empresa = setup.get("empresa") or {}
        tercero = setup.get("tercero") or {}
        plantilla = setup["plantilla"]
        firmantes, zonas = self._defaults_from_template(plantilla, empresa, tercero)
        self.configure(cursor="watch")

        def worker():
            try:
                documento = service.generar_documento(
                    plantilla["id"], setup["valores"], empresa=empresa, tercero=tercero,
                    firmantes=firmantes, usuario=self._user_name(),
                    ejercicio=int(empresa.get("ejercicio") or datetime.now().year),
                )
                self.after(0, self._review_generated, service, setup, documento, firmantes, zonas)
            except Exception as exc:
                self.after(0, self._done, "", str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _review_generated(self, service, setup, documento, firmantes, zonas):
        self.configure(cursor="")
        try:
            os.startfile(documento["ruta_docx"])
        except Exception as exc:
            messagebox.showerror("Documento", str(exc), parent=self)
            return
        if not messagebox.askyesno(
            "Revisar documento",
            "Revise y guarde el documento en Word. Cuando haya cerrado Word, pulse Si para regenerar y revisar el PDF.",
            parent=self,
        ):
            return
        self.configure(cursor="watch")

        def worker():
            try:
                actualizado = service.regenerar_pdf(documento["id"])
                self.after(0, self._configure_generated_signature, service, setup, actualizado, firmantes, zonas)
            except Exception as exc:
                self.after(0, self._done, "", str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _configure_generated_signature(self, service, setup, documento, firmantes, zonas):
        self.configure(cursor="")
        plantilla = setup["plantilla"]
        cfg = load_app_config()
        initial = {
            "asunto": plantilla.get("asunto") or plantilla.get("nombre") or documento["titulo"],
            "mensaje": plantilla.get("mensaje") or "",
            "firmantes": firmantes,
            "zonas": zonas,
        }
        empresa = setup.get("empresa") or {}
        codigo = str(empresa.get("codigo") or GLOBAL_CODE)
        ejercicio = int(empresa.get("ejercicio") or datetime.now().year)
        terceros = listar_terceros_para_firma(
            self._gestor, "" if codigo == GLOBAL_CODE else codigo, ejercicio,
        )
        dialog = UIFirmaDialog(
            self, documento["ruta_pdf"], terceros=terceros,
            remitente=self._remitente_config(cfg), initial=initial,
        )
        self.wait_window(dialog)
        if not dialog.result:
            return
        result = dict(dialog.result)
        result["usar_sms"] = any(bool(f.get("usar_sms")) for f in plantilla.get("firmantes") or [])
        self._save_template_zones_if_admin(plantilla, result.get("zonas") or [])
        self.configure(cursor="watch")

        def worker():
            try:
                archived_id = ""
                envio = documento["ruta_pdf"]
                if codigo != GLOBAL_CODE:
                    archived_id = GestionDocumentalService(self._gestor).importar_archivo(
                        codigo_empresa=codigo, ejercicio=ejercicio, categoria_id="firmas",
                        source=envio, usuario=self._user_name(),
                    )
                    envio = self._gestor.get_documento_archivo(archived_id)["ruta"]
                firma = FirmaService(
                    self._gestor, provider=build_firma_provider(cfg),
                    max_mb=cfg.get("firma_max_mb", 15),
                )
                solicitud_id = firma.crear_solicitud(
                    codigo, ejercicio, envio, result["firmantes"], origen="plantilla",
                    documento_archivo_id=archived_id, asunto=result["asunto"], mensaje=result["mensaje"],
                    usar_sms=bool(result.get("usar_sms")), zonas=result["zonas"], creado_por=self._user_name(),
                )
                firma.enviar(solicitud_id)
                self._gestor.vincular_documento_firma_solicitud(documento["id"], solicitud_id)
                self.after(0, self._done, "Documento generado y enviado a firma.", "")
            except Exception as exc:
                self.after(0, self._done, "", str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _defaults_from_template(self, plantilla, empresa, tercero):
        cfg = load_app_config()
        sources = {
            "empresa": empresa,
            "tercero": tercero,
            "gestor": self._remitente_config(cfg),
            "manual": {},
        }
        firmantes = []
        roles = []
        for pos, definition in enumerate(plantilla.get("firmantes") or []):
            source = dict(sources.get(str(definition.get("origen") or "manual"), {}) or {})
            firmantes.append({
                "orden": pos + 1,
                "nombre": source.get("nombre_legal") or source.get("nombre") or definition.get("nombre") or "",
                "email": source.get("email") or source.get("correo") or definition.get("email") or "",
                "telefono": source.get("telefono") or definition.get("telefono") or "",
                "tercero_id": source.get("tercero_id") or source.get("id"),
                "es_remitente": str(definition.get("origen")) == "gestor",
            })
            roles.append(str(definition.get("rol") or f"Firmante {pos + 1}"))
        if not firmantes:
            firmantes = [{"orden": 1, "nombre": "", "email": "", "telefono": "", "es_remitente": False}]
            roles = ["Firmante 1"]
        zones = []
        for zone in plantilla.get("zonas") or []:
            role = str(zone.get("rol") or "")
            if role not in roles:
                continue
            zones.append({
                "pagina": int(zone["pagina"]), "x": float(zone["x"]), "y": float(zone["y"]),
                "ancho": float(zone["ancho"]), "alto": float(zone["alto"]),
                "firmante": roles.index(role),
            })
        return firmantes, zones

    def _save_template_zones_if_admin(self, plantilla, zones):
        if not self._is_admin() or not zones:
            return
        roles = [str(f.get("rol") or "") for f in plantilla.get("firmantes") or []]
        if not roles or any(int(z.get("firmante", -1)) not in range(len(roles)) for z in zones):
            return
        updated = dict(plantilla)
        updated["zonas"] = [
            {**{key: zone[key] for key in ("pagina", "x", "y", "ancho", "alto")},
             "rol": roles[int(zone["firmante"])]}
            for zone in zones
        ]
        updated["zonas_revisadas"] = True
        try:
            PlantillasFirmaService(self._gestor).guardar_configuracion(updated, self._user_name())
        except Exception:
            pass

    def _is_admin(self):
        return bool(self._session and self._session.is_admin())

    def _new_request(self):
        ruta = filedialog.askopenfilename(parent=self, title="Seleccionar PDF", filetypes=(("PDF", "*.pdf"),))
        if not ruta:
            return
        empresas = self._gestor.listar_empresas()
        setup = _FirmaGlobalSetup(self, empresas)
        self.wait_window(setup)
        if setup.result is None:
            return
        codigo = setup.result.get("codigo") or GLOBAL_CODE
        ejercicio = int(setup.result.get("ejercicio") or datetime.now().year)
        terceros = listar_terceros_para_firma(
            self._gestor, "" if codigo == GLOBAL_CODE else codigo, ejercicio,
        )
        cfg = load_app_config()
        remitente = {
            "nombre": cfg.get("signrequest_gestor_email") or cfg.get("signrequest_from_email") or "Remitente",
            "email": cfg.get("signrequest_gestor_email") or cfg.get("signrequest_from_email") or "",
            "telefono": cfg.get("signrequest_gestor_telefono") or "",
        }
        firmante_cliente = self._firmante_desde_empresa(setup.result)
        initial = {"firmantes": [firmante_cliente]} if firmante_cliente else None
        dialog = UIFirmaDialog(
            self, ruta, terceros=terceros, remitente=remitente, initial=initial,
        )
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.configure(cursor="watch")

        def worker():
            try:
                provider = build_firma_provider(cfg)
                archived_id = ""
                envio = ruta
                if codigo != GLOBAL_CODE:
                    category = next(c for c in self._gestor.listar_categorias_documentales() if c["id"] == "firmas")
                    archived_id = GestionDocumentalService(self._gestor).importar_archivo(
                        codigo_empresa=codigo, ejercicio=ejercicio, categoria_id=category["id"],
                        source=ruta, usuario=self._user_name(),
                    )
                    envio = self._gestor.get_documento_archivo(archived_id)["ruta"]
                service = FirmaService(self._gestor, provider=provider, max_mb=cfg.get("firma_max_mb", 15))
                solicitud = service.crear_solicitud(
                    codigo, ejercicio, envio, dialog.result["firmantes"], origen="disco",
                    documento_archivo_id=archived_id, asunto=dialog.result["asunto"],
                    mensaje=dialog.result["mensaje"], zonas=dialog.result["zonas"],
                    creado_por=self._user_name(),
                )
                service.enviar(solicitud)
                self.after(0, self._done, "Solicitud enviada.", "")
            except Exception as exc:
                self.after(0, self._done, "", str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _update_selected(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Firmas", "Selecciona al menos una solicitud.", parent=self)
            return
        rows = [self._rows[iid] for iid in sel if iid in self._rows]
        if not rows:
            return
        cfg = load_app_config()
        self.configure(cursor="watch")

        def worker():
            provider = build_firma_provider(cfg)
            service = FirmaService(self._gestor, provider=provider, max_mb=cfg.get("firma_max_mb", 15))
            ok = 0
            errores = []
            ultimo_result = None
            for row in rows:
                try:
                    destination = self._evidence_dir(row)
                    ultimo_result = service.actualizar_estado(row["id"], str(destination))
                    if ultimo_result.get("estado") == "firmado":
                        service.archivar_evidencias(row["id"])
                    ok += 1
                except Exception as exc:
                    errores.append(f"{row.get('nombre_documento') or row['id']}: {exc}")
            # Componer mensaje de resultado
            if len(rows) == 1:
                estado_txt = self._estado_visible((ultimo_result or {}).get("estado")) if ok else ""
                detalle = self._resumen_entrega(((ultimo_result or {}).get("proveedor") or {}).get("firmantes") or []) if ok else ""
                mensaje = f"Estado: {estado_txt}." if ok else ""
                if detalle:
                    mensaje += "\n\n" + detalle
                error_txt = errores[0] if errores else ""
                self.after(0, self._done, mensaje, error_txt)
            else:
                partes = [f"{ok} de {len(rows)} solicitud(es) actualizadas correctamente."]
                if errores:
                    partes.append(f"\n{len(errores)} con error:\n" + "\n".join(errores[:10]))
                self.after(0, self._done, "\n".join(partes), "")

        threading.Thread(target=worker, daemon=True).start()

    def _resend_selected(self):
        row = self._selected()
        if not row:
            return
        if row.get("estado") != "borrador":
            self._simple_action("reenviar", "Solicitud reenviada.")
            return
        solicitud = self._gestor.get_firma_solicitud(row["id"])
        if not solicitud:
            return
        codigo = str(solicitud.get("codigo_empresa") or "")
        ejercicio = int(solicitud.get("ejercicio") or datetime.now().year)
        terceros = listar_terceros_para_firma(
            self._gestor, "" if codigo == GLOBAL_CODE else codigo, ejercicio,
        )
        cfg = load_app_config()
        remitente = self._remitente_config(cfg)
        dialog = UIFirmaDialog(
            self, solicitud.get("ruta_origen") or row.get("ruta_origen"),
            terceros=terceros, remitente=remitente, initial=solicitud,
        )
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.configure(cursor="watch")

        def worker():
            try:
                result = dict(dialog.result)
                service = FirmaService(
                    self._gestor, provider=build_firma_provider(cfg),
                    max_mb=cfg.get("firma_max_mb", 15),
                )
                service.editar_y_reenviar(
                    solicitud["id"], result["firmantes"], result["asunto"],
                    result["mensaje"], result["zonas"],
                )
                self.after(0, self._done, "Datos corregidos y solicitud reenviada.", "")
            except Exception as exc:
                self.after(0, self._done, "", str(exc))
        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _remitente_config(cfg):
        email = cfg.get("signrequest_gestor_email") or cfg.get("signrequest_from_email") or ""
        return {
            "nombre": email or "Remitente",
            "email": email,
            "telefono": cfg.get("signrequest_gestor_telefono") or "",
        }

    @staticmethod
    def _firmante_desde_empresa(empresa):
        """Prepara el contacto principal de la ficha para una firma desde disco."""
        if not empresa or not empresa.get("codigo"):
            return None
        correos = str(empresa.get("email") or empresa.get("correo") or "")
        # La ficha admite varios correos; SignRequest necesita un destinatario
        # por firmante, por lo que proponemos el primero y queda editable.
        email = correos.replace(";", ",").split(",", 1)[0].strip()
        return {
            "nombre": str(empresa.get("nombre") or "").strip(),
            "email": email,
            "telefono": str(empresa.get("telefono") or "").strip(),
        }

    def _cancel_selected(self):
        self._simple_action("cancelar", "Solicitud cancelada.")

    def _mark_pending(self):
        self._simple_action("marcar_pendiente", "Solicitud preparada para un nuevo envio.")

    def _finish_selected(self):
        self._simple_action("finalizar", "Expediente marcado como finalizado.")

    def _delete_selected(self):
        row = self._selected()
        if not row:
            return
        if not messagebox.askyesno(
                "Firmas", "Se eliminara el expediente local y el documento remoto de SignRequest.\n\n"
                "El PDF original se conservara. ¿Continuar?", parent=self):
            return
        self._simple_action("eliminar", "Expediente eliminado local y remotamente.")

    def _simple_action(self, action, success):
        row = self._selected()
        if not row:
            return
        cfg = load_app_config()
        self.configure(cursor="watch")

        def worker():
            try:
                service = FirmaService(self._gestor, provider=build_firma_provider(cfg))
                getattr(service, action)(row["id"])
                self.after(0, self._done, success, "")
            except Exception as exc:
                self.after(0, self._done, "", str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _open_selected(self):
        row = self._selected()
        if not row:
            return
        ruta = row.get("ruta_firmado") or row.get("ruta_origen")
        if not ruta or not Path(ruta).is_file():
            messagebox.showinfo("Firmas", "El documento firmado aun no esta descargado.", parent=self)
            return
        try:
            os.startfile(str(ruta))
        except Exception as exc:
            messagebox.showerror("Firmas", str(exc), parent=self)

    def _evidence_dir(self, row):
        codigo = str(row.get("codigo_empresa") or "")
        if codigo == GLOBAL_CODE:
            path = get_document_repository_dir() / "Firmas"
        else:
            path = GestionDocumentalService(self._gestor)._category_directory(
                codigo, int(row.get("ejercicio") or datetime.now().year), "FIRMAS"
            )
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _user_name(self):
        return str(getattr(getattr(self._session, "user", None), "nombre", "") or "")

    def _done(self, success, error):
        self.configure(cursor="")
        if error:
            messagebox.showerror("Firmas", error, parent=self)
        else:
            self._refresh()
            messagebox.showinfo("Firmas", success, parent=self)

    @staticmethod
    def _resumen_entrega(firmantes):
        lineas = []
        for item in sorted(firmantes, key=lambda row: int(row.get("order") or 0)):
            email = str(item.get("email") or "Firmante")
            orden = int(item.get("order") or 0)
            if item.get("signed"):
                estado = "firmado"
            elif item.get("declined"):
                estado = "rechazado"
            elif item.get("viewed") or item.get("email_viewed"):
                estado = "correo abierto"
            elif item.get("emailed"):
                estado = "correo enviado"
            else:
                estado = "en espera del firmante anterior" if orden > 1 else "correo aun no enviado"
            lineas.append(f"{orden}. {email}: {estado}")
        return "Entrega por firmante:\n" + "\n".join(lineas) if lineas else ""


class _FirmaGlobalSetup(tk.Toplevel):
    def __init__(self, parent, empresas):
        super().__init__(parent)
        self.title("Destino del documento")
        self.transient(parent)
        self.grab_set()
        self.result = None
        # listar_empresas devuelve una fila por ejercicio; conservamos la mas
        # reciente para no repetir clientes ni recuperar un email antiguo.
        empresas_por_codigo = {}
        for item in empresas or []:
            codigo = str(item.get("codigo") or "")
            anterior = empresas_por_codigo.get(codigo)
            if anterior is None or int(item.get("ejercicio") or 0) >= int(
                anterior.get("ejercicio") or 0
            ):
                empresas_por_codigo[codigo] = item
        self._empresas = list(empresas_por_codigo.values())
        ttk.Label(self, text="Cliente (opcional)").pack(anchor="w", padx=12, pady=(12, 3))
        self._client = tk.StringVar(value="Sin cliente")
        self._client_values = ["Sin cliente"] + [self._company_label(e) for e in self._empresas]
        self._client_cb = ttk.Combobox(
            self, textvariable=self._client, values=self._client_values, state="normal", width=48,
        )
        self._client_cb.pack(padx=12)
        self._client_cb.bind("<KeyRelease>", self._filter_clients)
        self._client_cb.bind("<Return>", lambda _e: self._select_match())
        ttk.Label(self, text="Si eliges cliente, el original y las evidencias iran a la categoria Firmas.", wraplength=380).pack(padx=12, pady=10)
        ttk.Button(self, text="Continuar", command=self._accept).pack(side="right", padx=12, pady=(0, 12))
        ttk.Button(self, text="Cancelar", command=self.destroy).pack(side="right", pady=(0, 12))

    @staticmethod
    def _company_label(empresa):
        return f"{empresa.get('codigo')} - {empresa.get('nombre')}"

    def _matches(self):
        texto = self._client.get().strip().lower()
        return [value for value in self._client_values if not texto or texto in value.lower()]

    def _filter_clients(self, event=None):
        if event and event.keysym in ("Return", "Tab", "Down", "Up", "Escape"):
            return
        self._client_cb["values"] = self._matches()

    def _select_match(self):
        matches = self._matches()
        if len(matches) == 1:
            self._client.set(matches[0])

    def _accept(self):
        value = self._client.get()
        codigo = ""
        empresa = None
        if value != "Sin cliente":
            empresa = next(
                (item for item in self._empresas if self._company_label(item) == value), None,
            )
            if not empresa:
                matches = self._matches()
                if len(matches) == 1:
                    value = matches[0]
                    self._client.set(value)
                    empresa = next(
                        (item for item in self._empresas if self._company_label(item) == value), None,
                    )
            if not empresa:
                messagebox.showwarning(
                    "Firma", "Selecciona un cliente de las coincidencias.", parent=self,
                )
                return
            codigo = str(empresa.get("codigo") or "")
        self.result = {
            "codigo": codigo,
            "ejercicio": datetime.now().year,
            "nombre": str((empresa or {}).get("nombre") or ""),
            "email": str((empresa or {}).get("email") or ""),
            "telefono": str((empresa or {}).get("telefono") or ""),
        }
        self.destroy()
