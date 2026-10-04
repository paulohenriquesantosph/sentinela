# -*- coding: utf-8 -*-
"""
Sentinela PLD - PDF do dossiê
=============================

Gera o PDF do dossiê no servidor, com as mesmas três abas da tela:

    Informações do Caso  ·  Resolução do Caso  ·  Avaliação de Qualidade

API:
    gerar_pdf(caso, escopo="completo")
        "completo"    -> Informações + Resolução + Avaliação (PDF guardado no Banco)
        "resolucao"   -> Informações + Resolução (botão da aba Resolução)
        "avaliacao"   -> só a Avaliação de Qualidade (botão da aba Avaliação)
        "informacoes" -> só a primeira aba
    gerar_pdf_dossie(caso, grafico_png=None)   # compatibilidade: escopo "completo"

Todo texto vindo do usuário passa por escape (nada é injetado cru no Paragraph).
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from io import BytesIO
from typing import Any, List, Optional, Tuple
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
    Image as RLImage, KeepTogether, PageBreak,
)

import core
from opcoes import (
    JURISPRUDENCIA_NUPAGAMENTOS, JURISPRUDENCIA_REPORTAR_NUINVEST,
    JURISPRUDENCIA_REPORTAR_CANCELAR_NUINVEST,
)

ESCOPOS = ("completo", "resolucao", "avaliacao", "informacoes")

# ---------------------------------------------------------------------------
# Paleta e fontes
# ---------------------------------------------------------------------------
C = colors.HexColor
PAPER = C("#EEE3CE")
PAPER_ALT = C("#F3EADA")
INK = C("#2A2035")
ACCENT = C("#6C4E97")
PURPLE_DEEP = C("#3E2A63")
PURPLE_SOFT = C("#9C82C4")
LINE = C("#C9B6DE")
GOLD = C("#C9A76B")
VERDE = C("#2F6F62")
AMBAR = C("#B8863B")
VERMELHO = C("#A13D2E")
NEUTRO_COR = C("#6B6475")

SERIF = "Times-Bold"
SANS = "Helvetica"
SANS_B = "Helvetica-Bold"
MONO_B = "Courier-Bold"
MONO = "Courier"
SIMBOLOS = "DejaVuSans"

_FONTES_OK = False


def _registrar_fontes() -> None:
    """Registra a DejaVu Sans (vem com o matplotlib) só para símbolos como ✦ e ✓."""
    global _FONTES_OK
    if _FONTES_OK:
        return
    try:
        import matplotlib
        caminho = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf")
        pdfmetrics.registerFont(TTFont(SIMBOLOS, caminho))
        _FONTES_OK = True
    except Exception:  # noqa: BLE001 - sem a fonte, usamos símbolos ASCII
        _FONTES_OK = False


def _sym(simbolo: str, alternativa: str, cor: Optional[str] = None) -> str:
    if _FONTES_OK:
        c = f' color="{cor}"' if cor else ""
        return f'<font name="{SIMBOLOS}"{c}>{simbolo}</font>'
    return alternativa


# ---------------------------------------------------------------------------
# Texto seguro
# ---------------------------------------------------------------------------
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _t(texto: Any, vazio: str = "") -> str:
    """Escapa texto do usuário para o Paragraph e converte quebras de linha em <br/>."""
    if texto is None:
        return vazio
    s = _CTRL_RE.sub("", str(texto)).replace("\r\n", "\n").replace("\r", "\n")
    if not s.strip():
        return vazio
    return escape(s).replace("\n", "<br/>")


def _fmt_ts(iso: str) -> str:
    """ISO -> 'DD/MM/AAAA, HH:MM:SS' (devolve o original se não for ISO)."""
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y, %H:%M:%S")
    except (TypeError, ValueError):
        return iso or ""


def _hex(cor) -> str:
    return "#%02X%02X%02X" % (int(cor.red * 255), int(cor.green * 255), int(cor.blue * 255))


# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------
def _estilos() -> dict:
    def ps(nome, **kw):
        base = dict(fontName=SANS, fontSize=9.5, leading=13, textColor=INK)
        base.update(kw)
        return ParagraphStyle(nome, **base)

    return {
        "eyebrow": ps("eyebrow", fontName=MONO_B, fontSize=7.5, leading=10, textColor=ACCENT),
        "caso": ps("caso", fontName=MONO_B, fontSize=8.5, leading=11, textColor=ACCENT),
        "nome": ps("nome", fontName=SERIF, fontSize=21, leading=25, textColor=PURPLE_DEEP),
        "aba": ps("aba", fontName=MONO_B, fontSize=8.5, leading=11, textColor=colors.white),
        "secao": ps("secao", fontName=SERIF, fontSize=14.5, leading=18, textColor=PURPLE_DEEP,
                    spaceBefore=12, spaceAfter=3),
        "sub": ps("sub", fontName=SERIF, fontSize=10.8, leading=14, textColor=PURPLE_DEEP,
                  spaceBefore=8, spaceAfter=2),
        "texto": ps("texto", fontSize=9.5, leading=13.5),
        "texto_peq": ps("texto_peq", fontSize=8.5, leading=11.5, textColor=ACCENT),
        "aplic": ps("aplic", fontSize=7.8, leading=10.2, textColor=ACCENT, leftIndent=14),
        "crit": ps("crit", fontName=SANS_B, fontSize=9, leading=11.5, leftIndent=14, firstLineIndent=-14),
        "pl": ps("pl", fontName=MONO_B, fontSize=6.3, leading=8, textColor=ACCENT),
        "pv": ps("pv", fontName=SANS_B, fontSize=9.2, leading=11.5),
        "status_ok": ps("status_ok", fontName=MONO_B, fontSize=7.2, leading=9.5, textColor=VERDE),
        "status_pend": ps("status_pend", fontName=MONO_B, fontSize=7.2, leading=9.5, textColor=AMBAR),
        "salvo": ps("salvo", fontName=MONO, fontSize=7.5, leading=10, textColor=ACCENT),
        "selo": ps("selo", fontName=MONO_B, fontSize=13, leading=16, alignment=1),
        "nota_rot": ps("nota_rot", fontName=MONO_B, fontSize=7.5, leading=10, textColor=ACCENT),
        "nota": ps("nota", fontName=SANS_B, fontSize=32, leading=36),
        "cartao_rot": ps("cartao_rot", fontName=MONO_B, fontSize=6.8, leading=9, textColor=ACCENT),
        "cartao_val": ps("cartao_val", fontName=SANS_B, fontSize=15, leading=18),
        "nota_rodape": ps("nota_rodape", fontName=MONO, fontSize=7.2, leading=9.5, textColor=ACCENT),
    }


# ---------------------------------------------------------------------------
# Blocos visuais
# ---------------------------------------------------------------------------
class _Ctx:
    """Largura útil da página e estilos compartilhados."""

    def __init__(self) -> None:
        self.largura = A4[0] - 3.4 * cm
        self.st = _estilos()


def _linha(cor=LINE, dash=None, espessura=0.8, antes=1, depois=4) -> HRFlowable:
    return HRFlowable(width="100%", color=cor, thickness=espessura, dash=dash,
                      spaceBefore=antes, spaceAfter=depois)


def _titulo_secao(ctx: _Ctx, texto: str) -> List[Any]:
    return [Paragraph(_t(texto), ctx.st["secao"]), _linha(LINE, None, 1.0, 0, 6)]


def _subtitulo(ctx: _Ctx, texto: str) -> List[Any]:
    marca = _sym("✦", "*", _hex(ACCENT))
    return [Paragraph(f"{marca} {_t(texto)}", ctx.st["sub"]),
            _linha(PURPLE_SOFT, (1, 2), 0.9, 0, 5)]


def _pilula(ctx: _Ctx, rotulo: str, valor: str, cor=None) -> Tuple[Table, float]:
    """Caixa com rótulo pequeno em caixa-alta e valor em negrito."""
    valor = valor if (valor or "").strip() else "—"
    rot = rotulo.upper()
    lw = stringWidth(rot, MONO_B, 6.3)
    vw = stringWidth(valor.replace("\n", " "), SANS_B, 9.2)
    w = min(max(lw, vw) + 18, ctx.largura)
    estilo_v = ParagraphStyle("pvc", parent=ctx.st["pv"], textColor=cor or INK)
    t = Table([[Paragraph(_t(rot), ctx.st["pl"])], [Paragraph(_t(valor), estilo_v)]], colWidths=[w])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPER_ALT),
        ("BOX", (0, 0), (-1, -1), 0.8, LINE),
        ("ROUNDEDCORNERS", [5, 5, 5, 5]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (0, 0), 4), ("BOTTOMPADDING", (0, 0), (0, 0), 0),
        ("TOPPADDING", (0, 1), (0, 1), 1), ("BOTTOMPADDING", (0, 1), (0, 1), 5),
    ]))
    return t, w


def _pilulas(ctx: _Ctx, itens: List[Tuple[str, str]], cores: Optional[dict] = None) -> List[Any]:
    """Distribui as pílulas em linhas que cabem na largura da página."""
    gap = 5
    linhas: List[List[Tuple[Table, float]]] = [[]]
    uso = 0.0
    for rotulo, valor in itens:
        p, w = _pilula(ctx, rotulo, valor, (cores or {}).get(rotulo))
        if linhas[-1] and uso + gap + w > ctx.largura:
            linhas.append([])
            uso = 0.0
        uso += (gap if linhas[-1] else 0) + w
        linhas[-1].append((p, w))
    out: List[Any] = []
    for linha in linhas:
        if not linha:
            continue
        dados, larguras = [], []
        for i, (p, w) in enumerate(linha):
            if i:
                dados.append("")
                larguras.append(gap)
            dados.append(p)
            larguras.append(w)
        t = Table([dados], colWidths=larguras, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        out.append(t)
        out.append(Spacer(1, 4))
    return out


def _texto(ctx: _Ctx, texto: Any, vazio: str = "—", estilo: str = "texto") -> Paragraph:
    return Paragraph(_t(texto, vazio), ctx.st[estilo])


def _faixa_aba(ctx: _Ctx, titulo: str) -> Table:
    t = Table([[Paragraph(_t(titulo.upper()), ctx.st["aba"])]], colWidths=[ctx.largura])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PURPLE_DEEP),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _cor_selo(estilo: str):
    return {"verde": VERDE, "ambar": AMBAR, "vermelho": VERMELHO,
            "neutro": NEUTRO_COR}.get(estilo, ACCENT)


def _cor_nota(nota: float):
    return {"verde": VERDE, "ambar": AMBAR}.get(core.faixa_nota(nota), VERMELHO)


# ---------------------------------------------------------------------------
# Cabeçalho do dossiê
# ---------------------------------------------------------------------------
def _cabecalho(ctx: _Ctx, caso) -> List[Any]:
    esquerda = [
        Paragraph("SENTINELA PLD &mdash; DOSSIÊ", ctx.st["eyebrow"]),
        Spacer(1, 3),
        Paragraph(_t(caso.numero_caso), ctx.st["caso"]),
        Paragraph(_t(caso.nome_display(), "Sem nome"), ctx.st["nome"]),
        Paragraph(_t(caso.tipo_caso), ctx.st["texto_peq"]),
    ]
    t = Table([[esquerda]], colWidths=[ctx.largura])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (0, 0), "TOP"),
        ("BOX", (0, 0), (-1, -1), 2.2, PURPLE_DEEP), ("ROUNDEDCORNERS", [9, 9, 9, 9]),
        ("BACKGROUND", (0, 0), (-1, -1), PAPER_ALT),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return [t, Spacer(1, 8)]


# ---------------------------------------------------------------------------
# Aba 1 - Informações do Caso
# ---------------------------------------------------------------------------
def _com_detalhe(valor: str, *detalhes: str) -> str:
    extras = [d.strip() for d in detalhes if d and d.strip()]
    return valor + (" — " + " · ".join(extras) if extras else "")


def _secao_alerta(ctx: _Ctx, caso) -> List[Any]:
    out = _titulo_secao(ctx, "1. Alerta / Sentença")
    out += _pilulas(ctx, [
        ("Tipo de caso de calibração", caso.tipo_caso),
        ("Número do caso (gerado automaticamente)", caso.numero_caso),
        ("Fator gerador/alerta", caso.fator_gerador),
        ("Data do alerta", caso.data_alerta),
    ])
    out += _subtitulo(ctx, "Descrição da Sentença")
    out.append(_texto(ctx, caso.sentenca))
    return out


def _flags_kyc(caso) -> List[Tuple[str, str]]:
    itens: List[Tuple[str, str]] = []
    if caso.regiao_risco == "Sim":
        itens.append(("Região de risco", _com_detalhe("Sim", caso.tipo_regiao_risco, caso.tipo_regiao_risco_2)))
    if caso.pep == "Sim":
        itens.append(("PEP", _com_detalhe("Sim", caso.tipo_pep, caso.descricao_pep)))
    if caso.midia_negativa == "Sim":
        itens.append(("Mídia negativa", _com_detalhe("Sim", caso.midia_negativa_detalhe)))
    if caso.historico_pld == "Sim":
        itens.append(("Histórico de PLD", _com_detalhe("Sim", caso.historico_pld_detalhe)))
    if caso.historico_fraude == "Sim":
        itens.append(("Histórico de fraude", _com_detalhe("Sim", caso.historico_fraude_detalhe)))
    return itens


def _secao_kyc(ctx: _Ctx, caso) -> List[Any]:
    out = _titulo_secao(ctx, "2. KYC - Know Your Customer")
    if caso.eh_pj():
        out += _subtitulo(ctx, "Informações da Empresa")
        out += _pilulas(ctx, [
            ("Nome da empresa", caso.nome_empresa), ("Data de abertura", caso.data_abertura),
            ("Ramo de atividade", caso.ramo_atividade), ("Porte", caso.porte),
            ("Faturamento presumido", caso.faturamento_presumido), ("Endereço", caso.endereco),
            ("Presença online", caso.presenca_online or "Não"),
            ("Fachada da empresa", caso.fachada_empresa or "Não"),
        ])
    else:
        out += _subtitulo(ctx, "Informações Básicas do Cliente")
        out += _pilulas(ctx, [("Nome do cliente", caso.nome_cliente), ("Idade", caso.idade),
                              ("Cidade/Estado", caso.cidade_estado)])
        out += _subtitulo(ctx, "Cadastro e Registros")
        out += _pilulas(ctx, [
            ("Última atualização cadastral", caso.ultima_atualizacao_cadastral),
            ("Registro profissional", caso.registro_profissional),
            ("Renda presumida do cliente", caso.renda_presumida),
            ("Profissão informada pelo cliente", caso.profissao_informada),
        ])
        if caso.registro_societario == "Sim":
            out += _subtitulo(ctx, "Registro Societário")
            out += _pilulas(ctx, [
                ("Razão social", caso.reg_soc_razao_social), ("Data de abertura", caso.reg_soc_data_abertura),
                ("Situação cadastral", caso.reg_soc_situacao_cadastral),
                ("Ramo de atividade", caso.reg_soc_ramo_atividade),
            ])
    if caso.tipo_caso == core.TIPO_UNDER18 and (caso.rep_nome or caso.rep_renda_presumida):
        out += _subtitulo(ctx, "Responsável Legal")
        out += _pilulas(ctx, [
            ("Nome do responsável legal", caso.rep_nome),
            ("Renda presumida", caso.rep_renda_presumida),
            ("Registro profissional", caso.rep_reg_prof), ("Registro societário", caso.rep_reg_soc),
            ("Histórico de PLD", caso.rep_hist_pld), ("Histórico de fraude", caso.rep_hist_fraude),
        ])
    flags = _flags_kyc(caso)
    if flags:
        out += _subtitulo(ctx, "Região de Risco, PEP e Históricos")
        out += _pilulas(ctx, flags)
    if caso.eh_pj() and caso.socios:
        out += _subtitulo(ctx, "Informações Sobre o Sócio")
        for s in caso.socios:
            itens = [("Nome", s.nome), ("Idade", s.idade), ("Endereço", s.endereco),
                     ("Renda presumida", s.renda_presumida), ("Patrimônio", s.patrimonio)]
            if s.regiao_risco == "Sim":
                itens.append(("Região de risco", _com_detalhe("Sim", s.tipo_regiao_risco)))
            if s.pep == "Sim":
                itens.append(("PEP", _com_detalhe("Sim", s.tipo_pep, s.descricao_pep)))
            if s.historico_pld == "Sim":
                itens.append(("Histórico de PLD", _com_detalhe("Sim", s.historico_pld_detalhe)))
            if s.historico_fraude == "Sim":
                itens.append(("Histórico de fraude", _com_detalhe("Sim", s.historico_fraude_detalhe)))
            if s.midia_negativa == "Sim":
                itens.append(("Mídia negativa", _com_detalhe("Sim", s.midia_negativa_detalhe)))
            out += _pilulas(ctx, itens)
    out += _subtitulo(ctx, "Outras Informações Relevantes")
    out.append(_texto(ctx, caso.outras_info))
    return out


def _contraparte(ctx: _Ctx, c) -> List[Any]:
    itens: List[Tuple[str, str]] = [("Porcentagem", c.porcentagem), ("Valor", c.valor),
                                    ("Número de transações", c.num_transacoes), ("Nome", c.nome)]
    if c.tipo == "Pessoa Jurídica":
        itens += [("Data de abertura", c.data_abertura), ("Cidade/Estado", c.cidade_estado),
                  ("Ramo de atividade", c.ramo_atividade or c.registro_profissional),
                  ("Porte", c.porte), ("Faturamento presumido", c.faturamento_presumido or c.renda_presumida)]
    else:
        itens += [("Idade", c.idade), ("Cidade/Estado", c.cidade_estado),
                  ("Renda presumida", c.renda_presumida),
                  ("Registro profissional", c.registro_profissional)]
    itens = [(r, v) for r, v in itens if (v or "").strip() or r in ("Nome", "Valor")]
    if c.registro_societario == "Sim":
        itens.append(("Registro societário", _com_detalhe("Sim", c.registro_societario_detalhe)))
    if c.regiao_risco == "Sim":
        itens.append(("Região de risco", _com_detalhe("Sim", c.regiao_risco_detalhe)))
    if c.pep == "Sim":
        itens.append(("PEP", _com_detalhe("Sim", c.pep_detalhe)))
    if c.historico_pld == "Sim":
        itens.append(("Histórico de PLD", _com_detalhe("Sim", c.historico_pld_detalhe)))
    if c.historico_fraude == "Sim":
        itens.append(("Histórico de fraude", _com_detalhe("Sim", c.historico_fraude_detalhe)))
    if c.midia_negativa == "Sim":
        itens.append(("Mídia negativa", _com_detalhe("Sim", c.midia_negativa_detalhe)))
    bloco = _subtitulo(ctx, c.tipo or "Pessoa Física") + _pilulas(ctx, itens)
    return [KeepTogether(bloco), _linha(LINE, (3, 3), 0.6, 2, 3)]


def _fmt_pct(p: float) -> str:
    return f"{p:.0f}" if abs(p - round(p)) < 1e-9 else f"{p:.1f}".replace(".", ",")


def _secao_movimentacoes(ctx: _Ctx, caso) -> List[Any]:
    out = _titulo_secao(ctx, "3. Resumo de Movimentações")
    out += _pilulas(ctx, [("Período", caso.mov_periodo), ("Total de créditos", caso.mov_total_credito),
                          ("Total de contrapartes (crédito)", caso.mov_total_contrapartes_credito)])
    out += _subtitulo(ctx, "Contrapartes Principais de Crédito")
    if not caso.contrapartes_credito:
        out.append(_texto(ctx, "", "Nenhuma contraparte principal informada.", "texto_peq"))
    for c in caso.contrapartes_credito:
        out += _contraparte(ctx, c)
    resto = core.percentual_restante(caso.contrapartes_credito)
    if resto is not None and caso.contrapartes_credito:
        out.append(Paragraph(f"{_fmt_pct(resto)}% restante é referente às demais contrapartes de crédito",
                             ctx.st["texto"]))
        out.append(Spacer(1, 4))
    out += _pilulas(ctx, [("Total de débitos", caso.mov_total_debito),
                          ("Total de contrapartes (débito)", caso.mov_total_contrapartes_debito)])
    out += _subtitulo(ctx, "Contrapartes Principais de Débito")
    if not caso.contrapartes_debito:
        out.append(_texto(ctx, "", "Nenhuma contraparte principal informada.", "texto_peq"))
    for c in caso.contrapartes_debito:
        out += _contraparte(ctx, c)
    resto = core.percentual_restante(caso.contrapartes_debito)
    if resto is not None and caso.contrapartes_debito:
        out.append(Paragraph(f"{_fmt_pct(resto)}% restante é referente às demais contrapartes de débito",
                             ctx.st["texto"]))
    out += _subtitulo(ctx, "Outras Movimentações")
    if not caso.outras_movimentacoes:
        out.append(_texto(ctx, "", "Nenhuma outra movimentação informada.", "texto_peq"))
    for i, m in enumerate(caso.outras_movimentacoes, 1):
        out.append(Paragraph(f"<b>{i}. {_t(m.tipo)}:</b><br/>{_t(m.info, '—')}", ctx.st["texto"]))
        out.append(Spacer(1, 3))
    return out


def _cartao_total(ctx: _Ctx, rotulo: str, valor: str, cor) -> Tuple[Table, float]:
    est = ParagraphStyle("cv", parent=ctx.st["cartao_val"], textColor=cor)
    w = max(4.2 * cm, stringWidth(valor or "—", SANS_B, 15) + 22)
    t = Table([[Paragraph(_t(rotulo.upper()), ctx.st["cartao_rot"])],
               [Paragraph(_t(valor, "—"), est)]], colWidths=[w])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPER_ALT), ("BOX", (0, 0), (-1, -1), 0.9, LINE),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (0, 0), 6),
        ("BOTTOMPADDING", (0, 1), (0, 1), 7),
    ]))
    return t, w


def _imagem_grafico(ctx: _Ctx, png: bytes) -> Optional[RLImage]:
    try:
        iw, ih = ImageReader(BytesIO(png)).getSize()
    except Exception:  # noqa: BLE001
        return None
    return RLImage(BytesIO(png), width=ctx.largura, height=ctx.largura * ih / iw)


def _secao_thundera(ctx: _Ctx, caso, grafico_png: Optional[bytes]) -> List[Any]:
    out = _titulo_secao(ctx, "4. Thundera - AML 360")
    out += _subtitulo(ctx, "Transações em Perfil de Arredondamento nas Unidades de Milhar")
    if caso.comp_arredondamento == "Sim" and caso.arredondamento_itens:
        itens: List[Tuple[str, str]] = []
        for i, a in enumerate(caso.arredondamento_itens, 1):
            lado = (a.cred_deb or "Créditos")
            itens += [(f"{lado} — Quantidade", a.quantidade), (f"{lado} — Valor {i}", a.valor)]
        out += _pilulas(ctx, itens)
    else:
        out += _pilulas(ctx, [("Arredondamento", caso.comp_arredondamento or "Não")])
    if caso.comp_pix == "Sim" and caso.pix_itens:
        out += _subtitulo(ctx, "Mensagens Pix")
        itens = []
        for i, p in enumerate(caso.pix_itens, 1):
            lado = (p.cred_deb or "Créditos")
            itens += [(f"{lado} — Quantidade Pix", p.quantidade), (f"{lado} — Mensagem Pix {i}", p.mensagem)]
        out += _pilulas(ctx, itens)
    else:
        out += _subtitulo(ctx, "Mensagens Pix")
        out += _pilulas(ctx, [("Mensagens Pix", caso.comp_pix or "Não")])

    tl: List[Any] = _subtitulo(ctx, "Timeline de Transferências")
    png = grafico_png
    if png is None and caso.comp_evasao:
        try:
            png = core.grafico_do_caso(caso)
        except Exception:  # noqa: BLE001 - gráfico nunca deve derrubar o PDF
            png = None
    if png or caso.comp_evasao:
        c1, w1 = _cartao_total(ctx, "Créditos", caso.mov_total_credito, VERDE)
        c2, w2 = _cartao_total(ctx, "Débitos", caso.mov_total_debito, VERMELHO)
        t = Table([[c1, "", c2]], colWidths=[w1, 6, w2], hAlign="LEFT")
        t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        tl += [t, Spacer(1, 6)]
    if png:
        img = _imagem_grafico(ctx, png)
        if img:
            tl += [img, Spacer(1, 4)]
    out.append(KeepTogether(tl))  # título, totais e gráfico não se separam entre páginas
    if caso.comp_mudanca_comportamento.strip():
        # só os meses e valores movimentados: o dossiê não afirma se houve mudança de comportamento
        out += _subtitulo(ctx, "Valores Movimentados por Mês")
        for linha in caso.comp_mudanca_comportamento.splitlines():
            if linha.strip():
                out.append(Paragraph(_t(linha), ctx.st["texto"]))
    out.append(Spacer(1, 4))
    out += _pilulas(ctx, [("Data de abertura da conta/data do último reporte",
                           caso.comp_data_abertura_ultimo_reporte)])
    return out


def _aba_informacoes(ctx: _Ctx, caso, grafico_png: Optional[bytes]) -> List[Any]:
    out: List[Any] = [_faixa_aba(ctx, "Informações do Caso")]
    out += _secao_alerta(ctx, caso)
    out += _secao_kyc(ctx, caso)
    out += _secao_movimentacoes(ctx, caso)
    out += _secao_thundera(ctx, caso, grafico_png)
    return out


# ---------------------------------------------------------------------------
# Aba 2 - Resolução do Caso
# ---------------------------------------------------------------------------
def _selo(ctx: _Ctx, caso) -> Table:
    texto = (caso.diligencia or "").strip() or "Diligência pendente"
    cor = _cor_selo(core.estilo_diligencia(caso.diligencia))
    est = ParagraphStyle("selo_c", parent=ctx.st["selo"], textColor=cor)
    interno = Table([[Paragraph(_t(texto.upper()), est)]], colWidths=[7.4 * cm])
    interno.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.4, cor), ("ROUNDEDCORNERS", [5, 5, 5, 5]),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    externo = Table([[interno]], colWidths=[7.8 * cm], hAlign="CENTER")
    externo.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.4, cor), ("ROUNDEDCORNERS", [7, 7, 7, 7]),
        ("BACKGROUND", (0, 0), (-1, -1), PAPER_ALT),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return externo


def _status(ctx: _Ctx, caso, chave: str) -> Paragraph:
    quando = (caso.resolucao_salva_em or {}).get(chave)
    if quando:
        return Paragraph(f"{_sym('✓', 'OK', _hex(VERDE))} PREENCHIDO E SALVO EM {_t(_fmt_ts(quando))}",
                         ctx.st["status_ok"])
    return Paragraph("PENDENTE — PREENCHER NA CALIBRAÇÃO DO TIME", ctx.st["status_pend"])


def _card_resolucao(ctx: _Ctx, caso, titulo: str, chave: str, conteudo: List[Any]) -> List[Any]:
    cabeca = [Paragraph(_t(titulo), ctx.st["secao"]), _linha(LINE, None, 1.0, 0, 3), _status(ctx, caso, chave),
              Spacer(1, 4)]
    primeiro = conteudo[:1]
    return [KeepTogether(cabeca + primeiro)] + conteudo[1:] + [Spacer(1, 4)]


def _lista_marcada(ctx: _Ctx, selecionadas: List[str], vazio: str = "Nenhuma selecionada") -> List[Any]:
    if not selecionadas:
        return [_texto(ctx, "", vazio, "texto_peq")]
    marca = _sym("✓", "[x]", _hex(VERDE))
    return [Paragraph(f"{marca} {_t(s)}", ParagraphStyle("li", parent=ctx.st["texto"], leftIndent=14,
                                                         firstLineIndent=-14))
            for s in selecionadas]


def _aba_resolucao(ctx: _Ctx, caso) -> List[Any]:
    out: List[Any] = [_faixa_aba(ctx, "Resolução do Caso"), Spacer(1, 8), _selo(ctx, caso), Spacer(1, 4)]
    out += _card_resolucao(ctx, caso, "Parecer Final do Analista", "parecer",
                           [_texto(ctx, caso.parecer_final)])
    out += _card_resolucao(ctx, caso, "Alíneas", "alineas", [_texto(ctx, caso.alineas)])

    sel = list(caso.jurisprudencias_selecionadas or [])
    grupos = [("Opções de Jurisprudência para NuPagamentos", JURISPRUDENCIA_NUPAGAMENTOS),
              ("Jurisprudências para Reportar (NuInvest)", JURISPRUDENCIA_REPORTAR_NUINVEST),
              ("Jurisprudências para Reportar e Cancelar (NuInvest)", JURISPRUDENCIA_REPORTAR_CANCELAR_NUINVEST)]
    conhecidas = {j for _, lst in grupos for j in lst}
    corpo: List[Any] = []
    for nome, lista in grupos:
        marcadas = [j for j in lista if j in sel]
        corpo.append(Paragraph(f"<b>{_t(nome)}</b> "
                               f"<font color=\"{_hex(ACCENT)}\">({len(marcadas)} de {len(lista)})</font>",
                               ParagraphStyle("gj", parent=ctx.st["texto"], spaceBefore=4, spaceAfter=2)))
        corpo += _lista_marcada(ctx, marcadas)
    outras = [j for j in sel if j not in conhecidas]
    if outras:
        corpo.append(Paragraph("<b>Outras</b>", ParagraphStyle("gj2", parent=ctx.st["texto"], spaceBefore=4)))
        corpo += _lista_marcada(ctx, outras)
    out += _card_resolucao(ctx, caso, "Jurisprudências", "jurisprudencias", corpo)
    out += _card_resolucao(ctx, caso, "Razões de Clear", "razoes_clear",
                           _lista_marcada(ctx, list(caso.razoes_clear_selecionadas or [])))
    out += _card_resolucao(ctx, caso, "Razões de Cancelamento", "razoes_cancelamento",
                           _lista_marcada(ctx, list(caso.razoes_cancelamento_selecionadas or [])))
    out += _card_resolucao(ctx, caso, "Diligência", "diligencia",
                           [Paragraph(f"<b>{_t(caso.diligencia, 'Pendente')}</b>", ctx.st["texto"])])
    if caso.resolucao_bloqueada_em:
        out.append(Paragraph(f"Informações do caso salvas e bloqueadas em "
                             f"{_t(_fmt_ts(caso.resolucao_bloqueada_em))}.", ctx.st["salvo"]))
    return out


# ---------------------------------------------------------------------------
# Aba 3 - Avaliação de Qualidade
# ---------------------------------------------------------------------------
def _aba_avaliacao(ctx: _Ctx, caso) -> List[Any]:
    nota = caso.nota_qualidade()
    cor = _cor_nota(nota)
    out: List[Any] = [_faixa_aba(ctx, "Avaliação de Qualidade"), Spacer(1, 6)]
    out += _titulo_secao(ctx, f"Avaliação de Qualidade — {caso.rubrica()}")
    est = ParagraphStyle("nota_c", parent=ctx.st["nota"], textColor=cor)
    bloco_nota = Table([[Paragraph("NOTA FINAL", ctx.st["nota_rot"])],
                        [Paragraph(_t(core.formatar_nota(nota)), est)]], colWidths=[5 * cm], hAlign="LEFT")
    bloco_nota.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.4, cor), ("ROUNDEDCORNERS", [8, 8, 8, 8]),
        ("BACKGROUND", (0, 0), (-1, -1), PAPER_ALT),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (0, 0), 7),
        ("BOTTOMPADDING", (0, 1), (0, 1), 8),
    ]))
    out += [bloco_nota, Spacer(1, 4),
            Paragraph("O desconto é por categoria, não por critério: a nota parte de 100% e perde o peso de "
                      "cada categoria com ao menos um critério marcado, uma única vez. Regulatory Critical "
                      "(100%) zera a nota; Business Intelligence (0%) registra sem descontar.",
                      ctx.st["texto_peq"]), Spacer(1, 4)]

    for cat in core.resumo_scorecard(caso):
        peso = cat["peso"] * 100
        peso_txt = f"{peso:.0f}" if abs(peso - round(peso)) < 1e-9 else f"{peso:.1f}".replace(".", ",")
        bloco = _subtitulo(ctx, f"Categoria: {cat['categoria']} — Peso {peso_txt}%")
        bloco.append(Paragraph(f"{len(cat['marcados'])} de {cat['total']} critérios marcados",
                               ctx.st["texto_peq"]))
        itens: List[List[Any]] = []
        if not cat["marcados"]:
            itens.append([_texto(ctx, "", "Nenhum critério marcado", "texto_peq")])
        for d in cat["marcados"]:
            marca = _sym("✓", "[x]", _hex(VERMELHO))
            itens.append([
                Paragraph(f"{marca} {_t(d['nome'])}", ctx.st["crit"]),
                Paragraph(_t(d.get("aplicabilidade", "")), ctx.st["aplic"]),
                Spacer(1, 3),
            ])
        # título da categoria + primeiro critério ficam juntos; os demais fluem livres
        out.append(KeepTogether(bloco + (itens[0] if itens else [])))
        for item in itens[1:]:
            out.append(KeepTogether(item))
    out += _subtitulo(ctx, "Feedback de Qualidade")
    out.append(_texto(ctx, caso.scorecard_feedback))
    out.append(Spacer(1, 4))
    if caso.scorecard_salvo_em:
        out.append(Paragraph(f"Salvo em {_t(_fmt_ts(caso.scorecard_salvo_em))}.", ctx.st["salvo"]))
    else:
        out.append(Paragraph("Avaliação ainda não salva.", ctx.st["salvo"]))
    return out


# ---------------------------------------------------------------------------
# Montagem
# ---------------------------------------------------------------------------
def gerar_pdf(caso, escopo: str = "completo", grafico_png: Optional[bytes] = None) -> bytes:
    """Gera o PDF do dossiê. `escopo`: completo | resolucao | avaliacao | informacoes."""
    if escopo not in ESCOPOS:
        raise ValueError(f"escopo inválido: {escopo!r} (use um de {ESCOPOS})")
    _registrar_fontes()
    ctx = _Ctx()

    story: List[Any] = _cabecalho(ctx, caso)
    if escopo in ("completo", "resolucao", "informacoes"):
        story += _aba_informacoes(ctx, caso, grafico_png)
    if escopo in ("completo", "resolucao"):
        story.append(PageBreak())
        story += _aba_resolucao(ctx, caso)
    if escopo in ("completo", "avaliacao"):
        if escopo == "completo":
            story.append(PageBreak())
        story += _aba_avaliacao(ctx, caso)

    gerado = _fmt_ts(caso.criado_em) or datetime.now().strftime("%d/%m/%Y, %H:%M:%S")
    rodape = f"Sentinela PLD · Dossiê gerado em {gerado} · Uso interno e confidencial"
    topo = f"{caso.numero_caso} · {caso.nome_display() or 'Sem nome'}"

    def _pagina(canvas, doc):
        canvas.saveState()
        larg, alt = A4
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.7)
        canvas.line(1.7 * cm, 1.35 * cm, larg - 1.7 * cm, 1.35 * cm)
        canvas.setFont(MONO, 7)
        canvas.setFillColor(ACCENT)
        canvas.drawString(1.7 * cm, 0.9 * cm, rodape)
        canvas.drawRightString(larg - 1.7 * cm, 0.9 * cm, f"Página {doc.page}")
        if doc.page > 1:
            canvas.setFont(MONO_B, 6.8)
            canvas.drawString(1.7 * cm, alt - 1.05 * cm, topo[:110].encode("latin-1", "replace").decode("latin-1"))
        canvas.restoreState()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=1.7 * cm, bottomMargin=1.8 * cm,
        leftMargin=1.7 * cm, rightMargin=1.7 * cm,
        title=f"Dossiê {caso.numero_caso}", author="Sentinela PLD",
    )
    doc.build(story, onFirstPage=_pagina, onLaterPages=_pagina)
    return buf.getvalue()


def gerar_pdf_dossie(caso, grafico_png: Optional[bytes] = None) -> bytes:
    """Compatibilidade com a versão anterior: PDF completo (as três abas)."""
    return gerar_pdf(caso, "completo", grafico_png=grafico_png)
