# -*- coding: utf-8 -*-
"""
Sentinela PLD - esquema SQL (Unity Catalog) dos dossiês gerados
===============================================================

Gera o DDL das tabelas Delta de `usr.sentinela_aml` a partir das classes do `core.py`, para o esquema
acompanhar o modelo: um teste (`tests/test_esquema_sql.py`) falha se um campo novo do Caso não tiver
coluna/tabela (ou não for declarado como "não gravado").

SÓ O DOSSIÊ GERADO É GRAVADO ("Informações do Caso": alerta, KYC, movimentações e comportamentos AML 360).
Resolução do Caso e Avaliação de Qualidade NÃO são gravadas: ficam sempre em branco, para o time preencher
na calibração dentro do app. A intenção é deixar os casos disponíveis para consulta, por tipo de caso.

Modelo (1 linha por caso em `casos`; as listas ficam em tabelas filhas ligadas por `numero_caso`, todas com
`tipo_caso` repetido para filtrar sem JOIN):

    casos                  um dossiê (campos escalares + colunas derivadas tipadas + o JSON do dossiê)
    contrapartes           contrapartes principais de crédito/débito (Bloco 3), com o mini-KYC
    socios                 sócios (caso PJ)
    outras_movimentacoes   Outras Movimentações (saques, boletos, criptomoedas...), com o montante extraído
    arredondamentos        transações em perfil de arredondamento (Bloco 4)
    mensagens_pix          mensagens Pix (Bloco 4)
    timeline_diaria        série diária dos gráficos (bancária e de criptomoedas)

    casos_pf, casos_pj, casos_cripto, casos_nuinvest, casos_under18
                           views de `casos`, uma por tipo de caso, só com as colunas daquele tipo

Colunas com o texto original do formulário mantêm o nome do campo do Caso (ex.: `mov_total_credito`
= "R$500.000,00"); as versões tipadas para análise têm sufixo `_valor` (DOUBLE) ou `_dt` (DATE).

Uso:
    python esquema_sql.py                       # imprime o DDL
    python esquema_sql.py --aplicar --warehouse <id> [--perfil <perfil do databricks cli>]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
import typing
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import core

CATALOGO = "usr"
SCHEMA = "sentinela_aml"

# ---- o que NÃO é gravado (Resolução do Caso e Avaliação de Qualidade) -------------------------------
EXCLUIDOS_CASOS = {
    "parecer_final", "alineas", "anexos", "diligencia", "resolucao_bloqueada_em",   # Resolução do Caso
    "scorecard_tipo", "scorecard_feedback", "scorecard_salvo_em",                     # Avaliação de Qualidade
}
NAO_GRAVADOS_LISTAS = {
    "jurisprudencias_selecionadas", "razoes_clear_selecionadas", "razoes_cancelamento_selecionadas",
    "resolucao_salva_em", "scorecard_drivers_marcados",
}

# Campos do Caso guardados como TIMESTAMP (no Caso são textos ISO; "" vira NULL ao gravar).
CAMPOS_TIMESTAMP = {"criado_em", "atualizado_em"}
CAMPOS_INT = {"schema_version"}


@dataclass
class Coluna:
    nome: str
    tipo: str = "STRING"
    comentario: str = ""
    nao_nulo: bool = False


# Colunas derivadas e tipadas da tabela `casos` (o texto original continua na coluna de mesmo nome do campo).
DERIVADAS_CASOS: List[Coluna] = [
    Coluna("data_alerta_dt", "DATE", "data_alerta em formato de data"),
    Coluna("mov_periodo_inicio", "DATE", "primeiro dia do período analisado"),
    Coluna("mov_periodo_fim", "DATE", "último dia do período analisado"),
    Coluna("mov_total_credito_valor", "DOUBLE", "total de créditos em R$ (número)"),
    Coluna("mov_total_debito_valor", "DOUBLE", "total de débitos em R$ (número)"),
    Coluna("renda_presumida_valor", "DOUBLE", "renda presumida do cliente em R$ (número)"),
    Coluna("faturamento_presumido_valor", "DOUBLE", "faturamento presumido anual da empresa em R$ (número)"),
    Coluna("montante_cripto_valor", "DOUBLE", "montante das Outras Movimentações do tipo Criptomoedas, em R$"),
    Coluna("caso_json", "STRING", "dossiê completo em JSON (sem Resolução e Avaliação), para reconstruir o caso"),
    Coluna("gravado_em", "TIMESTAMP", "quando esta linha foi gravada na tabela"),
]

COMENTARIOS_CASOS: Dict[str, str] = {
    "numero_caso": "número do caso (chave), ex.: 2026-426865",
    "tipo_caso": "Pessoa Física (PF), Pessoa Jurídica (PJ), Cripto, NuInvest ou Under 18",
    "schema_version": "versão do formato do caso",
    "fator_gerador": "nome do alerta (digitado pelo analista)",
    "data_alerta": "data do alerta, DD/MM/AAAA (texto original)",
    "sentenca": "descrição da sentença (digitada pelo analista)",
    "genero": "M ou F (define o avatar do dossiê)",
    "comp_evasao": "timeline bancária: Rápida Evasão, Sem Rápida Evasão, Só Créditos, Só Débitos ou Evasão Parcial",
    "comp_evasao_cripto": "timeline de criptomoedas (só casos Cripto): mesmos modos, exceto Evasão Parcial",
    "outras_info": "Outras Informações Relevantes do KYC, uma por linha",
}

# Listas/dicionários do Caso -> tabela onde são gravados (ou NAO_GRAVADOS_LISTAS).
COBERTURA_LISTAS: Dict[str, str] = {
    "socios": "socios",
    "contrapartes_credito": "contrapartes",
    "contrapartes_debito": "contrapartes",
    "outras_movimentacoes": "outras_movimentacoes",
    "arredondamento_itens": "arredondamentos",
    "pix_itens": "mensagens_pix",
    "timeline_creditos": "timeline_diaria",
    "timeline_debitos": "timeline_diaria",
    "timeline_cripto_creditos": "timeline_diaria",
    "timeline_cripto_debitos": "timeline_diaria",
}

TABELAS = ["casos", "contrapartes", "socios", "outras_movimentacoes", "arredondamentos", "mensagens_pix",
           "timeline_diaria"]

CHAVES: Dict[str, List[str]] = {
    "casos": ["numero_caso"],
    "contrapartes": ["numero_caso", "lado", "ordem"],
    "socios": ["numero_caso", "ordem"],
    "outras_movimentacoes": ["numero_caso", "ordem"],
    "arredondamentos": ["numero_caso", "ordem"],
    "mensagens_pix": ["numero_caso", "ordem"],
    "timeline_diaria": ["numero_caso", "timeline", "data"],
}

COMENTARIOS_TABELAS: Dict[str, str] = {
    "casos": "Dossiês gerados no Sentinela, um por linha (alerta, KYC, movimentações e comportamentos AML 360). "
             "Resolução e Avaliação de Qualidade não são gravadas.",
    "contrapartes": "Contrapartes principais de crédito e débito de cada dossiê (Bloco 3), com o mini-KYC.",
    "socios": "Sócios dos dossiês de Pessoa Jurídica.",
    "outras_movimentacoes": "Outras Movimentações (saques, boletos, cartões, empréstimos, criptomoedas, "
                            "investimentos...).",
    "arredondamentos": "Transações em perfil de arredondamento nas unidades de milhar (Bloco 4), por valor e lado.",
    "mensagens_pix": "Mensagens Pix observadas (Bloco 4).",
    "timeline_diaria": "Série diária dos gráficos de Timeline de Transferências (bancária e de criptomoedas).",
}

# ---- views por tipo de caso ----------------------------------------------------------------------------
GRUPO_PF = ["nome_cliente", "genero", "idade", "cidade_estado", "ultima_atualizacao_cadastral",
            "profissao_informada", "renda_presumida", "renda_presumida_valor", "registro_profissional",
            "registro_societario", "reg_soc_razao_social", "reg_soc_data_abertura", "reg_soc_situacao_cadastral",
            "reg_soc_ramo_atividade", "reg_soc_porte", "reg_soc_faturamento_presumido", "reg_soc_endereco"]
GRUPO_PJ = ["nome_empresa", "data_abertura", "ramo_atividade", "porte", "faturamento_presumido",
            "faturamento_presumido_valor", "endereco", "presenca_online", "fachada_empresa"]
GRUPO_UNDER18 = ["rep_nome", "rep_renda_presumida", "rep_reg_prof", "rep_reg_soc", "rep_hist_pld", "rep_hist_fraude"]
GRUPO_CRIPTO = ["comp_evasao_cripto", "timeline_cripto_inicio", "montante_cripto_valor"]
COLUNAS_TECNICAS = ["caso_json", "schema_version"]  # ficam só em `casos`

VIEWS: Dict[str, Tuple[str, List[str]]] = {
    "casos_pf": (core.TIPOS_CASO[0], GRUPO_PF),
    "casos_pj": (core.TIPO_PJ, GRUPO_PJ),
    "casos_cripto": (core.TIPO_CRIPTO, GRUPO_PF + GRUPO_CRIPTO),
    "casos_nuinvest": (core.TIPO_NUINVEST, GRUPO_PF),
    "casos_under18": (core.TIPO_UNDER18, GRUPO_PF + GRUPO_UNDER18),
}


def _nome(objeto: str) -> str:
    return f"{CATALOGO}.{SCHEMA}.{objeto}"


def _eh_escalar(campo: dataclasses.Field, hints: Dict[str, object]) -> bool:
    return typing.get_origin(hints[campo.name]) is None  # List[...] e Dict[...] têm origem; str e int não


def campos_escalares(classe: type) -> List[dataclasses.Field]:
    hints = typing.get_type_hints(classe)
    return [f for f in dataclasses.fields(classe) if _eh_escalar(f, hints)]


def campos_de_lista(classe: type) -> List[str]:
    hints = typing.get_type_hints(classe)
    return [f.name for f in dataclasses.fields(classe) if not _eh_escalar(f, hints)]


def _tipo_sql(nome_campo: str) -> str:
    if nome_campo in CAMPOS_TIMESTAMP:
        return "TIMESTAMP"
    return "INT" if nome_campo in CAMPOS_INT else "STRING"


def definir_esquema() -> Dict[str, List[Coluna]]:
    """Colunas de cada tabela, na ordem em que aparecem no CREATE TABLE."""
    esq: Dict[str, List[Coluna]] = {}

    cols = [Coluna(f.name, _tipo_sql(f.name), COMENTARIOS_CASOS.get(f.name, ""),
                   nao_nulo=f.name in ("numero_caso", "tipo_caso"))
            for f in campos_escalares(core.Caso) if f.name not in EXCLUIDOS_CASOS]
    esq["casos"] = cols + DERIVADAS_CASOS

    def base(*extras: Coluna) -> List[Coluna]:
        return [Coluna("numero_caso", "STRING", "dossiê a que pertence", True),
                Coluna("tipo_caso", "STRING", "tipo do caso (repetido de `casos` para filtrar sem JOIN)", True),
                *extras]

    esq["contrapartes"] = base(
        Coluna("lado", "STRING", "credito ou debito", True),
        Coluna("ordem", "INT", "posição na lista do lado (0 = primeira)", True),
        *[Coluna(f.name) for f in campos_escalares(core.ContraparteMovimentacao)],
        Coluna("porcentagem_valor", "DOUBLE", "porcentagem do total do lado (número, ex.: 14.0)"),
        Coluna("valor_valor", "DOUBLE", "valor movimentado em R$ (número)"),
        Coluna("renda_presumida_valor", "DOUBLE", "renda presumida em R$ (número, contraparte PF)"),
        Coluna("faturamento_presumido_valor", "DOUBLE", "faturamento presumido em R$ (número, contraparte PJ)"))
    esq["socios"] = base(
        Coluna("ordem", "INT", "posição na lista de sócios (0 = primeiro)", True),
        *[Coluna(f.name) for f in campos_escalares(core.Socio)],
        Coluna("renda_presumida_valor", "DOUBLE", "renda presumida em R$ (número)"),
        Coluna("patrimonio_valor", "DOUBLE", "patrimônio em R$ (número)"))
    esq["outras_movimentacoes"] = base(
        Coluna("ordem", "INT", "posição na lista", True),
        *[Coluna(f.name) for f in campos_escalares(core.OutraMovimentacao)],
        Coluna("montante_valor", "DOUBLE", "maior valor em R$ citado na descrição (número)"))
    esq["arredondamentos"] = base(
        Coluna("ordem", "INT", "posição na lista", True),
        *[Coluna(f.name) for f in campos_escalares(core.ItemArredondamento)],
        Coluna("quantidade_valor", "INT", "quantidade de transações (número)"),
        Coluna("valor_valor", "DOUBLE", "valor de referência em R$ (número)"))
    esq["mensagens_pix"] = base(
        Coluna("ordem", "INT", "posição na lista", True),
        *[Coluna(f.name) for f in campos_escalares(core.MensagemPix)],
        Coluna("quantidade_valor", "INT", "quantidade de mensagens (número)"))
    esq["timeline_diaria"] = base(
        Coluna("timeline", "STRING", "bancaria ou cripto", True),
        Coluna("data", "DATE", "dia da barra do gráfico", True),
        Coluna("creditos", "DOUBLE", "créditos do dia em R$"),
        Coluna("debitos", "DOUBLE", "débitos do dia em R$"))
    return esq


def _def_coluna(c: Coluna) -> str:
    texto = f"  {c.nome} {c.tipo}" + (" NOT NULL" if c.nao_nulo else "")
    if c.comentario:
        texto += " COMMENT '" + c.comentario.replace("'", "''") + "'"
    return texto


def gerar_ddl() -> List[str]:
    """Os CREATE TABLE, na ordem certa (casos primeiro, por causa das chaves estrangeiras)."""
    ddl: List[str] = []
    for tabela, cols in definir_esquema().items():
        linhas = [_def_coluna(c) for c in cols]
        linhas.append(f"  CONSTRAINT pk_{tabela} PRIMARY KEY ({', '.join(CHAVES[tabela])})")
        if tabela != "casos":
            linhas.append(f"  CONSTRAINT fk_{tabela}_caso FOREIGN KEY (numero_caso) "
                          f"REFERENCES {_nome('casos')} (numero_caso)")
        comentario = COMENTARIOS_TABELAS[tabela].replace("'", "''")
        ddl.append(f"CREATE TABLE IF NOT EXISTS {_nome(tabela)} (\n" + ",\n".join(linhas) +
                   f"\n)\nUSING DELTA\nCOMMENT '{comentario}'")
    return ddl


def colunas_da_view(grupo: List[str]) -> List[str]:
    """Colunas de `casos` que a view do tipo mostra: as comuns + as do grupo do tipo."""
    todas = [c.nome for c in definir_esquema()["casos"]]
    especificas = set(GRUPO_PF) | set(GRUPO_PJ) | set(GRUPO_UNDER18) | set(GRUPO_CRIPTO)
    return [n for n in todas if n not in COLUNAS_TECNICAS and (n not in especificas or n in grupo)]


def gerar_views() -> List[str]:
    views = []
    for nome, (tipo, grupo) in VIEWS.items():
        cols = ",\n  ".join(colunas_da_view(grupo))
        comentario = f"Dossiês do tipo {tipo}, só com as colunas desse tipo de caso.".replace("'", "''")
        tipo_sql = tipo.replace("'", "''")
        views.append(f"CREATE OR REPLACE VIEW {_nome(nome)}\nCOMMENT '{comentario}'\nAS SELECT\n  {cols}\n"
                     f"FROM {_nome('casos')}\nWHERE tipo_caso = '{tipo_sql}'")
    return views


def executar_sql(comando: str, warehouse_id: str, perfil: Optional[str] = None) -> Dict[str, object]:
    """Executa um comando no SQL warehouse pelo Databricks CLI (API de Statement Execution)."""
    corpo = json.dumps({"warehouse_id": warehouse_id, "statement": comando, "wait_timeout": "50s",
                        "on_wait_timeout": "CANCEL"})
    cmd = ["databricks", "api", "post", "/api/2.0/sql/statements", "--json", corpo]
    if perfil:
        cmd += ["--profile", perfil]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    saida = r.stdout[r.stdout.find("{"):] if "{" in r.stdout else r.stdout
    try:
        return json.loads(saida)
    except ValueError:
        return {"status": {"state": "FAILED", "error": {"message": (r.stderr or r.stdout)[-500:]}}}


def aplicar(warehouse_id: str, perfil: Optional[str] = None) -> bool:
    """Cria as tabelas e as views (IF NOT EXISTS / OR REPLACE: não apaga nem altera dados)."""
    ok = True
    for comando in gerar_ddl() + gerar_views():
        objeto = comando.split(f"{CATALOGO}.{SCHEMA}.")[1].split()[0]
        resp = executar_sql(comando, warehouse_id, perfil)
        estado = resp.get("status", {}).get("state")
        if estado != "SUCCEEDED":
            ok = False
            msg = resp.get("status", {}).get("error", {}).get("message", resp)
            print(f"ERRO em {objeto}: {estado} - {msg}", file=sys.stderr)
        else:
            print(f"ok  {_nome(objeto)}")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true", help="cria as tabelas e views no Databricks")
    ap.add_argument("--warehouse", help="id do SQL warehouse")
    ap.add_argument("--perfil", help="perfil do Databricks CLI")
    args = ap.parse_args()
    if args.aplicar:
        if not args.warehouse:
            ap.error("--aplicar exige --warehouse")
        sys.exit(0 if aplicar(args.warehouse, args.perfil) else 1)
    print(";\n\n".join(gerar_ddl() + gerar_views()) + ";")
