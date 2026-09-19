#!/usr/bin/env python3
"""Compara dos outcomes.jsonl y lista las facturas en las que discrepan, con el motivo de la referencia.

    python3 pruebas/comparar_outcomes.py outputs/outcomes.jsonl referencia/outcomes_albertito_v3.jsonl [referencia/decisiones_albertito_v3.tsv]

Uso previsto: vuestro pipeline contra la implementacion de referencia (albertito, viernes noche, norma v3).
Una discrepancia NO significa que la referencia tenga razon: significa que uno de los dos tiene un bug
o una politica distinta, y hay que mirar esa factura. Ojo: en la referencia los 29 escaneados salen
ESCALAR "sin_texto" (no tenia OCR) y los 2 con caracteres invisibles (F26-3011, FA-4488) salen ESCALAR
cuando deberian ser PAGAR; esas 31 discrepancias son esperables si vuestro OCR funciona.
"""
import csv, json, sys
from collections import Counter


def cargar(ruta):
    out = {}
    with open(ruta, encoding="utf-8") as fh:
        for n, linea in enumerate(fh, 1):
            if not linea.strip():
                continue
            try:
                o = json.loads(linea)
            except json.JSONDecodeError as e:
                print(f"{ruta}:{n}: JSON invalido ({e})"); continue
            out[o.get("file_id")] = o.get("result")
    return out


def main():
    mio, ref = cargar(sys.argv[1]), cargar(sys.argv[2])
    motivos = {}
    if len(sys.argv) > 3:
        with open(sys.argv[3], encoding="utf-8") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                motivos[r["file_id"]] = r["motivo"]
    solo_mio, solo_ref = sorted(set(mio) - set(ref)), sorted(set(ref) - set(mio))
    comunes = sorted(set(mio) & set(ref))
    disc = [(f, mio[f], ref[f]) for f in comunes if mio[f] != ref[f]]
    print(f"mio: {len(mio)} · referencia: {len(ref)} · comunes: {len(comunes)} · discrepancias: {len(disc)}")
    if solo_mio: print(f"solo en el mio ({len(solo_mio)}): {solo_mio[:10]}")
    if solo_ref: print(f"solo en la referencia ({len(solo_ref)}): {solo_ref[:10]}")
    print("\nreparto mio:", dict(Counter(mio.values())), "| referencia:", dict(Counter(ref.values())))
    print("\ntransiciones (mio -> referencia):", dict(Counter(f"{a}->{b}" for _, a, b in disc)))
    print()
    for f, a, b in disc:
        print(f"{f:36} mio={a:9} ref={b:9} {motivos.get(f, '')[:110]}")


if __name__ == "__main__":
    main()
