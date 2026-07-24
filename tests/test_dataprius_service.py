from pathlib import Path

from services.dataprius_service import DatapriusClient


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.content = b"{}"
        self.text = str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/oauth/token"):
            return _Response(200, {"access_token": "token-prueba"})
        if url.endswith("/folders/getpath"):
            return _Response(
                400,
                {
                    "error": {
                        "error_code": "PATH_NOT_EXISTS",
                        "error_message": "Path does not exists.",
                    }
                },
            )
        if url.endswith("/folders/createpath"):
            return _Response(
                201,
                {"data": [{"ID": "carpeta-1", "Path": kwargs["json"]["Path"]}]},
            )
        if url.endswith("/files/upload"):
            return _Response(
                201,
                {
                    "data": {
                        "ID": "archivo-1",
                        "Folder": "carpeta-1",
                        "Name": kwargs["files"]["file"][0],
                        "Size": 12,
                    }
                },
            )
        raise AssertionError(url)


def test_crea_ruta_y_sube_archivo_a_dataprius(tmp_path: Path):
    path = tmp_path / "contrato.pdf"
    path.write_bytes(b"%PDF prueba")
    session = _Session()
    client = DatapriusClient("key", "secret", session=session)

    result = client.subir_archivo(
        "FOLDERS/Gest2A3Eco/Tramites DGT/DGT-2026-0001/Generados",
        str(path),
    )

    assert result["id"] == "archivo-1"
    assert result["nombre"] == "contrato.pdf"
    assert result["provider"] == "dataprius"
    assert len([call for call in session.calls if call[1].endswith("/oauth/token")]) == 1
