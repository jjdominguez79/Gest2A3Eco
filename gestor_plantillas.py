import json, os, tempfile
from pathlib import Path
import portalocker

class GestorPlantillas:
    def __init__(self, path_json: Path):
        self.path = Path(path_json)
        self.data = {}
        self._load()

    def _atomic_write(self, text: str):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmppath = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmpf:
                tmpf.write(text); tmpf.flush(); os.fsync(tmpf.fileno())
            os.replace(tmppath, self.path)
        finally:
            try:
                if os.path.exists(tmppath): os.remove(tmppath)
            except Exception: pass

    def _load(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._atomic_write('{"empresas":[],"bancos":[],"facturas_emitidas":[],"facturas_recibidas":[]}')
        with portalocker.Lock(str(self.path), mode="r", flags=portalocker.LOCK_SH, timeout=5) as f:
            txt = f.read()
        self.data = json.loads(txt or "{}")

    def save(self):
        new_text = json.dumps(self.data, ensure_ascii=False, indent=2)
        with portalocker.Lock(str(self.path), mode="w", flags=portalocker.LOCK_EX, timeout=5):
            pass
        self._atomic_write(new_text)

    def listar_empresas(self):
        return self.data.get("empresas", [])

    # bancos
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

    # emitidas
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

    # recibidas
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
