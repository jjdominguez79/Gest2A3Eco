import json
from pathlib import Path

class GestorPlantillas:
    def __init__(self, path_json: Path):
        self.path = Path(path_json)
        self.data = {}
        self._load()

    def _load(self):
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text('{"empresas":[],"bancos":[],"facturas_emitidas":[],"facturas_recibidas":[]}', encoding="utf-8")
        self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Empresas
    def listar_empresas(self):
        return self.data.get("empresas", [])

    def obtener_empresa(self, codigo: str):
        for empresa in self.data.get("empresas", []):
            if empresa.get("codigo") == codigo:
                return empresa
        return None

    def crear_empresa(self, empresa: dict):
        codigo = empresa.get("codigo")
        if not codigo:
            raise ValueError("El código de empresa es obligatorio")
        if self.obtener_empresa(codigo):
            raise ValueError(f"Ya existe una empresa con el código {codigo}")
        empresas = self.data.setdefault("empresas", [])
        empresas.append(dict(empresa))
        self.save()

    def actualizar_empresa(self, codigo_actual: str, empresa_actualizada: dict):
        empresas = self.data.setdefault("empresas", [])
        for idx, existente in enumerate(empresas):
            if existente.get("codigo") == codigo_actual:
                nuevo_codigo = empresa_actualizada.get("codigo") or codigo_actual
                if nuevo_codigo != codigo_actual and any(
                    e.get("codigo") == nuevo_codigo for i, e in enumerate(empresas) if i != idx
                ):
                    raise ValueError(f"Ya existe una empresa con el código {nuevo_codigo}")
                empresas[idx] = dict(empresa_actualizada)
                if nuevo_codigo != codigo_actual:
                    self._actualizar_codigo_relacionado(codigo_actual, nuevo_codigo)
                self.save()
                return
        raise KeyError(f"No se encontró la empresa con código {codigo_actual}")

    def eliminar_empresa(self, codigo: str):
        empresas = [e for e in self.data.get("empresas", []) if e.get("codigo") != codigo]
        if len(empresas) == len(self.data.get("empresas", [])):
            raise KeyError(f"No se encontró la empresa con código {codigo}")
        self.data["empresas"] = empresas
        # Limpiar datos asociados
        self.data["bancos"] = [b for b in self.data.get("bancos", []) if b.get("codigo_empresa") != codigo]
        self.data["facturas_emitidas"] = [
            f for f in self.data.get("facturas_emitidas", []) if f.get("codigo_empresa") != codigo
        ]
        self.data["facturas_recibidas"] = [
            f for f in self.data.get("facturas_recibidas", []) if f.get("codigo_empresa") != codigo
        ]
        self.save()

    def _actualizar_codigo_relacionado(self, codigo_viejo: str, codigo_nuevo: str):
        for bloque in ("bancos", "facturas_emitidas", "facturas_recibidas"):
            for item in self.data.get(bloque, []):
                if item.get("codigo_empresa") == codigo_viejo:
                    item["codigo_empresa"] = codigo_nuevo

    # Bancos
    def listar_bancos(self, codigo_empresa: str):
        return [b for b in self.data.get("bancos", []) if b.get("codigo_empresa")==codigo_empresa]

    def upsert_banco(self, plantilla):
        arr = self.data.setdefault("bancos", [])
        for i,p in enumerate(arr):
            if p.get("codigo_empresa")==plantilla.get("codigo_empresa") and p.get("banco")==plantilla.get("banco"):
                arr[i] = plantilla; self.save(); return
        arr.append(plantilla); self.save()

    def eliminar_banco(self, codigo_empresa: str, banco: str):
        arr = [p for p in self.data.get("bancos", []) if not (p.get("codigo_empresa")==codigo_empresa and p.get("banco")==banco)]
        self.data["bancos"] = arr; self.save()

    # Emitidas
    def listar_emitidas(self, codigo_empresa: str):
        return [b for b in self.data.get("facturas_emitidas", []) if b.get("codigo_empresa")==codigo_empresa]

    def upsert_emitida(self, plantilla):
        arr = self.data.setdefault("facturas_emitidas", [])
        key = (plantilla.get("codigo_empresa"), plantilla.get("nombre"))
        for i,p in enumerate(arr):
            if (p.get("codigo_empresa"), p.get("nombre"))==key:
                arr[i] = plantilla; self.save(); return
        arr.append(plantilla); self.save()

    def eliminar_emitida(self, codigo_empresa: str, nombre: str):
        arr = [p for p in self.data.get("facturas_emitidas", []) if not (p.get("codigo_empresa")==codigo_empresa and p.get("nombre")==nombre)]
        self.data["facturas_emitidas"] = arr; self.save()

    # Recibidas
    def listar_recibidas(self, codigo_empresa: str):
        return [b for b in self.data.get("facturas_recibidas", []) if b.get("codigo_empresa")==codigo_empresa]

    def upsert_recibida(self, plantilla):
        arr = self.data.setdefault("facturas_recibidas", [])
        key = (plantilla.get("codigo_empresa"), plantilla.get("nombre"))
        for i,p in enumerate(arr):
            if (p.get("codigo_empresa"), p.get("nombre"))==key:
                arr[i] = plantilla; self.save(); return
        arr.append(plantilla); self.save()

    def eliminar_recibida(self, codigo_empresa: str, nombre: str):
        arr = [p for p in self.data.get("facturas_recibidas", []) if not (p.get("codigo_empresa")==codigo_empresa and p.get("nombre")==nombre)]
        self.data["facturas_recibidas"] = arr; self.save()
