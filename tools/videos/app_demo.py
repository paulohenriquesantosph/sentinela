# -*- coding: utf-8 -*-
"""Roda o app real com a resposta da IA SIMULADA (JSON em cenas/<cena>.json), só para gravar os tutoriais.
A cena atual vem do arquivo apontado por DEMO_CENA_ARQ. Não faz parte do app publicado."""
import json
import os
import runpy
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
import ia  # noqa: E402


def _resposta_simulada(*args, **kwargs):
    cena = Path(os.environ["DEMO_CENA_ARQ"]).read_text().strip()
    return json.loads((Path(__file__).parent / "cenas" / f"{cena}.json").read_text(encoding="utf-8"))


ia.extrair_dados_do_texto = _resposta_simulada

# Em produção a base de casos está ativa: simula só o retorno de sucesso da gravação (nada é gravado de verdade) e
# lê os dossiês dos arquivos locais da demonstração.
import gravacao_sql  # noqa: E402
gravacao_sql.configurado = lambda: True
gravacao_sql.gravar_se_configurado = lambda caso, limpar=False: ("ok", "usr.sentinela_aml")
gravacao_sql.carregar_se_configurado = lambda numero: ("desativado", None, "")
gravacao_sql.listar_se_configurado = lambda: ("desativado", [], "")
runpy.run_path(str(RAIZ / "app.py"), run_name="__main__")
