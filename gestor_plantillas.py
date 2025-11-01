import json, os, tempfile, time
from pathlib import Path
import portalocker

DEFAULT_JSON = '{"empresas":[],"bancos":[],"facturas_emitidas":[],"facturas_recibidas":[]}'

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

    def get_empresa(self, codigo: str):
        return next((e for e in self.data.get("empresas", []) if e.get("codigo")==codigo), None)

    def upsert_empresa(self, emp: dict):
        arr = self.data.setdefault("empresas", [])
        for i, e in enumerate(arr):
            if e.get("codigo")==emp.get("codigo"):
                arr[i] = emp
                self.save()
                return
        arr.append(emp)
        self.save()

    # ---------- BANCOS ----------
    def listar_bancos(self, codigo_empresa: str):
        return [b for b in self.data.get("bancos", []) if b.get("codigo_empresa")==codigo_empresa]

    def upsert_banco(self, plantilla):
        arr = self.data.setdefault("bancos", [])
        for i,p in enumerate(arr):
            if p.get("codigo_empresa")==plantilla.get("codigo_empresa") and p.get("banco")==plantilla.get("banco"):
                arr[i] = plantilla
                self.save()
                return
        arr.append(plantilla)
        self.save()

    def eliminar_banco(self, codigo_empresa: str, banco: str):
        arr = [p for p in self.data.get("bancos", []) if not (p.get("codigo_empresa")==codigo_empresa and p.get("banco")==banco)]
        self.data["bancos"] = arr
        self.save()

    # ---------- EMITIDAS ----------
    def listar_emitidas(self, codigo_empresa: str):
        return [b for b in self.data.get("facturas_emitidas", []) if b.get("codigo_empresa")==codigo_empresa]

    def upsert_emitida(self, plantilla):
        arr = self.data.setdefault("facturas_emitidas", [])
        key = (plantilla.get("codigo_empresa"), plantilla.get("nombre"))
        for i,p in enumerate(arr):
            if (p.get("codigo_empresa"), p.get("nombre"))==key:
                arr[i] = plantilla
                self.save()
                return
        arr.append(plantilla)
        self.save()

    def eliminar_emitida(self, codigo_empresa: str, nombre: str):
        arr = [p for p in self.data.get("facturas_emitidas", []) if not (p.get("codigo_empresa")==codigo_empresa and p.get("nombre")==nombre)]
        self.data["facturas_emitidas"] = arr
        self.save()

    # ---------- RECIBIDAS ----------
    def listar_recibidas(self, codigo_empresa: str):
        return [b for b in self.data.get("facturas_recibidas", []) if b.get("codigo_empresa")==codigo_empresa]

    def upsert_recibida(self, plantilla):
        arr = self.data.setdefault("facturas_recibidas", [])
        key = (plantilla.get("codigo_empresa"), plantilla.get("nombre"))
        for i,p in enumerate(arr):
            if (p.get("codigo_empresa"), p.get("nombre"))==key:
                arr[i] = plantilla
                self.save()
                return
        arr.append(plantilla)
        self.save()

    def eliminar_recibida(self, codigo_empresa: str, nombre: str):
        arr = [p for p in self.data.get("facturas_recibidas", []) if not (p.get("codigo_empresa")==codigo_empresa and p.get("nombre")==nombre)]
        self.data["facturas_recibidas"] = arr
        self.save()
