"""
Caché de extracciones, indexada por el hash del archivo.

Para qué sirve, en orden de importancia:

1. No pagar dos veces por leer el mismo PDF. La segunda pasada cuesta 0.
2. Idempotencia: relanzar el proceso no repite trabajo ni duplica nada.
3. Reproceso incremental: si el domingo cambian un archivo, su hash cambia
   y solo se reextrae ese. Los otros 499 salen de aquí.
"""

import hashlib
import json
import sqlite3
from pathlib import Path

RUTA_POR_DEFECTO = Path("estado/extraccion.db")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS extracciones (
    clave       TEXT PRIMARY KEY,
    sha256      TEXT NOT NULL,
    version     TEXT NOT NULL,
    file_id     TEXT NOT NULL,
    via         TEXT NOT NULL,
    datos_json  TEXT NOT NULL,
    coste_usd   REAL NOT NULL DEFAULT 0,
    guardado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_file_id ON extracciones(file_id);
CREATE INDEX IF NOT EXISTS idx_sha ON extracciones(sha256);
"""


def version_extractor() -> str:
    """Huella del codigo que hace la extraccion.

    Va dentro de la clave de cache junto al hash del PDF. Si no estuviera,
    pasaria esto: mejoras el parser, el PDF no cambia, y la cache te sirve
    el resultado VIEJO. Creerias haber arreglado algo que sigue roto.

    Con esto, tocar campos.py, lector.py o llm.py invalida la cache sola.
    """
    h = hashlib.sha256()
    aqui = Path(__file__).parent
    for nombre in sorted(("campos.py", "lector.py", "llm.py")):
        ruta = aqui / nombre
        if ruta.exists():
            h.update(ruta.read_bytes())
    return h.hexdigest()[:12]


class Cache:
    def __init__(self, ruta: str | Path = RUTA_POR_DEFECTO, version: str | None = None):
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.ruta, check_same_thread=False)
        # WAL: permite leer mientras se escribe. Con varios hilos extrayendo
        # a la vez, evita bloqueos.
        self.con.execute("PRAGMA journal_mode=WAL")
        self._migrar()
        self.con.executescript(ESQUEMA)
        self.con.commit()
        self.version = version or version_extractor()
        self.aciertos = 0
        self.fallos = 0

    def _migrar(self) -> None:
        """Adapta una base de datos creada por una version anterior.

        `CREATE TABLE IF NOT EXISTS` no anade columnas nuevas a una tabla que
        ya existe: la deja como estaba y luego todo peta con "no such column".
        Como lo que hay dentro es cache regenerable, se tira y se crea de cero.
        """
        existe = self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='extracciones'"
        ).fetchone()
        if not existe:
            return
        columnas = {fila[1] for fila in
                    self.con.execute("PRAGMA table_info(extracciones)")}
        if "clave" not in columnas or "version" not in columnas:
            self.con.execute("DROP TABLE extracciones")
            self.con.commit()

    def _clave(self, sha256: str) -> str:
        return f"{sha256}:{self.version}"

    def buscar(self, sha256: str) -> dict | None:
        fila = self.con.execute(
            "SELECT datos_json FROM extracciones WHERE clave = ?",
            (self._clave(sha256),),
        ).fetchone()
        if fila:
            self.aciertos += 1
            return json.loads(fila[0])
        self.fallos += 1
        return None

    def guardar(self, extraccion) -> None:
        """Solo se guarda lo que salió bien.

        Un fallo del modelo NO se cachea: si volvemos a intentarlo, queremos
        que lo intente de verdad, no que nos devuelva el fallo de antes.
        """
        if extraccion.via in ("llm_fallido", "sin_leer"):
            return
        self.con.execute(
            "INSERT OR REPLACE INTO extracciones "
            "(clave, sha256, version, file_id, via, datos_json, coste_usd) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                self._clave(extraccion.sha256),
                extraccion.sha256,
                self.version,
                extraccion.file_id,
                extraccion.via,
                json.dumps(extraccion.to_dict(), ensure_ascii=False),
                extraccion.coste_usd,
            ),
        )
        self.con.commit()

    def limpiar_versiones_viejas(self) -> int:
        """Borra lo cacheado con versiones anteriores del extractor."""
        cur = self.con.execute(
            "DELETE FROM extracciones WHERE version != ?", (self.version,)
        )
        self.con.commit()
        return cur.rowcount

    def resumen(self) -> dict:
        total, coste = self.con.execute(
            "SELECT COUNT(*), COALESCE(SUM(coste_usd), 0) FROM extracciones "
            "WHERE version = ?", (self.version,)
        ).fetchone()
        viejas = self.con.execute(
            "SELECT COUNT(*) FROM extracciones WHERE version != ?", (self.version,)
        ).fetchone()[0]
        return {
            "version_extractor": self.version,
            "guardadas": total,
            "de_versiones_viejas": viejas,
            "coste_acumulado_usd": round(coste, 4),
            "aciertos_sesion": self.aciertos,
            "fallos_sesion": self.fallos,
        }

    def cerrar(self) -> None:
        self.con.close()
