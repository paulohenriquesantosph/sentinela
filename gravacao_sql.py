# -*- coding: utf-8 -*-
"""
Sentinela PLD - gravação do dossiê gerado nas tabelas de `usr.sentinela_aml`
============================================================================

Grava SÓ o dossiê gerado ("Informações do Caso"). Resolução do Caso e Avaliação de Qualidade não são
gravadas e saem sempre em branco (ver `esquema_sql.EXCLUIDOS_CASOS`). Os casos ficam disponíveis para
consulta, por tipo de caso (views `casos_pf`, `casos_pj`, `casos_cripto`, `casos_nuinvest`, `casos_under18`).

Como funciona
-------------
- Só roda se `SENTINELA_SQL_WAREHOUSE_ID` estiver definida (id do SQL warehouse). Sem ela, o app funciona
  igual a antes e nada é enviado ao Databricks.
- Outras variáveis (opcionais): `SENTINELA_SQL_CATALOGO` (padrão "usr"), `SENTINELA_SQL_SCHEMA` (padrão
  "sentinela_aml") e `SENTINELA_SQL_PERFIL` (perfil do Databricks CLI, para rodar fora do Databricks Apps).
- Os textos do usuário nunca entram no comando SQL: vão como PARÂMETRO (um JSON com as linhas de cada
  tabela, lido no SQL por `from_json`). Não há SQL montado com texto livre.
- Um erro na gravação nunca derruba o app: o dossiê continua salvo no Banco de Dossiês (arquivos) e o
  resultado ("ok" / "erro") é mostrado ao analista, com a opção de tentar de novo.
- Cada dossiê tem número único, então a primeira gravação só faz INSERT. Para tentar de novo depois de uma
  falha parcial, `limpar=True` apaga antes as linhas do caso em todas as tabelas (DELETE por `numero_caso`).
"""
from __future__ import annotations

import concurrent.futures
import dataclasses
import functools
import json
import os
import re
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import core
import esquema_sql

ENV_WAREHOUSE = "SENTINELA_SQL_WAREHOUSE_ID"
ENV_CATALOGO = "SENTINELA_SQL_CATALOGO"
ENV_SCHEMA = "SENTINELA_SQL_SCHEMA"
ENV_PERFIL = "SENTINELA_SQL_PERFIL"

# (comando SQL, parâmetros nomeados [{"name": ..., "value": ..., "type": "STRING"}]) -> executa ou levanta ErroGravacao
Executor = Callable[[str, List[Dict[str, str]]], None]


class ErroGravacao(Exception):
    pass


# ---------------------------------------------------------------------------
# Conversões
# ---------------------------------------------------------------------------

def _texto(v: Any) -> Optional[str]:
    """Texto do formulário -> valor da coluna: vazio vira NULL."""
    s = "" if v is None else str(v)
    return s if s.strip() else None


def _numero(v: Any) -> Optional[float]:
    """'R$1.200,00' / '14%' -> número; vazio ou sem dígitos -> NULL."""
    s = "" if v is None else str(v)
    if not re.search(r"\d", s):
        return None
    return core.parse_valor_br(s)


def _inteiro(v: Any) -> Optional[int]:
    m = re.search(r"\d+", "" if v is None else str(v))
    return int(m.group()) if m else None


def dossie_sem_resolucao(caso: core.Caso) -> core.Caso:
    """Cópia do caso com Resolução do Caso e Avaliação de Qualidade em branco (só o dossiê é gravado)."""
    copia = core.Caso.from_dict(caso.to_dict())
    padroes = {f.name: f for f in dataclasses.fields(core.Caso)}
    for nome in esquema_sql.EXCLUIDOS_CASOS | esquema_sql.NAO_GRAVADOS_LISTAS:
        f = padroes[nome]
        if f.default is not dataclasses.MISSING:
            setattr(copia, nome, f.default)
        else:
            setattr(copia, nome, f.default_factory())  # type: ignore[misc]
    copia.scorecard_tipo = ""
    return copia


def _campos(obj: Any, classe: type) -> Dict[str, Any]:
    return {f.name: _texto(getattr(obj, f.name)) for f in esquema_sql.campos_escalares(classe)}


# ---------------------------------------------------------------------------
# Linhas de cada tabela
# ---------------------------------------------------------------------------

def linhas_do_caso(caso: core.Caso) -> Dict[str, List[Dict[str, Any]]]:
    """Linhas de cada tabela para o dossiê (sem Resolução e Avaliação). Tabelas sem linhas vêm vazias."""
    c = dossie_sem_resolucao(caso)
    chave = {"numero_caso": c.numero_caso, "tipo_caso": c.tipo_caso}
    out: Dict[str, List[Dict[str, Any]]] = {t: [] for t in esquema_sql.TABELAS}

    # ---- casos --------------------------------------------------------------------------------
    linha: Dict[str, Any] = {}
    for f in esquema_sql.campos_escalares(core.Caso):
        if f.name in esquema_sql.EXCLUIDOS_CASOS:
            continue
        valor = getattr(c, f.name)
        linha[f.name] = (int(valor) if valor not in (None, "") else None) if f.name in esquema_sql.CAMPOS_INT \
            else _texto(valor)
    periodo = core.parse_periodo(c.mov_periodo)
    alerta = core.parse_data_br(c.data_alerta)
    montante = core.montante_cripto(c)
    linha.update({
        "data_alerta_dt": alerta.isoformat() if alerta else None,
        "mov_periodo_inicio": periodo[0].isoformat() if periodo else None,
        "mov_periodo_fim": periodo[1].isoformat() if periodo else None,
        "mov_total_credito_valor": _numero(c.mov_total_credito),
        "mov_total_debito_valor": _numero(c.mov_total_debito),
        "renda_presumida_valor": _numero(c.renda_presumida),
        "faturamento_presumido_valor": _numero(c.faturamento_presumido),
        "montante_cripto_valor": montante if montante > 0 else None,
        "caso_json": json.dumps(c.to_dict(), ensure_ascii=False),
        "gravado_em": core.agora_iso(),
    })
    out["casos"].append(linha)

    # ---- contrapartes -------------------------------------------------------------------------
    for lado, lista in (("credito", c.contrapartes_credito), ("debito", c.contrapartes_debito)):
        for i, cp in enumerate(lista):
            out["contrapartes"].append({
                **chave, "lado": lado, "ordem": i, **_campos(cp, core.ContraparteMovimentacao),
                "porcentagem_valor": _numero(cp.porcentagem), "valor_valor": _numero(cp.valor),
                "renda_presumida_valor": _numero(cp.renda_presumida),
                "faturamento_presumido_valor": _numero(cp.faturamento_presumido)})

    # ---- sócios, outras movimentações, arredondamento e Pix --------------------------------------
    for i, s in enumerate(c.socios):
        out["socios"].append({**chave, "ordem": i, **_campos(s, core.Socio),
                              "renda_presumida_valor": _numero(s.renda_presumida),
                              "patrimonio_valor": _numero(s.patrimonio)})
    for i, m in enumerate(c.outras_movimentacoes):
        montante_m = core.extrair_montante(m.info)
        out["outras_movimentacoes"].append({**chave, "ordem": i, **_campos(m, core.OutraMovimentacao),
                                            "montante_valor": montante_m if montante_m > 0 else None})
    for i, a in enumerate(c.arredondamento_itens):
        out["arredondamentos"].append({**chave, "ordem": i, **_campos(a, core.ItemArredondamento),
                                       "quantidade_valor": _inteiro(a.quantidade), "valor_valor": _numero(a.valor)})
    for i, p in enumerate(c.pix_itens):
        out["mensagens_pix"].append({**chave, "ordem": i, **_campos(p, core.MensagemPix),
                                     "quantidade_valor": _inteiro(p.quantidade)})

    # ---- timelines (série diária) ----------------------------------------------------------------
    for nome, inicio, creditos, debitos in (
            ("bancaria", c.timeline_inicio, c.timeline_creditos, c.timeline_debitos),
            ("cripto", c.timeline_cripto_inicio, c.timeline_cripto_creditos, c.timeline_cripto_debitos)):
        ini = core.parse_data_br(inicio)
        if not ini:
            continue
        for i in range(max(len(creditos), len(debitos))):
            out["timeline_diaria"].append({
                **chave, "timeline": nome, "data": (ini + timedelta(days=i)).isoformat(),
                "creditos": creditos[i] if i < len(creditos) else 0.0,
                "debitos": debitos[i] if i < len(debitos) else 0.0})
    return out


# ---------------------------------------------------------------------------
# Comandos SQL (com parâmetros)
# ---------------------------------------------------------------------------

def _q(nome: str) -> str:
    return f"`{nome}`"


def comando_insert(tabela: str, linhas: List[Dict[str, Any]], catalogo: str = esquema_sql.CATALOGO,
                   schema: str = esquema_sql.SCHEMA) -> Tuple[str, List[Dict[str, str]]]:
    """INSERT de todas as linhas da tabela num único comando. As linhas viajam como UM parâmetro JSON."""
    cols = esquema_sql.definir_esquema()[tabela]
    struct = ", ".join(f"{_q(c.nome)}: " + ("DOUBLE" if c.tipo == "DOUBLE" else "INT" if c.tipo == "INT" else "STRING")
                       for c in cols)
    lista_cols = ", ".join(_q(c.nome) for c in cols)
    campos = ", ".join(f"CAST(r.{_q(c.nome)} AS {c.tipo})" if c.tipo in ("DATE", "TIMESTAMP") else f"r.{_q(c.nome)}"
                       for c in cols)
    sql = (f"INSERT INTO {catalogo}.{schema}.{tabela} ({lista_cols})\n"
           f"SELECT {campos}\nFROM (SELECT explode(from_json(:linhas, 'ARRAY<STRUCT<{struct}>>')) AS r)")
    linhas_json = json.dumps([{c.nome: l.get(c.nome) for c in cols} for l in linhas], ensure_ascii=False)
    return sql, [{"name": "linhas", "value": linhas_json, "type": "STRING"}]


def comando_delete(tabela: str, numero_caso: str, catalogo: str = esquema_sql.CATALOGO,
                   schema: str = esquema_sql.SCHEMA) -> Tuple[str, List[Dict[str, str]]]:
    return (f"DELETE FROM {catalogo}.{schema}.{tabela} WHERE numero_caso = :numero_caso",
            [{"name": "numero_caso", "value": numero_caso, "type": "STRING"}])


def gravar_caso(caso: core.Caso, executar: Executor, catalogo: str = esquema_sql.CATALOGO,
                schema: str = esquema_sql.SCHEMA, limpar: bool = False) -> Dict[str, int]:
    """Grava o dossiê. Devolve quantas linhas foram gravadas por tabela. Levanta ErroGravacao se algo falhar."""
    linhas = linhas_do_caso(caso)
    if limpar:  # nova tentativa depois de falha parcial: apaga o que já tinha entrado
        for tabela in reversed(esquema_sql.TABELAS):
            executar(*comando_delete(tabela, caso.numero_caso, catalogo, schema))
    executar(*comando_insert("casos", linhas["casos"], catalogo, schema))  # primeiro o caso; depois as filhas
    filhas = [t for t in esquema_sql.TABELAS[1:] if linhas[t]]
    erros: List[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(6, len(filhas)))) as pool:
        futuros = {pool.submit(executar, *comando_insert(t, linhas[t], catalogo, schema)): t for t in filhas}
        for futuro in concurrent.futures.as_completed(futuros):
            try:
                futuro.result()
            except Exception as e:  # noqa: BLE001
                erros.append(f"{futuros[futuro]}: {e}")
    if erros:
        raise ErroGravacao("; ".join(sorted(erros)))
    return {t: len(linhas[t]) for t in esquema_sql.TABELAS if linhas[t]}


# ---------------------------------------------------------------------------
# Databricks (SDK) e integração com o app
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=4)
def executor_databricks(warehouse_id: str, perfil: Optional[str] = None) -> Executor:
    """Executor que roda os comandos num SQL warehouse pelo Databricks SDK (no Databricks Apps a autenticação
    é automática; fora dele, use `SENTINELA_SQL_PERFIL` com um perfil do Databricks CLI)."""
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.sql import (ExecuteStatementRequestOnWaitTimeout, StatementParameterListItem,
                                            StatementState)
    cliente = WorkspaceClient(profile=perfil) if perfil else WorkspaceClient()

    def executar(sql: str, parametros: List[Dict[str, str]]) -> None:
        resp = cliente.statement_execution.execute_statement(
            warehouse_id=warehouse_id, statement=sql, wait_timeout="50s",
            on_wait_timeout=ExecuteStatementRequestOnWaitTimeout.CANCEL,
            parameters=[StatementParameterListItem(name=p["name"], value=p["value"], type=p.get("type", "STRING"))
                        for p in parametros] or None)
        estado = resp.status.state if resp.status else None
        if estado != StatementState.SUCCEEDED:
            erro = resp.status.error.message if resp.status and resp.status.error else None
            raise ErroGravacao(erro or f"o comando terminou com estado {getattr(estado, 'value', estado)}")

    return executar


def configurado() -> bool:
    return bool(os.environ.get(ENV_WAREHOUSE, "").strip())


def gravar_se_configurado(caso: core.Caso, limpar: bool = False) -> Tuple[str, str]:
    """Grava o dossiê se a base estiver configurada. Devolve (status, mensagem), com status
    'desativado' (nada a fazer), 'ok' ou 'erro'. Nunca levanta exceção."""
    if not configurado():
        return "desativado", ""
    catalogo = os.environ.get(ENV_CATALOGO, esquema_sql.CATALOGO).strip() or esquema_sql.CATALOGO
    schema = os.environ.get(ENV_SCHEMA, esquema_sql.SCHEMA).strip() or esquema_sql.SCHEMA
    try:
        executar = executor_databricks(os.environ[ENV_WAREHOUSE].strip(), os.environ.get(ENV_PERFIL) or None)
        gravar_caso(caso, executar, catalogo, schema, limpar=limpar)
        return "ok", f"{catalogo}.{schema}"
    except Exception as e:  # noqa: BLE001 - a gravação na base nunca pode derrubar o app
        return "erro", str(e)[:400]


# ---------------------------------------------------------------------------
# Migração de casos já salvos (arquivos do Banco de Dossiês) para as tabelas
# ---------------------------------------------------------------------------

MARCADOR_ANTIGO = "Não informado"  # versões antigas do app preenchiam campos sem dado com este texto


def normalizar_caso_antigo(caso: core.Caso) -> List[str]:
    """Casos gerados por versões antigas podem ter campos com "Não informado". Hoje o campo sem dado fica em
    branco e some do dossiê, então a migração os trata como vazios. Devolve os campos alterados."""
    alterados: List[str] = []

    def varre(obj: Any, onde: str) -> None:
        for f in dataclasses.fields(obj):
            v = getattr(obj, f.name)
            if isinstance(v, str) and v.strip() == MARCADOR_ANTIGO:
                setattr(obj, f.name, "")
                alterados.append(f"{onde}{f.name}")
            elif isinstance(v, list):
                for i, x in enumerate(v):
                    if dataclasses.is_dataclass(x):
                        varre(x, f"{onde}{f.name}[{i}].")

    varre(caso, "")
    return alterados


def migrar_pasta(pasta: str, executar: Executor, catalogo: str = esquema_sql.CATALOGO,
                 schema: str = esquema_sql.SCHEMA) -> List[Dict[str, Any]]:
    """Grava nas tabelas todos os casos de um Banco de Dossiês em arquivos (por exemplo `./data` ou o Volume).
    Idempotente: cada caso é apagado e regravado, então rodar de novo não duplica. Só o dossiê é gravado."""
    armazenamento = core.ArmazenamentoLocal(pasta)
    relatorio: List[Dict[str, Any]] = []
    for item in armazenamento.listar_indice():
        numero = item["numero_caso"]
        try:
            caso = armazenamento.carregar_caso(numero)
            if caso is None:
                raise ErroGravacao("arquivo do caso não encontrado")
            limpos = normalizar_caso_antigo(caso)
            qtd = gravar_caso(caso, executar, catalogo, schema, limpar=True)
            relatorio.append({"numero_caso": numero, "tipo_caso": caso.tipo_caso, "status": "ok",
                              "linhas": qtd, "marcadores_removidos": limpos})
        except Exception as e:  # noqa: BLE001
            relatorio.append({"numero_caso": numero, "status": "erro", "erro": str(e)[:300]})
    return relatorio


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Migra casos já salvos (arquivos) para as tabelas de usr.sentinela_aml.")
    ap.add_argument("pasta", help="pasta do Banco de Dossiês (ex.: ./data ou /Volumes/.../dossies)")
    ap.add_argument("--warehouse", required=True, help="id do SQL warehouse")
    ap.add_argument("--perfil", help="perfil do Databricks CLI")
    args = ap.parse_args()
    resultado = migrar_pasta(args.pasta, executor_databricks(args.warehouse, args.perfil))
    for r in resultado:
        print(json.dumps(r, ensure_ascii=False))
    raise SystemExit(0 if all(r["status"] == "ok" for r in resultado) else 1)
