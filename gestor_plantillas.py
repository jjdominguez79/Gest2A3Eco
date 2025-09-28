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
