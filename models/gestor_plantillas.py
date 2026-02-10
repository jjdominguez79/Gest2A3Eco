import json, os, tempfile, time
from pathlib import Path
import portalocker

DEFAULT_JSON = '{"empresas":[],"bancos":[],"facturas_emitidas":[],"facturas_recibidas":[],"facturas_emitidas_docs":[],"terceros":[],"terceros_empresas":[]}'

def _ej_val(v):
    try:
        return int(v)
    except Exception:
        return None

class GestorPlantillas:
    
    def __init__(self, path_json: Path):
        self.path = Path(path_json)
        # lockfile separado para evitar bloquear el propio JSON
        self.lock_path = Path(str(self.path) + ".lock")
        self.data = {}
        self._load()

    def _atomic_write(self, text: str):
        """Escritura atómica vía archivo temporal + replace, con pequeño retry en Windows."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmppath = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmpf:
                tmpf.write(text)
                tmpf.flush()
                os.fsync(tmpf.fileno())
            # Retry por si otro proceso toca el archivo justo en ese instante (AV, indexer, etc.)
            last_err = None
            for _ in range(10):
                try:
                    os.replace(tmppath, self.path)
                    last_err = None
                    break
                except PermissionError as e:
                    last_err = e
                    time.sleep(0.05)
            if last_err is not None:
                raise last_err
        finally:
            try:
                if os.path.exists(tmppath):
                    os.remove(tmppath)
            except Exception:
                pass

    def _ensure_exists(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            # Crear con contenido por defecto
            self._atomic_write(DEFAULT_JSON)

    def _load(self):
        """Carga sin bloquear el JSON; si quieres lectura consistente, opcionalmente bloquea el lockfile en modo SH."""
        self._ensure_exists()
        # Lectura simple: no abrimos el JSON en modo bloqueado para permitir replace atómico de otros hilos/procesos
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                txt = f.read()
        except FileNotFoundError:
            # si alguien lo reemplazó justo ahora
            self._ensure_exists()
            with open(self.path, "r", encoding="utf-8") as f:
                txt = f.read()
        self.data = json.loads(txt or "{}")
        # Garantiza presencia de nuevas claves para compatibilidad hacia atrás
        self.data.setdefault("empresas", [])
        self.data.setdefault("bancos", [])
        self.data.setdefault("facturas_emitidas", [])
        self.data.setdefault("facturas_recibidas", [])
        self.data.setdefault("facturas_emitidas_docs", [])
        self.data.setdefault("terceros", [])
        self.data.setdefault("terceros_empresas", [])

    def save(self):
        """Bloqueo exclusivo en lockfile (no en el JSON) + escritura atómica del JSON."""
        new_text = json.dumps(self.data, ensure_ascii=False, indent=2)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusivo sobre el lockfile; así el JSON está libre para replace
        with portalocker.Lock(str(self.lock_path), mode="a", flags=portalocker.LOCK_EX):
            self._atomic_write(new_text)

    # ---------- EMPRESAS ----------
    def listar_empresas(self):
        return self.data.get("empresas", [])

    def get_empresa(self, codigo: str, ejercicio: int | None = None):
        if ejercicio is None:
            return next(
                (e for e in self.data.get("empresas", []) if e.get("codigo") == codigo),
                None,
            )
        return next(
            (
                e
                for e in self.data.get("empresas", [])
                if e.get("codigo") == codigo and int(e.get("ejercicio", 0)) == int(ejercicio)
            ),
            None,
        )

    def upsert_empresa(self, emp: dict):
        arr = self.data.setdefault("empresas", [])
        emp_eje_raw = emp.get("ejercicio")
        for i, e in enumerate(arr):
            mismo_codigo = e.get("codigo") == emp.get("codigo")
            eje_e = e.get("ejercicio")
            if emp_eje_raw is None and eje_e is None and mismo_codigo:
                arr[i] = emp; self.save(); return
            if emp_eje_raw is not None and mismo_codigo:
                try:
                    if int(eje_e or 0) == int(emp_eje_raw):
                        arr[i] = emp; self.save(); return
                except Exception:
                    pass
        arr.append(emp)
        self.save()

    def copiar_empresa(self, codigo_origen: str, ejercicio_origen: int, nueva_empresa: dict):
        """Crea una empresa nueva copiando terceros y plantillas del ejercicio origen."""
        if not codigo_origen:
            raise ValueError("Codigo de origen requerido")
        if ejercicio_origen is None:
            raise ValueError("Ejercicio de origen requerido")
        if not nueva_empresa.get("codigo"):
            raise ValueError("Codigo de destino requerido")
        if nueva_empresa.get("ejercicio") is None:
            raise ValueError("Ejercicio de destino requerido")
        origen = self.get_empresa(codigo_origen, ejercicio_origen)
        if not origen:
            raise ValueError(f"No existe la empresa {codigo_origen} ({ejercicio_origen})")
        if self.get_empresa(nueva_empresa["codigo"], nueva_empresa.get("ejercicio")):
            raise ValueError(f"Ya existe una empresa con codigo {nueva_empresa['codigo']} y ejercicio {nueva_empresa.get('ejercicio')}")

        empresas = self.data.setdefault("empresas", [])
        empresas.append(nueva_empresa)

        dest_eje = nueva_empresa.get("ejercicio")

        # Copiar plantillas (bancos, emitidas, recibidas) del ejercicio origen o sin ejercicio
        def copy_list(origen_list, target_list, key_builder, mutate):
            existing = set()
            for item in target_list:
                existing.add(key_builder(item))
            for item in origen_list:
                nuevo = mutate(item)
                k = key_builder(nuevo)
                if k in existing:
                    continue
                target_list.append(nuevo)
                existing.add(k)

        bancos_origen = [
            b for b in self.data.get("bancos", [])
            if b.get("codigo_empresa")==codigo_origen and (b.get("ejercicio") is None or _ej_val(b.get("ejercicio"))==_ej_val(ejercicio_origen))
        ]
        if bancos_origen:
            bancos_dest = self.data.setdefault("bancos", [])
            copy_list(
                bancos_origen,
                bancos_dest,
                lambda it: (it.get("codigo_empresa"), it.get("banco"), _ej_val(it.get("ejercicio"))),
                lambda it: dict(it, codigo_empresa=nueva_empresa["codigo"], ejercicio=dest_eje),
            )

        emitidas_origen = [
            b for b in self.data.get("facturas_emitidas", [])
            if b.get("codigo_empresa")==codigo_origen and (b.get("ejercicio") is None or _ej_val(b.get("ejercicio"))==_ej_val(ejercicio_origen))
        ]
        if emitidas_origen:
            emitidas_dest = self.data.setdefault("facturas_emitidas", [])
            copy_list(
                emitidas_origen,
                emitidas_dest,
                lambda it: (it.get("codigo_empresa"), it.get("nombre"), _ej_val(it.get("ejercicio"))),
                lambda it: dict(it, codigo_empresa=nueva_empresa["codigo"], ejercicio=dest_eje),
            )

        recibidas_origen = [
            b for b in self.data.get("facturas_recibidas", [])
            if b.get("codigo_empresa")==codigo_origen and (b.get("ejercicio") is None or _ej_val(b.get("ejercicio"))==_ej_val(ejercicio_origen))
        ]
        if recibidas_origen:
            recibidas_dest = self.data.setdefault("facturas_recibidas", [])
            copy_list(
                recibidas_origen,
                recibidas_dest,
                lambda it: (it.get("codigo_empresa"), it.get("nombre"), _ej_val(it.get("ejercicio"))),
                lambda it: dict(it, codigo_empresa=nueva_empresa["codigo"], ejercicio=dest_eje),
            )

        origen_terceros = [
            t for t in self.data.get("terceros_empresas", [])
            if t.get("codigo_empresa")==codigo_origen and (t.get("ejercicio") is None or int(t.get("ejercicio", 0))==int(ejercicio_origen))
        ]
        if origen_terceros:
            rels = self.data.setdefault("terceros_empresas", [])
            existing = set()
            for r in rels:
                try:
                    existing.add((r.get("codigo_empresa"), str(r.get("tercero_id")), int(r.get("ejercicio", 0)) if r.get("ejercicio") is not None else None))
                except Exception:
                    existing.add((r.get("codigo_empresa"), str(r.get("tercero_id")), None))
            for rel in origen_terceros:
                nuevo_rel = dict(rel)
                nuevo_rel["codigo_empresa"] = nueva_empresa["codigo"]
                nuevo_rel["ejercicio"] = nueva_empresa.get("ejercicio")
                try:
                    eje_key = int(nuevo_rel.get("ejercicio", 0)) if nuevo_rel.get("ejercicio") is not None else None
                except Exception:
                    eje_key = None
                key = (nuevo_rel.get("codigo_empresa"), str(nuevo_rel.get("tercero_id")), eje_key)
                if key in existing:
                    continue
                rels.append(nuevo_rel)
                existing.add(key)

        self.save()

    def eliminar_empresa(self, codigo: str, ejercicio: int):
        """Elimina la empresa y todos sus datos asociados al ejercicio indicado."""
        eje_key = _ej_val(ejercicio)
        # Empresas
        self.data["empresas"] = [
            e for e in self.data.get("empresas", [])
            if not (e.get("codigo")==codigo and (_ej_val(e.get("ejercicio"))==eje_key))
        ]
        # Plantillas
        self.data["bancos"] = [
            b for b in self.data.get("bancos", [])
            if not (b.get("codigo_empresa")==codigo and (_ej_val(b.get("ejercicio"))==eje_key or b.get("ejercicio") is None and eje_key is None))
        ]
        self.data["facturas_emitidas"] = [
            p for p in self.data.get("facturas_emitidas", [])
            if not (p.get("codigo_empresa")==codigo and (_ej_val(p.get("ejercicio"))==eje_key or p.get("ejercicio") is None and eje_key is None))
        ]
        self.data["facturas_recibidas"] = [
            p for p in self.data.get("facturas_recibidas", [])
            if not (p.get("codigo_empresa")==codigo and (_ej_val(p.get("ejercicio"))==eje_key or p.get("ejercicio") is None and eje_key is None))
        ]
        # Facturas emitidas docs
        self.data["facturas_emitidas_docs"] = [
            f for f in self.data.get("facturas_emitidas_docs", [])
            if not (f.get("codigo_empresa")==codigo and (_ej_val(f.get("ejercicio"))==eje_key or f.get("ejercicio") is None and eje_key is None))
        ]
        # Terceros-empresa
        self.data["terceros_empresas"] = [
            t for t in self.data.get("terceros_empresas", [])
            if not (t.get("codigo_empresa")==codigo and (_ej_val(t.get("ejercicio"))==eje_key or t.get("ejercicio") is None and eje_key is None))
        ]
        self.save()

    # ---------- BANCOS ----------
    def listar_bancos(self, codigo_empresa: str, ejercicio: int):
        return [
            b for b in self.data.get("bancos", [])
            if b.get("codigo_empresa")==codigo_empresa and (b.get("ejercicio") is None or int(b.get("ejercicio", 0))==int(ejercicio))
        ]

    def upsert_banco(self, plantilla):
        arr = self.data.setdefault("bancos", [])
        eje_key = _ej_val(plantilla.get("ejercicio"))
        key = (plantilla.get("codigo_empresa"), plantilla.get("banco"), eje_key)
        for i,p in enumerate(arr):
            if (
                p.get("codigo_empresa")==key[0]
                and p.get("banco")==key[1]
                and (p.get("ejercicio") is None or (key[2] is None and p.get("ejercicio") is None) or _ej_val(p.get("ejercicio"))==key[2])
            ):
                arr[i] = plantilla
                self.save()
                return
        arr.append(plantilla)
        self.save()

    def eliminar_banco(self, codigo_empresa: str, banco: str, ejercicio: int):
        eje_key = _ej_val(ejercicio)
        arr = [
            p for p in self.data.get("bancos", [])
            if not (
                p.get("codigo_empresa")==codigo_empresa
                and p.get("banco")==banco
                and (p.get("ejercicio") is None or (eje_key is None and p.get("ejercicio") is None) or _ej_val(p.get("ejercicio"))==eje_key)
            )
        ]
        self.data["bancos"] = arr
        self.save()

    # ---------- EMITIDAS ----------
    def listar_emitidas(self, codigo_empresa: str, ejercicio: int):
        return [
            b for b in self.data.get("facturas_emitidas", [])
            if b.get("codigo_empresa")==codigo_empresa and (b.get("ejercicio") is None or int(b.get("ejercicio", 0))==int(ejercicio))
        ]

    def upsert_emitida(self, plantilla):
        arr = self.data.setdefault("facturas_emitidas", [])
        eje_key = _ej_val(plantilla.get("ejercicio"))
        key = (plantilla.get("codigo_empresa"), plantilla.get("nombre"), eje_key)
        for i,p in enumerate(arr):
            if (
                p.get("codigo_empresa")==key[0]
                and p.get("nombre")==key[1]
                and (p.get("ejercicio") is None or (key[2] is None and p.get("ejercicio") is None) or _ej_val(p.get("ejercicio"))==key[2])
            ):
                arr[i] = plantilla
                self.save()
                return
        arr.append(plantilla)
        self.save()

    def eliminar_emitida(self, codigo_empresa: str, nombre: str, ejercicio: int):
        eje_key = _ej_val(ejercicio)
        arr = [
            p for p in self.data.get("facturas_emitidas", [])
            if not (
                p.get("codigo_empresa")==codigo_empresa
                and p.get("nombre")==nombre
                and (p.get("ejercicio") is None or (eje_key is None and p.get("ejercicio") is None) or _ej_val(p.get("ejercicio"))==eje_key)
            )
        ]
        self.data["facturas_emitidas"] = arr
        self.save()

    # ---------- FACTURAS EMITIDAS (DOCUMENTOS) ----------
    def listar_facturas_emitidas(self, codigo_empresa: str, ejercicio: int):
        return [
            f for f in self.data.get("facturas_emitidas_docs", [])
            if f.get("codigo_empresa")==codigo_empresa and (f.get("ejercicio") is None or int(f.get("ejercicio", 0))==int(ejercicio))
        ]

    def upsert_factura_emitida(self, factura: dict):
        arr = self.data.setdefault("facturas_emitidas_docs", [])
        fid = factura.get("id") or str(int(time.time() * 1000))
        factura["id"] = fid
        eje_key = _ej_val(factura.get("ejercicio"))
        key = (factura.get("codigo_empresa"), fid, eje_key)
        for i, f in enumerate(arr):
            if (
                f.get("codigo_empresa")==key[0]
                and f.get("id")==key[1]
                and (f.get("ejercicio") is None or (key[2] is None and f.get("ejercicio") is None) or _ej_val(f.get("ejercicio"))==key[2])
            ):
                arr[i] = factura
                self.save()
                return fid
        arr.append(factura)
        self.save()
        return fid

    def eliminar_factura_emitida(self, codigo_empresa: str, factura_id: str, ejercicio: int):
        eje_key = _ej_val(ejercicio)
        arr = [
            f for f in self.data.get("facturas_emitidas_docs", [])
            if not (
                f.get("codigo_empresa")==codigo_empresa
                and str(f.get("id"))==str(factura_id)
                and (f.get("ejercicio") is None or (eje_key is None and f.get("ejercicio") is None) or _ej_val(f.get("ejercicio"))==eje_key)
            )
        ]
        self.data["facturas_emitidas_docs"] = arr
        self.save()

    def marcar_facturas_emitidas_generadas(self, codigo_empresa: str, ids: list, fecha: str, ejercicio: int):
        changed = False
        idset = set(map(str, ids or []))
        arr = self.data.get("facturas_emitidas_docs", [])
        for f in arr:
            if (
                f.get("codigo_empresa")==codigo_empresa
                and (f.get("ejercicio") is None or int(f.get("ejercicio", 0))==int(ejercicio))
                and str(f.get("id")) in idset
            ):
                f["generada"] = True
                f["fecha_generacion"] = fecha
                changed = True
        if changed:
            self.save()

    # ---------- RECIBIDAS ----------
    def listar_recibidas(self, codigo_empresa: str, ejercicio: int):
        return [
            b for b in self.data.get("facturas_recibidas", [])
            if b.get("codigo_empresa")==codigo_empresa and (b.get("ejercicio") is None or int(b.get("ejercicio", 0))==int(ejercicio))
        ]

    def upsert_recibida(self, plantilla):
        arr = self.data.setdefault("facturas_recibidas", [])
        eje_key = _ej_val(plantilla.get("ejercicio"))
        key = (plantilla.get("codigo_empresa"), plantilla.get("nombre"), eje_key)
        for i,p in enumerate(arr):
            if (
                p.get("codigo_empresa")==key[0]
                and p.get("nombre")==key[1]
                and (p.get("ejercicio") is None or (key[2] is None and p.get("ejercicio") is None) or _ej_val(p.get("ejercicio"))==key[2])
            ):
                arr[i] = plantilla
                self.save()
                return
        arr.append(plantilla)
        self.save()

    def eliminar_recibida(self, codigo_empresa: str, nombre: str, ejercicio: int):
        eje_key = _ej_val(ejercicio)
        arr = [
            p for p in self.data.get("facturas_recibidas", [])
            if not (
                p.get("codigo_empresa")==codigo_empresa
                and p.get("nombre")==nombre
                and (p.get("ejercicio") is None or (eje_key is None and p.get("ejercicio") is None) or _ej_val(p.get("ejercicio"))==eje_key)
            )
        ]
        self.data["facturas_recibidas"] = arr
        self.save()

    # ---------- TERCEROS (GLOBAL) ----------
    def listar_terceros(self):
        return self.data.get("terceros", [])

    def upsert_tercero(self, tercero: dict):
        arr = self.data.setdefault("terceros", [])
        tid = tercero.get("id") or str(int(time.time() * 1000))
        tercero["id"] = tid
        for i, t in enumerate(arr):
            if str(t.get("id")) == str(tid):
                arr[i] = tercero
                self.save()
                return tid
        arr.append(tercero)
        self.save()
        return tid

    def eliminar_tercero(self, tercero_id: str):
        tid = str(tercero_id)
        for f in self.data.get("facturas_emitidas_docs", []):
            if str(f.get("tercero_id")) == tid:
                raise ValueError("No se puede eliminar el tercero: tiene facturas emitidas asociadas.")
        for a in self.data.get("albaranes_emitidas_docs", []):
            if str(a.get("tercero_id")) == tid:
                raise ValueError("No se puede eliminar el tercero: tiene albaranes asociados.")
        self.data["terceros"] = [t for t in self.data.get("terceros", []) if str(t.get("id")) != str(tercero_id)]
        self.data["terceros_empresas"] = [
            te for te in self.data.get("terceros_empresas", [])
            if str(te.get("tercero_id")) != str(tercero_id)
        ]
        self.save()

    # ---------- TERCEROS x EMPRESA ----------
    def listar_terceros_empresa(self, codigo_empresa: str, ejercicio: int):
        return [
            t for t in self.data.get("terceros_empresas", [])
            if t.get("codigo_empresa")==codigo_empresa and (t.get("ejercicio") is None or int(t.get("ejercicio", 0))==int(ejercicio))
        ]

    def get_tercero_empresa(self, codigo_empresa: str, tercero_id: str, ejercicio: int):
        return next(
            (t for t in self.data.get("terceros_empresas", [])
             if t.get("codigo_empresa")==codigo_empresa and str(t.get("tercero_id"))==str(tercero_id) and (t.get("ejercicio") is None or int(t.get("ejercicio", 0))==int(ejercicio))),
            None
        )

    def upsert_tercero_empresa(self, rel: dict):
        arr = self.data.setdefault("terceros_empresas", [])
        eje_key = _ej_val(rel.get("ejercicio"))
        key = (rel.get("codigo_empresa"), str(rel.get("tercero_id")), eje_key)
        for i, t in enumerate(arr):
            if (
                t.get("codigo_empresa")==key[0]
                and str(t.get("tercero_id"))==key[1]
                and (t.get("ejercicio") is None or (key[2] is None and t.get("ejercicio") is None) or _ej_val(t.get("ejercicio"))==key[2])
            ):
                arr[i] = rel
                self.save()
                return
        arr.append(rel)
        self.save()

    def listar_empresas_de_tercero(self, tercero_id: str):
        tid = str(tercero_id)
        empresas = self.data.get("empresas", [])
        resultado = []
        for rel in self.data.get("terceros_empresas", []):
            if str(rel.get("tercero_id")) != tid:
                continue
            codigo = rel.get("codigo_empresa")
            ejercicio = rel.get("ejercicio")
            emp = next(
                (
                    e for e in empresas
                    if e.get("codigo") == codigo and (ejercicio is None or _ej_val(e.get("ejercicio")) == _ej_val(ejercicio))
                ),
                None,
            )
            resultado.append(
                {
                    "codigo": codigo,
                    "nombre": (emp or {}).get("nombre", ""),
                    "ejercicio": ejercicio if ejercicio is not None else (emp or {}).get("ejercicio"),
                }
            )
        resultado.sort(key=lambda r: (str(r.get("codigo") or ""), _ej_val(r.get("ejercicio")) or 0))
        return resultado
