# -*- coding: utf-8 -*-
"""
Sentinela PLD - Aba "Informações do Caso" em HTML
=================================================

Gera os quatro cartões somente-leitura do dossiê (Alerta/Sentença, KYC,
Resumo de Movimentações e Thundera - AML 360) no formato das capturas do
manual: seções com título serifado, subtítulos com ✦ e "pílulas" de campo.

É usado em duas telas: na prévia abaixo do formulário e na aba Informações do
Caso. Todo texto vem escapado (html.escape); o gráfico entra como data-URI.
"""

from __future__ import annotations

import base64
from html import escape
from typing import List, Optional, Tuple

import estilo
from core import (
    Caso, ContraparteMovimentacao, grafico_do_caso, parse_valor_br,
    formatar_brl, percentual_restante, formatar_data_br, parse_data_br,
)

Par = Tuple[str, str]


def _p(*itens: Par) -> str:
    """Pílulas dos pares (rótulo, valor); pares com valor vazio são omitidos."""
    return estilo.pilulas([(r, v) for r, v in itens if str(v or "").strip()])


def _sub(texto: str) -> str:
    return f'<div class="sx-subhead">{escape(texto)}</div>'


def _texto(texto: str) -> str:
    return f'<div class="sx-texto">{escape(texto)}</div>'


def _cartao(titulo: str, corpo: str) -> str:
    return (f'<div class="sx-info-card"><div class="sx-sec-titulo">{escape(titulo)}</div>'
            f'{corpo}</div>')


def _dinheiro(txt: str) -> str:
    """'R$500.000,00' -> 'R$ 500.000,00' (o dossiê original separa o símbolo)."""
    v = parse_valor_br(txt)
    return "R$ " + formatar_brl(v).replace("R$", "") if (txt or "").strip() else "—"


def _pct(v: float) -> str:
    return f"{int(round(v))}%" if abs(v - round(v)) < 0.05 else f"{v:.1f}%".replace(".", ",")


# ---------------------------------------------------------------------------
# Cabeçalho
# ---------------------------------------------------------------------------

def cabecalho_html(caso: Caso) -> str:
    """Cartão do topo: número do caso, nome do cliente, avatar e risco geral."""
    avatar = "" if caso.eh_pj() else estilo.avatar_svg(caso.genero)
    return (
        '<div class="sx-info-card" style="padding:14px 22px 16px;">'
        '<div class="sx-dossie-cab">'
        f'<div class="sx-dossie-num">{escape(caso.numero_caso)}</div>'
        f'<div class="sx-dossie-nome">{avatar}<span>{escape(caso.nome_display() or "Sem nome")}</span>'
        f'{estilo.chip_risco(caso.risco_geral())}</div>'
        '</div></div>'
    )


# ---------------------------------------------------------------------------
# 1. Alerta / Sentença
# ---------------------------------------------------------------------------

def secao_alerta(caso: Caso) -> str:
    corpo = _p(
        ("Tipo de caso de calibração", caso.tipo_caso),
        ("Número do caso (gerado automaticamente)", caso.numero_caso),
        ("Fator gerador/alerta", caso.fator_gerador),
        ("Data do alerta", caso.data_alerta),
    )
    corpo += _sub("Descrição da Sentença") + _texto(caso.sentenca or "—")
    return _cartao("1. Alerta / Sentença", corpo)


# ---------------------------------------------------------------------------
# 2. KYC
# ---------------------------------------------------------------------------

def _flags_kyc(caso: Caso) -> str:
    """Região de risco, PEP, mídia negativa e históricos: só aparecem quando 'Sim'."""
    pares: List[Par] = []
    if caso.regiao_risco == "Sim":
        tipo = caso.tipo_regiao_risco
        if caso.tipo_regiao_risco_2:
            tipo = f"{tipo} — {caso.tipo_regiao_risco_2}" if tipo else caso.tipo_regiao_risco_2
        pares.append(("Região de risco", tipo or "Sim"))
    if caso.pep == "Sim":
        pares.append(("PEP", caso.tipo_pep or "Sim"))
        if caso.descricao_pep:
            pares.append(("Descrição do PEP e carência", caso.descricao_pep))
    if caso.midia_negativa == "Sim":
        pares.append(("Mídia negativa", caso.midia_negativa_detalhe or "Sim"))
    if caso.historico_pld == "Sim":
        pares.append(("Histórico de PLD", caso.historico_pld_detalhe or "Sim"))
    if caso.historico_fraude == "Sim":
        pares.append(("Histórico de fraudes", caso.historico_fraude_detalhe or "Sim"))
    return (_sub("Região de Risco, PEP e Históricos") + _p(*pares)) if pares else ""


def secao_kyc(caso: Caso) -> str:
    c = caso
    corpo = ""
    if c.eh_pj():
        corpo += _sub("Informações da Empresa")
        corpo += _p(("Nome da empresa", c.nome_empresa), ("Data de abertura", c.data_abertura),
                    ("Ramo de atividade", c.ramo_atividade), ("Porte", c.porte),
                    ("Faturamento presumido", c.faturamento_presumido), ("Endereço", c.endereco))
        corpo += _p(("Presença online", (c.presenca_online_detalhe or "Sim") if c.presenca_online == "Sim" else "Não"),
                    ("Fachada da empresa", (c.fachada_empresa_detalhe or "Sim") if c.fachada_empresa == "Sim" else "Não"))
        for i, s in enumerate(c.socios, 1):
            corpo += _sub(f"Sócio {i}")
            corpo += _p(("Nome", s.nome), ("Idade", s.idade), ("Endereço", s.endereco),
                        ("Renda presumida", s.renda_presumida), ("Patrimônio", s.patrimonio),
                        ("Risco", s.nivel_risco().title()))
            flags: List[Par] = []
            if s.regiao_risco == "Sim":
                flags.append(("Região de risco", s.tipo_regiao_risco or "Sim"))
            if s.pep == "Sim":
                flags.append(("PEP", s.tipo_pep or "Sim"))
                if s.descricao_pep:
                    flags.append(("Descrição do PEP", s.descricao_pep))
            if s.historico_pld == "Sim":
                flags.append(("Histórico de PLD", s.historico_pld_detalhe or "Sim"))
            if s.historico_fraude == "Sim":
                flags.append(("Histórico de fraudes", s.historico_fraude_detalhe or "Sim"))
            if s.midia_negativa == "Sim":
                flags.append(("Mídia negativa", s.midia_negativa_detalhe or "Sim"))
            corpo += _p(*flags)
    else:
        corpo += _sub("Informações Básicas do Cliente")
        corpo += _p(("Nome do cliente", c.nome_cliente), ("Idade", c.idade), ("Cidade/Estado", c.cidade_estado))
        corpo += _sub("Cadastro e Registros")
        corpo += _p(("Última atualização cadastral", c.ultima_atualizacao_cadastral),
                    ("Registro profissional", c.registro_profissional),
                    ("Renda presumida do cliente", c.renda_presumida),
                    ("Profissão informada pelo cliente", c.profissao_informada))
        if c.registro_societario == "Sim":
            corpo += _sub("Registro Societário")
            corpo += _p(("Razão social", c.reg_soc_razao_social), ("Data de abertura", c.reg_soc_data_abertura),
                        ("Situação cadastral", c.reg_soc_situacao_cadastral), ("Ramo de atividade", c.reg_soc_ramo_atividade))
        if c.rep_nome:
            corpo += _sub("Responsável Legal")
            corpo += _p(("Nome", c.rep_nome), ("Renda presumida", c.rep_renda_presumida),
                        ("Registro profissional", c.rep_reg_prof), ("Registro societário", c.rep_reg_soc),
                        ("Histórico de PLD", c.rep_hist_pld), ("Histórico de fraude", c.rep_hist_fraude))
    corpo += _flags_kyc(c)
    corpo += _sub("Outras Informações Relevantes") + _texto(c.outras_info or "—")
    return _cartao("2. KYC - KNOW YOUR CUSTOMER", corpo)


# ---------------------------------------------------------------------------
# 3. Resumo de Movimentações
# ---------------------------------------------------------------------------

def _contraparte(cp: ContraparteMovimentacao) -> str:
    out = _sub(cp.tipo or "Pessoa Física")
    if cp.tipo == "Pessoa Jurídica":
        out += _p(("Porcentagem", cp.porcentagem), ("Valor", cp.valor), ("Número de transações", cp.num_transacoes),
                  ("Nome", cp.nome), ("Cidade/Estado", cp.cidade_estado), ("Data de abertura", cp.data_abertura),
                  ("Ramo de atividade", cp.ramo_atividade), ("Porte", cp.porte),
                  ("Faturamento presumido", cp.faturamento_presumido))
    else:
        out += _p(("Porcentagem", cp.porcentagem), ("Valor", cp.valor), ("Número de transações", cp.num_transacoes),
                  ("Nome", cp.nome), ("Idade", cp.idade), ("Cidade/Estado", cp.cidade_estado),
                  ("Renda presumida", cp.renda_presumida), ("Registro profissional", cp.registro_profissional))
    flags: List[Par] = []
    for rot, ativo, det in (("Registro societário", cp.registro_societario, cp.registro_societario_detalhe),
                            ("Região de risco", cp.regiao_risco, cp.regiao_risco_detalhe),
                            ("PEP", cp.pep, cp.pep_detalhe),
                            ("Histórico de PLD", cp.historico_pld, cp.historico_pld_detalhe),
                            ("Histórico de fraude", cp.historico_fraude, cp.historico_fraude_detalhe),
                            ("Mídia negativa", cp.midia_negativa, cp.midia_negativa_detalhe)):
        if ativo == "Sim":
            flags.append((rot, det or "Sim"))
    return out + _p(*flags)


def _lado(titulo: str, lista: List[ContraparteMovimentacao], rotulo_lado: str) -> str:
    corpo = _sub(titulo)
    blocos = [_contraparte(cp) for cp in lista]
    # a primeira contraparte já traz o próprio subtítulo "Pessoa Física"
    corpo += '<hr class="sx-linha-sep"/>'.join(blocos) if blocos else _texto("Nenhuma contraparte descrita.")
    resto = percentual_restante(lista)
    if lista and resto is not None:
        corpo += f'<div class="sx-resto">{_pct(resto)} restante é referente às demais contrapartes de {rotulo_lado}</div>'
    return corpo


def secao_movimentacoes(caso: Caso) -> str:
    c = caso
    corpo = _p(("Período", c.mov_periodo), ("Total de créditos", c.mov_total_credito),
               ("Total de contrapartes (crédito)", c.mov_total_contrapartes_credito))
    corpo += _lado("Contrapartes Principais de Crédito", c.contrapartes_credito, "crédito")
    corpo += _p(("Total de débitos", c.mov_total_debito),
                ("Total de contrapartes (débito)", c.mov_total_contrapartes_debito))
    corpo += _lado("Contrapartes Principais de Débito", c.contrapartes_debito, "débito")
    if c.outras_movimentacoes:
        corpo += _sub("Outras Movimentações")
        for i, m in enumerate(c.outras_movimentacoes, 1):
            corpo += (f'<div class="sx-texto"><b>{i}. {escape(m.tipo)}:</b><br/>'
                      f'{escape(m.info or "—")}</div>')
    return _cartao("3. Resumo de Movimentações", corpo)


# ---------------------------------------------------------------------------
# 4. Thundera - AML 360
# ---------------------------------------------------------------------------

def secao_thundera(caso: Caso, grafico_png: Optional[bytes] = None) -> str:
    c = caso
    corpo = ""
    if c.comp_arredondamento == "Sim" and c.arredondamento_itens:
        corpo += _sub("Transações em Perfil de Arredondamento nas Unidades de Milhar")
        for i, a in enumerate(c.arredondamento_itens, 1):
            lado = (a.cred_deb or "Créditos").upper()
            corpo += _p((f"{lado} — Quantidade", a.quantidade), (f"{lado} — Valor {i}", a.valor))
    elif c.comp_arredondamento == "Não":
        corpo += _sub("Transações em Perfil de Arredondamento nas Unidades de Milhar")
        corpo += _texto("Não identificado.")
    if c.comp_pix == "Sim" and c.pix_itens:
        corpo += _sub("Mensagens Pix")
        for i, p in enumerate(c.pix_itens, 1):
            lado = (p.cred_deb or "Créditos").upper()
            corpo += _p((f"{lado} — Quantidade", p.quantidade), (f"{lado} — Mensagem {i}", p.mensagem))
    if c.comp_evasao:
        corpo += _sub("Timeline de Transferências")
        corpo += ('<div class="sx-pills">'
                  + estilo.pilula("Créditos", _dinheiro(c.mov_total_credito), "gde verde")
                  + estilo.pilula("Débitos", _dinheiro(c.mov_total_debito), "gde vermelho")
                  + estilo.pilula("Padrão", c.comp_evasao) + "</div>")
        png = grafico_png or grafico_do_caso(c)
        if png:
            b64 = base64.b64encode(png).decode("ascii")
            corpo += f'<div class="sx-grafico"><img alt="Timeline de Transferências" src="data:image/png;base64,{b64}"/></div>'
    if c.comp_mudanca_comportamento.strip():
        corpo += _sub("Mudança de Comportamento")
        corpo += '<div class="sx-mudanca">' + "<br/>".join(
            escape(l) for l in c.comp_mudanca_comportamento.splitlines() if l.strip()) + "</div>"
    corpo += _p(("Data de abertura da conta/data do último reporte", c.comp_data_abertura_ultimo_reporte))
    fatores = c.fatores_risco()
    if fatores:
        corpo += _sub("Fatores considerados no risco geral")
        corpo += '<div class="sx-texto">' + "<br/>".join(
            f"&bull; <b>{escape(n.title())}</b> — {escape(d)}" for n, d in fatores) + "</div>"
    return _cartao("4. Thundera - AML 360", corpo)


# ---------------------------------------------------------------------------
# Conjunto
# ---------------------------------------------------------------------------

def informacoes_html(caso: Caso, grafico_png: Optional[bytes] = None) -> List[str]:
    """Os quatro cartões da aba Informações do Caso, na ordem do dossiê."""
    return [secao_alerta(caso), secao_kyc(caso), secao_movimentacoes(caso),
            secao_thundera(caso, grafico_png)]
