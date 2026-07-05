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
import tkinter as tk
from datetime import date, datetime
from tkinter import filedialog, messagebox, ttk

from utils.crypto_utils import cifrar_password
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


class UICertificados(ttk.Frame):
    """Panel del certificado digital (unico) de una empresa."""

    def __init__(self, master, gestor, codigo, session=None):
        super().__init__(master)
        self._gestor = gestor
        self._codigo = codigo
        self._session = session
        self._cert = None
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
            ("ruta",      "Fichero"),
            ("clave",     "Contrasena guardada"),
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
            for v in self._vals.values():
                v.configure(text="-", fg="#0f172a")
            self._vals["estado"].configure(text="Sin certificado", fg=_SUB)
            self._btn_set.configure(text="Seleccionar certificado...")
            self._btn_del.configure(state="disabled")
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
        self._vals["ruta"].configure(text=c.get("ruta_archivo", "") or "-")
        self._vals["clave"].configure(text="Si" if c.get("password_cifrada") else "No")
        self._btn_set.configure(text="Reemplazar certificado...")
        self._btn_del.configure(state="normal")

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
            "password_cifrada": cifrar_password(password),
            "activo":          1,
        }
        # Mantener un unico registro: reutilizar el id existente si lo hay.
        if self._cert and self._cert.get("id"):
            cert["id"] = self._cert["id"]

        try:
            self._gestor.upsert_notif_certificado(cert)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return

        # Aviso segun vigencia detectada.
        lbl, tag = _vigencia(cert["fecha_caducidad"])
        if tag == "caducado":
            messagebox.showwarning(
                "Certificado caducado",
                f"El certificado de '{cert['nombre']}' esta CADUCADO "
                f"(caduco el {cert['fecha_caducidad']}).\n\nGuardado, pero debes renovarlo.",
                parent=self.winfo_toplevel(),
            )
        elif tag == "por_vencer":
            messagebox.showwarning(
                "Certificado por vencer",
                f"El certificado de '{cert['nombre']}' {lbl.lower()}.",
                parent=self.winfo_toplevel(),
            )
        else:
            messagebox.showinfo(
                "Certificado guardado",
                f"Titular: {cert['nombre']}\nNIF: {cert['nif_titular']}\n"
                f"Emitido: {cert['fecha_emision']}\nCaduca: {cert['fecha_caducidad']}",
                parent=self.winfo_toplevel(),
            )
        self.refresh()

    def _on_eliminar(self):
        if not self._cert:
            return
        if not messagebox.askyesno(
            "Eliminar certificado",
            f"Eliminar el certificado de '{self._cert.get('nombre')}'?",
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            self._gestor.eliminar_notif_certificado(self._codigo, self._cert["id"])
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return
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
        ttk.Label(frm, text="(Las propiedades se detectan automaticamente al guardar.)",
                  foreground="#64748b").grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        btns = ttk.Frame(self, padding=(16, 8))
        btns.pack(fill="x")
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="Guardar", command=self._on_ok).pack(side="right")

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
