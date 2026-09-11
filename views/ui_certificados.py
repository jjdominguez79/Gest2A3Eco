"""
Vista: Certificado Digital del cliente (uno solo por empresa).

Cada cliente tiene UN unico certificado digital. Al seleccionar el fichero .pfx
y su contrasena, la aplicacion abre el certificado y detecta automaticamente sus
propiedades (titular, NIF, fecha de emision y de caducidad); el usuario no las
teclea. Si el certificado esta caducado (o proximo a caducar), se avisa.

Requiere la libreria 'cryptography' para leer el .pfx.
"""
from __future__ import annotations

import os
import re
import threading
import tkinter as tk
from datetime import date, datetime
from tkinter import filedialog, messagebox, ttk

from views.notificaciones_theme import *  # noqa: F401,F403


def _vigencia(fecha_caducidad_str):
    """Devuelve (label, tag) segun la fecha de caducidad."""
    if not fecha_caducidad_str:
        return "Sin fecha", "neutro"
    try:
        cad = datetime.strptime(str(fecha_caducidad_str)[:10], "%Y-%m-%d").date()
        dias = (cad - date.today()).days
        if dias < 0:
            return "CADUCADO", "caducado"
        if dias <= 30:
            return f"Vence en {dias} dias", "por_vencer"
        return f"Vigente ({dias} dias)", "vigente"
    except ValueError:
        return str(fecha_caducidad_str), "neutro"


def leer_metadatos_pfx(ruta, password):
    """Abre un .pfx/.p12 y devuelve (info, error).

    info = {cn, nif, fecha_emision, fecha_caducidad}  o  None si error.
    """
    try:
        from services.aapp.cert_store import CertStore, CertMaterial
    except Exception as exc:
        return None, f"No se pudo cargar el lector de certificados: {exc}"
    store = CertStore.__new__(CertStore)  # sin gestor: solo lectura
    mat = CertMaterial(cert_id="", nombre="", nif_titular=None,
                       ruta_archivo=ruta, password=password or None)
    try:
        return store.info(mat), None
    except Exception as exc:
        return None, str(exc)


def _normalizar_nif(valor) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(valor or "").upper())


class UICertificados(ttk.Frame):
    """Panel del certificado digital (unico) de una empresa."""

    def __init__(self, master, gestor, codigo, session=None):
        super().__init__(master)
        self._gestor = gestor
        self._codigo = codigo
        self._session = session
        self._cert = None
        self._estado_central_seq = 0
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build
    def _build(self):
        hdr = tk.Frame(self, bg=_HDR_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="\U0001F510  Certificado Digital", bg=_HDR_BG, fg=_HDR_FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left", padx=16, pady=10)
        tk.Label(hdr, text="Un unico certificado por cliente (autodeteccion de propiedades)",
                 bg=_HDR_BG, fg=_HDR_SUB, font=("Segoe UI", 9)).pack(side="left", pady=10)

        self._banner = tk.Frame(self, bg=_WARNING)
        self._lbl_banner = tk.Label(self._banner, text="", bg=_WARNING, fg="white",
                                    font=("Segoe UI", 9, "bold"), anchor="w")
        self._lbl_banner.pack(side="left", padx=12, pady=5)

        # Panel de propiedades (solo lectura)
        card = tk.Frame(self, bg=_BG)
        card.pack(fill="x", padx=16, pady=12)
        self._vals = {}
        campos = [
            ("titular",   "Titular"),
            ("nif",       "NIF"),
            ("emision",   "Fecha de emision"),
            ("caducidad", "Fecha de caducidad"),
            ("estado",    "Estado"),
            ("ruta",      "Fichero local"),
            ("clave",     "Contrasena local"),
            ("central",   "Copia segura en Azure"),
        ]
        for i, (key, label) in enumerate(campos):
            tk.Label(card, text=label + ":", bg=_BG, fg=_SUB, font=("Segoe UI", 9, "bold"),
                     anchor="e", width=20).grid(row=i, column=0, sticky="e", padx=(0, 10), pady=3)
            val = tk.Label(card, text="-", bg=_BG, fg="#0f172a", font=("Segoe UI", 9),
                           anchor="w", justify="left", wraplength=520)
            val.grid(row=i, column=1, sticky="w", pady=3)
            self._vals[key] = val

        # Botones
        tb = tk.Frame(self, bg=_BG)
        tb.pack(fill="x", padx=16, pady=(0, 10))
        btn = dict(font=("Segoe UI", 9), relief="flat", cursor="hand2", padx=12, pady=5)
        self._btn_set = tk.Button(tb, text="Seleccionar certificado...", bg=_PRIMARY, fg="white",
                                  command=self._on_seleccionar, **btn)
        self._btn_set.pack(side="left", padx=(0, 6))
        self._btn_del = tk.Button(tb, text="Eliminar", bg=_DANGER, fg="white",
                                  command=self._on_eliminar, state="disabled", **btn)
        self._btn_del.pack(side="left", padx=(0, 6))
        self._btn_cloud = tk.Button(
            tb,
            text="Verificar custodia en Azure",
            bg="#0f766e",
            fg="white",
            command=lambda: self._consultar_estado_central(avisar=True),
            state="disabled",
            **btn,
        )
        self._btn_cloud.pack(side="left", padx=(0, 6))
        tk.Button(tb, text="↻ Actualizar", bg="#64748b", fg="white",
                  command=self.refresh, **btn).pack(side="left")

    # ------------------------------------------------------------------ refresh
    def refresh(self):
        rows = self._gestor.listar_notif_certificados(self._codigo)
        self._cert = rows[0] if rows else None

        # Limpieza de duplicados historicos: dejar solo el primero.
        for extra in rows[1:]:
            try:
                self._gestor.eliminar_notif_certificado(self._codigo, extra["id"])
            except Exception:
                pass

        if not self._cert:
            self._estado_central_seq += 1
            for v in self._vals.values():
                v.configure(text="-", fg="#0f172a")
            self._vals["estado"].configure(text="Sin certificado", fg=_SUB)
            self._vals["central"].configure(text="Sin comprobar", fg=_SUB)
            self._btn_set.configure(text="Seleccionar certificado...")
            self._btn_del.configure(state="disabled")
            self._btn_cloud.configure(state="disabled")
            self._banner.pack_forget()
            return

        c = self._cert
        lbl, tag = _vigencia(c.get("fecha_caducidad"))
        color = {"vigente": _SUCCESS, "por_vencer": _WARNING,
                 "caducado": _DANGER, "neutro": _SUB}.get(tag, _SUB)
        self._vals["titular"].configure(text=c.get("nombre", "") or "-")
        self._vals["nif"].configure(text=c.get("nif_titular", "") or "-")
        self._vals["emision"].configure(text=c.get("fecha_emision", "") or "-")
        self._vals["caducidad"].configure(text=c.get("fecha_caducidad", "") or "-")
        self._vals["estado"].configure(text=lbl, fg=color)
        self._vals["ruta"].configure(
            text=c.get("ruta_archivo", "") or "No se conserva (custodia en Azure)",
        )
        self._vals["clave"].configure(text="Si" if c.get("password_cifrada") else "No se conserva")
        self._vals["central"].configure(text="Comprobando...", fg=_SUB)
        self._btn_set.configure(text="Reemplazar certificado...")
        self._btn_del.configure(state="normal")
        self._btn_cloud.configure(
            state="normal",
            text="Verificar custodia en Azure",
            command=lambda: self._consultar_estado_central(avisar=True),
        )

        if tag == "caducado":
            self._lbl_banner.configure(bg=_DANGER, text="⚠  Certificado CADUCADO. Debes renovarlo para poder acceder a los organismos.")
            self._banner.configure(bg=_DANGER)
            self._banner.pack(fill="x", after=self.winfo_children()[0])
        elif tag == "por_vencer":
            self._lbl_banner.configure(bg=_WARNING, text=f"⚠  Certificado {lbl.lower()}. Conviene renovarlo pronto.")
            self._banner.configure(bg=_WARNING)
            self._banner.pack(fill="x", after=self.winfo_children()[0])
        else:
            self._banner.pack_forget()
        self._consultar_estado_central()

    def _consultar_estado_central(self, *, avisar=False):
        """Consulta Azure sin bloquear la interfaz ni exponer el PFX."""
        self._estado_central_seq += 1
        seq = self._estado_central_seq
        if avisar:
            self._vals["central"].configure(text="Verificando custodia...", fg=_SUB)
            self._btn_cloud.configure(state="disabled", text="Verificando...")

        def _worker():
            try:
                from services.backend_client_service import BackendClientService

                result = BackendClientService().get_client_certificate_status(
                    company_code=self._codigo,
                )
                self.after(
                    0,
                    lambda: self._estado_central_fin(
                        seq, result, None, avisar=avisar,
                    ),
                )
            except Exception as exc:
                self.after(
                    0,
                    lambda error=exc: self._estado_central_fin(
                        seq, None, error, avisar=avisar,
                    ),
                )

        threading.Thread(target=_worker, daemon=True).start()

    def _estado_central_fin(self, seq, result, error, *, avisar=False):
        if seq != self._estado_central_seq or not self.winfo_exists():
            return
        self._btn_cloud.configure(
            state="normal",
            text="Verificar custodia en Azure",
            command=lambda: self._consultar_estado_central(avisar=True),
        )
        if error is not None:
            self._vals["central"].configure(text="No se pudo comprobar", fg=_WARNING)
            if avisar:
                messagebox.showerror(
                    "Custodia en Azure",
                    "No se ha podido verificar la copia del certificado en Azure."
                    f"\n\nDetalle: {error}",
                    parent=self.winfo_toplevel(),
                )
            return
        if not result or not result.get("configured"):
            self._vals["central"].configure(
                text="No guardado; vuelve a seleccionar el PFX",
                fg=_DANGER,
            )
            self._btn_cloud.configure(
                text="Seleccionar PFX para Azure...",
                command=self._on_seleccionar,
            )
            if avisar:
                messagebox.showwarning(
                    "Custodia en Azure",
                    "Azure no tiene una copia del certificado de este cliente. "
                    "Selecciona de nuevo el fichero PFX para guardarlo.",
                    parent=self.winfo_toplevel(),
                )
            return
        try:
            self._eliminar_material_local_confirmado()
        except Exception:
            # La copia central sigue siendo valida; una limpieza local fallida
            # se reintentara en la siguiente carga de la pantalla.
            pass
        version = result.get("version")
        suffix = f" (version {version})" if version else ""
        estado = "Caducado" if result.get("status") == "expired" else "Guardado"
        color = _DANGER if result.get("status") == "expired" else _SUCCESS
        self._vals["central"].configure(text=estado + suffix, fg=color)
        if avisar:
            if result.get("status") == "expired":
                messagebox.showwarning(
                    "Custodia verificada",
                    f"Azure confirma que conserva el certificado (version {version or '-'}), "
                    "pero esta caducado.",
                    parent=self.winfo_toplevel(),
                )
            else:
                messagebox.showinfo(
                    "Custodia verificada",
                    f"Azure confirma que conserva correctamente el certificado cifrado "
                    f"(version {version or '-'}).",
                    parent=self.winfo_toplevel(),
                )

    def _eliminar_material_local_confirmado(self):
        """Borra ruta y clave locales solo tras confirmar la copia de Azure."""
        if not self._cert or not (
            self._cert.get("ruta_archivo") or self._cert.get("password_cifrada")
        ):
            return
        limpio = dict(self._cert)
        limpio["ruta_archivo"] = None
        limpio["password_cifrada"] = None
        self._gestor.upsert_notif_certificado(limpio)
        self._cert = limpio
        self._vals["ruta"].configure(text="No se conserva (custodia en Azure)")
        self._vals["clave"].configure(text="No se conserva")

    # ------------------------------------------------------------------ eventos
    def _on_seleccionar(self):
        dlg = _SeleccionCertDialog(self.winfo_toplevel())
        if not dlg.result:
            return
        ruta, password = dlg.result["ruta"], dlg.result["password"]

        info, error = leer_metadatos_pfx(ruta, password)
        if error or info is None:
            messagebox.showerror(
                "No se pudo leer el certificado",
                "Revisa el fichero y la contrasena.\n\nDetalle: " + (error or "desconocido"),
                parent=self.winfo_toplevel(),
            )
            return

        empresa = self._gestor.get_empresa(self._codigo) or {}
        nif_empresa = _normalizar_nif(empresa.get("cif"))
        nif_certificado = _normalizar_nif(info.get("nif"))
        if nif_empresa and nif_certificado and nif_empresa != nif_certificado:
            if not messagebox.askyesno(
                "El titular no coincide",
                f"El cliente tiene NIF {nif_empresa}, pero el certificado pertenece a "
                f"{nif_certificado}.\n\n"
                "Continua solo si es un certificado de representante autorizado para "
                "este cliente. Guardarlo de todos modos?",
                parent=self.winfo_toplevel(),
            ):
                return

        tipo = "PFX" if ruta.lower().endswith((".pfx", ".p12")) else "OTRO"
        cert = {
            "codigo_empresa":  self._codigo,
            "nombre":          info.get("cn") or "Certificado",
            "nif_titular":     info.get("nif") or "",
            "tipo":            tipo,
            "ruta_archivo":    ruta,
            "fecha_emision":   info.get("fecha_emision"),
            "fecha_caducidad": info.get("fecha_caducidad"),
            "notas":           None,
            # La contrasena viaja directamente al backend y nunca se persiste
            # en la base de datos del escritorio.
            "password_cifrada": None,
            "activo":          1,
        }
        # Mantener un unico registro: reutilizar el id existente si lo hay.
        if self._cert and self._cert.get("id"):
            cert["id"] = self._cert["id"]

        self._iniciar_subida_central(
            cert=cert,
            password=password,
            automatico=True,
        )

    def _on_eliminar(self):
        if not self._cert:
            return
        if not messagebox.askyesno(
            "Eliminar certificado",
            f"Eliminar el certificado de '{self._cert.get('nombre')}'?\n\n"
            "Se eliminara tanto del puesto como de la custodia cifrada en Azure. "
            "El cliente dejara de poder solicitar certificados hasta configurar otro.",
            parent=self.winfo_toplevel(),
        ):
            return
        cert = dict(self._cert)
        self._estado_central_seq += 1
        self._vals["central"].configure(text="Eliminando...", fg=_WARNING)
        self._btn_set.configure(state="disabled")
        self._btn_del.configure(state="disabled")
        self._btn_cloud.configure(state="disabled")

        def _worker():
            try:
                from services.backend_client_service import BackendClientService

                BackendClientService().delete_client_certificate(company_code=self._codigo)
                self.after(0, lambda: self._eliminacion_fin(cert, None))
            except Exception as exc:
                self.after(0, lambda error=exc: self._eliminacion_fin(cert, error))

        threading.Thread(target=_worker, daemon=True).start()

    def _eliminacion_fin(self, cert, error):
        if error is not None:
            self._btn_set.configure(state="normal")
            self._btn_del.configure(state="normal")
            self._btn_cloud.configure(state="normal")
            self._vals["central"].configure(text="No se pudo eliminar", fg=_DANGER)
            messagebox.showerror(
                "Eliminar certificado",
                "No se ha eliminado el certificado porque Azure no confirmo la operacion."
                f"\n\nDetalle: {error}",
                parent=self.winfo_toplevel(),
            )
            return
        try:
            self._gestor.eliminar_notif_certificado(self._codigo, cert["id"])
        except Exception as exc:
            messagebox.showerror(
                "Eliminar certificado",
                "La copia de Azure se elimino, pero no se pudo borrar el registro del puesto."
                f"\n\nDetalle: {exc}",
                parent=self.winfo_toplevel(),
            )
            self.refresh()
            return
        self.refresh()
        messagebox.showinfo(
            "Certificado eliminado",
            "El certificado se ha eliminado del puesto y de Azure.",
            parent=self.winfo_toplevel(),
        )

    def _iniciar_subida_central(self, *, cert, password, automatico=True):
        self._estado_central_seq += 1
        self._vals["central"].configure(text="Guardando...", fg=_WARNING)
        self._btn_set.configure(state="disabled")
        self._btn_del.configure(state="disabled")
        self._btn_cloud.configure(state="disabled", text="Guardando en Azure...")

        def _worker():
            try:
                from services.backend_client_service import BackendClientService

                result = BackendClientService().upload_client_certificate(
                    company_code=self._codigo,
                    pfx_path=cert["ruta_archivo"],
                    password=password,
                )
                self.after(
                    0,
                    lambda: self._subida_central_fin(
                        result, None, cert=cert, automatico=automatico,
                    ),
                )
            except Exception as exc:
                self.after(
                    0,
                    lambda error=exc: self._subida_central_fin(
                        None, error, cert=cert, automatico=automatico,
                    ),
                )

        threading.Thread(target=_worker, daemon=True).start()

    def _subida_central_fin(self, result, error, *, cert, automatico=True):
        self._btn_set.configure(state="normal")
        self._btn_cloud.configure(
            state="normal",
            text="Verificar custodia en Azure",
            command=lambda: self._consultar_estado_central(avisar=True),
        )
        if error is not None:
            self._btn_del.configure(state="normal" if self._cert else "disabled")
            self._vals["central"].configure(text="Error al guardar", fg=_DANGER)
            messagebox.showerror(
                "Certificado central",
                "No se pudo guardar el certificado cifrado en Azure. "
                "No se ha conservado ninguna copia nueva en la aplicacion."
                + f"\n\nDetalle: {error}",
                parent=self.winfo_toplevel(),
            )
            return
        limpio = dict(cert)
        limpio["ruta_archivo"] = None
        limpio["password_cifrada"] = None
        try:
            limpio["id"] = self._gestor.upsert_notif_certificado(limpio)
        except Exception as exc:
            messagebox.showerror(
                "Certificado central",
                "El certificado se guardo correctamente en Azure, pero no se pudieron "
                f"actualizar sus metadatos locales.\n\nDetalle: {exc}",
                parent=self.winfo_toplevel(),
            )
            self.refresh()
            return
        self._cert = limpio
        self._btn_del.configure(state="normal")
        version = result.get("version")
        self._vals["central"].configure(
            text=f"Guardado (version {version})" if version else "Guardado",
            fg=_SUCCESS,
        )
        warning = (
            "\n\nAviso: el NIF detectado no coincide con la empresa. "
            "Comprueba que sea un certificado de representante autorizado."
            if result.get("tax_id_warning") else ""
        )
        if automatico:
            lbl, tag = _vigencia(limpio.get("fecha_caducidad"))
            detalle = (
                f"Titular: {limpio['nombre']}\nNIF: {limpio['nif_titular']}\n"
                f"Caduca: {limpio['fecha_caducidad']}\n"
                f"Copia segura en Azure: version {version or '-'}"
            )
            if tag == "caducado":
                messagebox.showwarning(
                    "Certificado caducado",
                    detalle + "\n\nEl certificado esta CADUCADO y no podra utilizarse." + warning,
                    parent=self.winfo_toplevel(),
                )
            elif tag == "por_vencer":
                messagebox.showwarning(
                    "Certificado por vencer",
                    detalle + f"\n\nEl certificado {lbl.lower()}." + warning,
                    parent=self.winfo_toplevel(),
                )
            else:
                messagebox.showinfo(
                    "Certificado guardado",
                    detalle + "\n\nYa esta preparado para la app y el worker." + warning,
                    parent=self.winfo_toplevel(),
                )
        self.refresh()


# ── Dialogo de seleccion (fichero + contrasena) ─────────────────────────────
class _SeleccionCertDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Seleccionar certificado")
        self.resizable(False, False)
        self.result = None
        self._var_ruta = tk.StringVar()
        self._var_pwd = tk.StringVar()
        self._build()
        self.grab_set()
        self.transient(parent)
        self.wait_window()

    def _build(self):
        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Fichero del certificado (.pfx / .p12)").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        ttk.Entry(frm, textvariable=self._var_ruta, width=46).grid(row=1, column=0, sticky="w")
        ttk.Button(frm, text="...", width=3, command=self._browse).grid(row=1, column=1, padx=(4, 0))
        ttk.Label(frm, text="Contrasena del certificado").grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 4))
        self._ent_pwd = ttk.Entry(frm, textvariable=self._var_pwd, width=30, show="*")
        self._ent_pwd.grid(row=3, column=0, sticky="w")
        ttk.Label(
            frm,
            text=(
                "Las propiedades se detectan automaticamente. Al guardar, el PFX se envia "
                "por HTTPS y se custodia cifrado en Azure."
            ),
            foreground="#64748b",
            wraplength=430,
            justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        btns = ttk.Frame(self, padding=(16, 8))
        btns.pack(fill="x")
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="Guardar y proteger", command=self._on_ok).pack(side="right")

    def _browse(self):
        path = filedialog.askopenfilename(
            parent=self, title="Seleccionar certificado",
            filetypes=[("Certificados", "*.pfx *.p12"), ("Todos", "*.*")],
        )
        if path:
            self._var_ruta.set(path)

    def _on_ok(self):
        ruta = self._var_ruta.get().strip()
        if not ruta or not os.path.isfile(ruta):
            messagebox.showerror("Gest2A3Eco", "Selecciona un fichero de certificado valido.", parent=self)
            return
        self.result = {"ruta": ruta, "password": self._var_pwd.get()}
        self.destroy()
