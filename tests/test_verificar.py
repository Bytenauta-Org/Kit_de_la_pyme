"""``verificar`` detecta datos cambiados, que faltan o que sobran, y prompts alterados."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from kit_pyme.verificar import FICHERO_CHECKSUMS, generar_checksums, leer_checksums, verificar


def test_los_datos_del_clon_son_los_publicados(raiz):
    assert verificar(raiz) == []


def test_checksums_tiene_los_85_ficheros_en_formato_sha256sum(raiz):
    sumas = leer_checksums(raiz / "datos" / FICHERO_CHECKSUMS)
    assert len(sumas) == 85
    assert sumas["pedidos/pedido-01.txt"] == "b9579711e64458b976434564e777dc3191a13f330630c993dc3e8abfefdd12ff"
    assert sumas["contrato/contrato.txt"] == "a4ccbecd6113e55654bb68f884e4b0145a89f61947e3e110404badcf77cbe7fb"
    assert sumas["cobros/cobros-verdad.json"] == "4f188364fc11d91eae5bacf93b103b9c6c5d9d816b145ca48547a3bf2eaf70d1"
    assert generar_checksums(raiz) == (raiz / "datos" / FICHERO_CHECKSUMS).read_text(encoding="utf-8")


def _copia(raiz: Path, destino: Path) -> Path:
    shutil.copytree(raiz / "datos", destino / "datos")
    shutil.copytree(raiz / "tareas", destino / "tareas")
    return destino


def test_detecta_un_dato_cambiado(raiz, tmp_path):
    copia = _copia(raiz, tmp_path)
    fichero = copia / "datos" / "pedidos" / "pedido-03.txt"
    fichero.write_bytes(fichero.read_bytes() + b"\n")
    assert verificar(copia) == ["datos/pedidos/pedido-03.txt ha cambiado (sha256 distinto del publicado)"]


def test_detecta_un_dato_que_falta_y_otro_que_sobra(raiz, tmp_path):
    copia = _copia(raiz, tmp_path)
    (copia / "datos" / "correos" / "correo-30.txt").unlink()
    (copia / "datos" / "correos" / "correo-31.txt").write_text("nuevo", encoding="utf-8")
    assert verificar(copia) == [
        "falta datos/correos/correo-30.txt",
        f"datos/correos/correo-31.txt no está en {FICHERO_CHECKSUMS}: sobra o hay que versionar el kit",
    ]


def test_detecta_un_prompt_alterado(raiz, tmp_path):
    copia = _copia(raiz, tmp_path)
    ruta = copia / "tareas" / "resumir-correos" / "tarea.json"
    d = json.loads(ruta.read_text(encoding="utf-8"))
    d["prompt"] = d["prompt"].replace("hoy es lunes 14", "hoy es martes 15")
    ruta.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    assert verificar(copia) == [
        "tareas/resumir-correos: el prompt compuesto no coincide con su sha256",
        "tareas/resumir-correos: el mensaje de sistema no coincide con su sha256",
    ]


def test_sin_fichero_de_sumas(raiz, tmp_path):
    copia = _copia(raiz, tmp_path)
    (copia / "datos" / FICHERO_CHECKSUMS).unlink()
    assert verificar(copia) == [f"falta datos/{FICHERO_CHECKSUMS}"]
