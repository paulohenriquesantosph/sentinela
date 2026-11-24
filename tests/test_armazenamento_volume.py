# -*- coding: utf-8 -*-
"""Banco de Dossiês em Volume (armazenamento_volume.py) com uma API de arquivos falsa, em memória.

Rodar, da raiz do projeto:
    ./venv/bin/python -m unittest tests.test_armazenamento_volume -v
"""
import io
import os
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from databricks.sdk.errors import NotFound

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import armazenamento_volume as av  # noqa: E402
import core  # noqa: E402

BASE = "/Volumes/cat/sch/dossies"


class ArquivosFalsos:
    """Imita databricks.sdk FilesAPI: upload, download, list_directory_contents e delete."""

    def __init__(self, falhar=None):
        self.arquivos = {}
        self.falhar = falhar
        self._trava = threading.Lock()

    def upload(self, file_path, contents, *, overwrite=None):
        if self.falhar:
            raise self.falhar
        with self._trava:
            self.arquivos[file_path] = contents.read()

    def download(self, file_path):
        if file_path not in self.arquivos:
            raise NotFound("não existe")
        return SimpleNamespace(contents=io.BytesIO(self.arquivos[file_path]))

    def list_directory_contents(self, directory_path, **kw):
        prefixo = directory_path.rstrip("/") + "/"
        nomes = sorted(p[len(prefixo):] for p in list(self.arquivos) if p.startswith(prefixo) and "/" not in p[len(prefixo):])
        if not nomes:
            raise NotFound("pasta não existe")
        return iter(SimpleNamespace(name=n, path=prefixo + n, is_directory=False) for n in nomes)

    def delete(self, file_path):
        self.arquivos.pop(file_path, None)


def novo(falhar=None):
    arquivos = ArquivosFalsos(falhar)
    return av.ArmazenamentoVolume(BASE, SimpleNamespace(files=arquivos)), arquivos


def caso(numero="2026-AAA111", nome="Ana", criado="2026-10-05T10:00:00", tipo="Pessoa Física (PF)"):
    return core.Caso(numero_caso=numero, tipo_caso=tipo, nome_cliente=nome, criado_em=criado)


class TestArmazenamentoVolume(unittest.TestCase):
    def test_salva_e_carrega_caso_e_pdf(self):
        s, arq = novo()
        s.salvar_caso(caso(), b"%PDF-1.4 teste")
        self.assertIn(f"{BASE}/casos/2026-AAA111.json", arq.arquivos)
        self.assertIn(f"{BASE}/pdfs/dossie_2026-AAA111.pdf", arq.arquivos)
        self.assertIn(f"{BASE}/indice/2026-AAA111.json", arq.arquivos)
        c = s.carregar_caso("2026-AAA111")
        self.assertEqual((c.numero_caso, c.nome_cliente), ("2026-AAA111", "Ana"))
        self.assertEqual(s.carregar_pdf("2026-AAA111"), b"%PDF-1.4 teste")

    def test_inexistente_e_numero_invalido(self):
        s, _ = novo()
        self.assertIsNone(s.carregar_caso("2026-NAOEXISTE"))
        self.assertIsNone(s.carregar_pdf("2026-NAOEXISTE"))
        self.assertIsNone(s.carregar_caso("../../etc/passwd"))
        with self.assertRaises(ValueError):
            s.salvar_caso(caso(numero="../x"))

    def test_sem_pdf_nao_apaga_o_anterior(self):
        s, _ = novo()
        s.salvar_caso(caso(), b"v1")
        s.salvar_caso(caso(), None)
        self.assertEqual(s.carregar_pdf("2026-AAA111"), b"v1")

    def test_lista_do_mais_recente_e_busca(self):
        s, _ = novo()
        self.assertEqual(s.listar_indice(), [])  # pasta ainda não existe
        s.salvar_caso(caso("2026-AAA111", "Ana", "2026-10-01T10:00:00"))
        s.salvar_caso(caso("2026-BBB222", "Bia", "2026-10-03T10:00:00"))
        s.salvar_caso(caso("2026-CCC333", "Caio", "2026-10-02T10:00:00"))
        self.assertEqual([i["numero_caso"] for i in s.listar_indice()], ["2026-BBB222", "2026-CCC333", "2026-AAA111"])
        self.assertEqual([i["numero_caso"] for i in s.buscar_por_numero("ccc")], ["2026-CCC333"])
        self.assertEqual(s.buscar_por_numero("  "), [])

    def test_salvar_renova_a_lista_guardada(self):
        s, _ = novo()
        s.salvar_caso(caso("2026-AAA111"))
        self.assertEqual(len(s.listar_indice()), 1)
        s.salvar_caso(caso("2026-BBB222", criado="2026-10-06T10:00:00"))
        self.assertEqual(len(s.listar_indice()), 2)  # sem esperar a validade

    def test_entrada_corrompida_nao_derruba_a_lista(self):
        s, arq = novo()
        s.salvar_caso(caso("2026-AAA111"))
        arq.arquivos[f"{BASE}/indice/2026-ZZZ999.json"] = b"{ quebrado"
        self.assertEqual([i["numero_caso"] for i in s.listar_indice()], ["2026-AAA111"])

    def test_gravacoes_simultaneas_nao_perdem_casos(self):
        s, _ = novo()
        numeros = [f"2026-T{i:05d}" for i in range(30)]
        fios = [threading.Thread(target=s.salvar_caso, args=(caso(n, criado=f"2026-10-05T10:00:{i % 60:02d}"),))
                for i, n in enumerate(numeros)]
        [f.start() for f in fios]
        [f.join() for f in fios]
        self.assertEqual({i["numero_caso"] for i in s.listar_indice()}, set(numeros))


class TestCriarArmazenamento(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.pasta, True)

    def _env(self, **extra):
        env = {"SENTINELA_DATA_DIR": self.pasta, **extra}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop(av.ENV_VOLUME, None) if av.ENV_VOLUME not in extra else None

    def test_sem_a_variavel_usa_a_pasta_local(self):
        self._env()
        with mock.patch.object(av, "_cliente") as cli:
            s, aviso = av.criar_armazenamento()
            cli.assert_not_called()
        self.assertIsInstance(s, core.ArmazenamentoLocal)
        self.assertEqual(aviso, "")

    def test_com_a_variavel_usa_o_volume(self):
        self._env(**{av.ENV_VOLUME: BASE})
        arq = ArquivosFalsos()
        with mock.patch.object(av, "_cliente", return_value=SimpleNamespace(files=arq)):
            s, aviso = av.criar_armazenamento()
        self.assertIsInstance(s, av.ArmazenamentoVolume)
        self.assertEqual(aviso, "")
        self.assertEqual(arq.arquivos, {})  # o arquivo de teste é apagado

    def test_sem_acesso_ao_volume_volta_para_a_pasta_local_com_aviso(self):
        self._env(**{av.ENV_VOLUME: BASE})
        arq = ArquivosFalsos(falhar=PermissionError("sem permissão"))
        with mock.patch.object(av, "_cliente", return_value=SimpleNamespace(files=arq)):
            s, aviso = av.criar_armazenamento()
        self.assertIsInstance(s, core.ArmazenamentoLocal)
        self.assertIn("Não foi possível acessar o Volume", aviso)
        self.assertIn("sem permissão", aviso)

    def test_falha_ao_criar_o_cliente_tambem_volta_para_a_pasta_local(self):
        self._env(**{av.ENV_VOLUME: BASE})
        with mock.patch.object(av, "_cliente", side_effect=RuntimeError("sem credencial")):
            s, aviso = av.criar_armazenamento()
        self.assertIsInstance(s, core.ArmazenamentoLocal)
        self.assertIn("sem credencial", aviso)


if __name__ == "__main__":
    unittest.main()
