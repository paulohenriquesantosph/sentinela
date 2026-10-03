# -*- coding: utf-8 -*-
"""
Sentinela PLD — versão Databricks (Streamlit)
================================================
Fluxo das telas, com o design do artefato original (ver estilo.py).

Camadas:
  - core.py        : modelo, nota de qualidade, risco, gráfico e Banco de Dossiês
  - ia.py          : preenchimento automático por IA
  - pdf_dossie.py  : PDF do dossiê (Informações + Resolução + Avaliação)
  - dossie_html.py : aba "Informações do Caso" em HTML
  - opcoes.py      : listas de razões/jurisprudências e rubricas de qualidade
  - estilo.py      : todo o visual (CSS, arte de fundo, cartões)
  - app.py         : este arquivo, apenas o fluxo das telas

Ver README.md para publicar no Databricks.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import streamlit as st

import dossie_html
import estilo
import ia
import pdf_dossie
from core import (
    Caso, Socio, ContraparteMovimentacao, OutraMovimentacao, ItemArredondamento, MensagemPix,
    ArmazenamentoLocal, gerar_numero_caso, aplicar_timeline_ao_caso, gerar_series_timeline,
    renderizar_timeline_png, calcular_nota_scorecard, listar_drivers_scorecard, faixa_nota,
    formatar_nota, estilo_diligencia, inferir_genero, validar_caso, parse_valor_br,
    agora_iso, formatar_data_br, formatar_brl,
    TIPOS_CASO, TIPO_PJ, TIPO_UNDER18, TIPOS_REGIAO_RISCO_1, TIPOS_PEP, TIPOS_CONTRAPARTE,
    TIPOS_OUTRAS_MOV, OPCOES_EVASAO, SECOES_RESOLUCAO,
)
from opcoes import (
    DILIGENCIAS, RAZOES_CLEAR, RAZOES_CANCELAMENTO, JURISPRUDENCIA_NUPAGAMENTOS,
    JURISPRUDENCIA_REPORTAR_NUINVEST, JURISPRUDENCIA_REPORTAR_CANCELAR_NUINVEST,
)

st.set_page_config(page_title="Sentinela PLD", page_icon="\U0001F6E1️", layout="wide",
                   initial_sidebar_state="collapsed")


@st.cache_resource
def _store() -> ArmazenamentoLocal:
    return ArmazenamentoLocal()


store = _store()
ss = st.session_state

SIM_NAO = ["Não", "Sim"]
GENEROS = {"": "", "Masculino": "M", "Feminino": "F"}

DEFAULTS: Dict[str, Any] = {
    "tela": "home",
    "tipo_caso_novo": None,
    "caso_selecionado": None,
    "dossie_voltar": "banco",
    "gerado_numero": None,
    "banco_modo": "",
    "banco_termo": "",
    "ia_avisos": [],
    "ia_erro": "",
    "erros_form": [],
    "timeline": None,
    "snapshot": None,
    "_uid": 0,
}
for _k, _v in DEFAULTS.items():
    if _k not in ss:
        ss[_k] = _v

# ---------------------------------------------------------------------------
# Navegação e estado do formulário
# ---------------------------------------------------------------------------
_PREFIXOS_FORM = ("f_", "L_", "r_")


def ir_para(tela: str) -> None:
    ss.tela = tela


def _chaves_form() -> List[str]:
    return [k for k in list(ss.keys()) if isinstance(k, str) and k.startswith(_PREFIXOS_FORM)]


def limpar_formulario() -> None:
    for k in _chaves_form():
        del ss[k]
    ss.timeline = None
    ss.snapshot = None
    ss.gerado_numero = None
    ss.ia_avisos = []
    ss.erros_form = []


def guardar_formulario() -> None:
    """Foto do formulário antes de sair para o dossiê (as chaves dos widgets somem
    quando o widget deixa de ser desenhado). 'Voltar ao Sentinela' restaura."""
    ss.snapshot = {k: ss[k] for k in _chaves_form() if k in ss}


def restaurar_formulario() -> None:
    if ss.snapshot:
        for k, v in ss.snapshot.items():
            ss[k] = v
        ss.snapshot = None


def ver_dossie(numero: str, voltar_para: str) -> None:
    if voltar_para == "formulario":
        guardar_formulario()
    ss.caso_selecionado = numero
    ss.dossie_voltar = voltar_para
    ir_para("dossie")


def voltar_do_dossie() -> None:
    destino = ss.dossie_voltar or "banco"
    if destino == "formulario":
        restaurar_formulario()
    ir_para(destino)


def _novo_id() -> int:
    ss._uid += 1
    return ss._uid


def _lista(nome: str) -> List[int]:
    return ss.setdefault(f"L_{nome}", [])


def _kr(nome: str, rid: int, campo: str) -> str:
    return f"r_{nome}_{rid}_{campo}"


LINHA_PADRAO: Dict[str, Dict[str, str]] = {
    "cred": {"tipo": "Pessoa Física", "pct": "", "valor": "", "ntrans": "", "nome": "", "idade": "",
             "cidade": "", "renda": "", "regprof": "", "dataab": "", "ramo": "", "porte": "", "fat": "",
             "regsoc": "Não", "regsoc_d": "", "regiao": "Não", "regiao_d": "", "pep": "Não", "pep_d": "",
             "hpld": "Não", "hpld_d": "", "hfraude": "Não", "hfraude_d": "", "midia": "Não", "midia_d": ""},
    "om": {"tipo": "Saques", "info": ""},
    "ar": {"cd": "Créditos", "qtd": "", "valor": ""},
    "px": {"cd": "Créditos", "qtd": "", "msg": ""},
    "so": {"nome": "", "idade": "", "endereco": "", "renda": "", "patrimonio": "", "regiao": "Não",
           "tipo_regiao": TIPOS_REGIAO_RISCO_1[0], "pep": "Não", "tipo_pep": TIPOS_PEP[0], "desc_pep": "",
           "hpld": "Não", "hpld_d": "", "hfraude": "Não", "hfraude_d": "", "midia": "Não", "midia_d": ""},
}
LINHA_PADRAO["deb"] = LINHA_PADRAO["cred"]


def _padrao_lista(nome: str) -> Dict[str, str]:
    return LINHA_PADRAO[nome]


def add_linha(nome: str, valores: Optional[Dict[str, str]] = None) -> int:
    rid = _novo_id()
    _lista(nome).append(rid)
    for campo, padrao in _padrao_lista(nome).items():
        ss[_kr(nome, rid, campo)] = (valores or {}).get(campo, padrao)
    return rid


def rem_ultima(nome: str) -> None:
    ids = _lista(nome)
    if ids:
        rid = ids.pop()
        for k in [k for k in list(ss.keys()) if isinstance(k, str) and k.startswith(f"r_{nome}_{rid}_")]:
            del ss[k]


# (chave do formulário, atributo do Caso) — usados para carregar e ler o formulário
CAMPOS: List[tuple] = [
    ("f_fator", "fator_gerador"), ("f_data_alerta", "data_alerta"), ("f_sentenca", "sentenca"),
    ("f_nome", "nome_cliente"), ("f_idade", "idade"), ("f_cidade", "cidade_estado"),
    ("f_ult_atualizacao", "ultima_atualizacao_cadastral"), ("f_profissao", "profissao_informada"),
    ("f_renda", "renda_presumida"), ("f_regprof", "registro_profissional"),
    ("f_regsoc", "registro_societario"), ("f_rs_razao", "reg_soc_razao_social"),
    ("f_rs_data", "reg_soc_data_abertura"), ("f_rs_situacao", "reg_soc_situacao_cadastral"),
    ("f_rs_ramo", "reg_soc_ramo_atividade"),
    ("f_regiao", "regiao_risco"), ("f_tipo_regiao", "tipo_regiao_risco"), ("f_tipo_regiao2", "tipo_regiao_risco_2"),
    ("f_pep", "pep"), ("f_tipo_pep", "tipo_pep"), ("f_desc_pep", "descricao_pep"),
    ("f_midia", "midia_negativa"), ("f_midia_d", "midia_negativa_detalhe"),
    ("f_hpld", "historico_pld"), ("f_hpld_d", "historico_pld_detalhe"),
    ("f_hfraude", "historico_fraude"), ("f_hfraude_d", "historico_fraude_detalhe"),
    ("f_outras_info", "outras_info"),
    ("f_empresa", "nome_empresa"), ("f_emp_data", "data_abertura"), ("f_emp_ramo", "ramo_atividade"),
    ("f_emp_porte", "porte"), ("f_emp_fat", "faturamento_presumido"), ("f_emp_end", "endereco"),
    ("f_pres_online", "presenca_online"), ("f_pres_online_d", "presenca_online_detalhe"),
    ("f_fachada", "fachada_empresa"), ("f_fachada_d", "fachada_empresa_detalhe"),
    ("f_rep_nome", "rep_nome"), ("f_rep_renda", "rep_renda_presumida"), ("f_rep_regprof", "rep_reg_prof"),
    ("f_rep_regsoc", "rep_reg_soc"), ("f_rep_hpld", "rep_hist_pld"), ("f_rep_hfraude", "rep_hist_fraude"),
    ("f_periodo", "mov_periodo"), ("f_tot_cred", "mov_total_credito"),
    ("f_tot_cp_cred", "mov_total_contrapartes_credito"), ("f_tot_deb", "mov_total_debito"),
    ("f_tot_cp_deb", "mov_total_contrapartes_debito"),
    ("f_arred", "comp_arredondamento"), ("f_pix", "comp_pix"), ("f_evasao", "comp_evasao"),
    ("f_mudanca", "comp_mudanca_comportamento"), ("f_data_conta", "comp_data_abertura_ultimo_reporte"),
]

CP_CAMPOS = [("tipo", "tipo"), ("pct", "porcentagem"), ("valor", "valor"), ("ntrans", "num_transacoes"),
             ("nome", "nome"), ("idade", "idade"), ("cidade", "cidade_estado"), ("renda", "renda_presumida"),
             ("regprof", "registro_profissional"), ("dataab", "data_abertura"), ("ramo", "ramo_atividade"),
             ("porte", "porte"), ("fat", "faturamento_presumido"),
             ("regsoc", "registro_societario"), ("regsoc_d", "registro_societario_detalhe"),
             ("regiao", "regiao_risco"), ("regiao_d", "regiao_risco_detalhe"), ("pep", "pep"), ("pep_d", "pep_detalhe"),
             ("hpld", "historico_pld"), ("hpld_d", "historico_pld_detalhe"),
             ("hfraude", "historico_fraude"), ("hfraude_d", "historico_fraude_detalhe"),
             ("midia", "midia_negativa"), ("midia_d", "midia_negativa_detalhe")]
SOCIO_CAMPOS = [("nome", "nome"), ("idade", "idade"), ("endereco", "endereco"), ("renda", "renda_presumida"),
                ("patrimonio", "patrimonio"), ("regiao", "regiao_risco"), ("tipo_regiao", "tipo_regiao_risco"),
                ("pep", "pep"), ("tipo_pep", "tipo_pep"), ("desc_pep", "descricao_pep"),
                ("hpld", "historico_pld"), ("hpld_d", "historico_pld_detalhe"),
                ("hfraude", "historico_fraude"), ("hfraude_d", "historico_fraude_detalhe"),
                ("midia", "midia_negativa"), ("midia_d", "midia_negativa_detalhe")]


def carregar_caso_no_formulario(caso: Caso) -> None:
    """Joga um Caso (por exemplo, o devolvido pela IA) nos campos do formulário."""
    limpar_formulario()
    for chave, attr in CAMPOS:
        ss[chave] = getattr(caso, attr) or ""
    for chave, padrao in (("f_regsoc", "Não"), ("f_regiao", "Não"), ("f_pep", "Não"), ("f_midia", "Não"),
                          ("f_hpld", "Não"), ("f_hfraude", "Não"), ("f_pres_online", "Não"),
                          ("f_fachada", "Não"), ("f_arred", "Não"), ("f_pix", "Não")):
        ss[chave] = ss.get(chave) or padrao
    ss["f_genero"] = next((k for k, v in GENEROS.items() if v == caso.genero), "")
    for cp_nome, lista in (("cred", caso.contrapartes_credito), ("deb", caso.contrapartes_debito)):
        for cp in lista:
            add_linha(cp_nome, {c: (getattr(cp, a) or _padrao_lista(cp_nome)[c]) for c, a in CP_CAMPOS})
    for om in caso.outras_movimentacoes:
        add_linha("om", {"tipo": om.tipo if om.tipo in TIPOS_OUTRAS_MOV else "Outros", "info": om.info})
    for a in caso.arredondamento_itens:
        add_linha("ar", {"cd": a.cred_deb if a.cred_deb in ("Créditos", "Débitos") else "Créditos",
                         "qtd": a.quantidade, "valor": a.valor})
    for p in caso.pix_itens:
        add_linha("px", {"cd": p.cred_deb if p.cred_deb in ("Créditos", "Débitos") else "Créditos",
                         "qtd": p.quantidade, "msg": p.mensagem})
    for s in caso.socios:
        add_linha("so", {c: (getattr(s, a) or _padrao_lista("so")[c]) for c, a in SOCIO_CAMPOS})


def _txt(chave: str, padrao: str = "") -> str:
    v = ss.get(chave, padrao)
    return (v if isinstance(v, str) else padrao).strip()


def montar_caso_do_formulario(tipo_caso: str) -> Caso:
    """Lê todos os campos do formulário e devolve o Caso (sem número definitivo)."""
    caso = Caso(numero_caso="tmp", tipo_caso=tipo_caso)
    for chave, attr in CAMPOS:
        valor = ss.get(chave, getattr(caso, attr))
        setattr(caso, attr, valor.strip() if isinstance(valor, str) else valor)
    caso.genero = GENEROS.get(ss.get("f_genero", ""), "") or (inferir_genero(caso.nome_cliente) or "")
    if caso.tipo_regiao_risco != TIPOS_REGIAO_RISCO_1[2]:
        caso.tipo_regiao_risco_2 = ""

    def _cp(nome):
        out = []
        for rid in _lista(nome):
            v = {c: _txt(_kr(nome, rid, c), _padrao_lista(nome)[c]) for c, _ in CP_CAMPOS}
            out.append(ContraparteMovimentacao(**{a: v[c] for c, a in CP_CAMPOS}))
        return out

    caso.contrapartes_credito = _cp("cred")
    caso.contrapartes_debito = _cp("deb")
    caso.outras_movimentacoes = [
        OutraMovimentacao(tipo=_txt(_kr("om", r, "tipo"), "Outros"), info=_txt(_kr("om", r, "info")))
        for r in _lista("om") if _txt(_kr("om", r, "info"))]
    if caso.comp_arredondamento == "Sim":
        caso.arredondamento_itens = [
            ItemArredondamento(cred_deb=_txt(_kr("ar", r, "cd"), "Créditos"), quantidade=_txt(_kr("ar", r, "qtd")),
                               valor=_txt(_kr("ar", r, "valor"))) for r in _lista("ar")]
    if caso.comp_pix == "Sim":
        caso.pix_itens = [
            MensagemPix(cred_deb=_txt(_kr("px", r, "cd"), "Créditos"), quantidade=_txt(_kr("px", r, "qtd")),
                        mensagem=_txt(_kr("px", r, "msg"))) for r in _lista("px")]
    if caso.eh_pj():
        caso.socios = []
        for rid in _lista("so"):
            v = {c: _txt(_kr("so", rid, c), _padrao_lista("so")[c]) for c, _ in SOCIO_CAMPOS}
            caso.socios.append(Socio(**{a: v[c] for c, a in SOCIO_CAMPOS}))
    return caso


# ---------------------------------------------------------------------------
# Widgets com estado por chave
# ---------------------------------------------------------------------------

def _init(chave: str, padrao: Any) -> None:
    if chave not in ss:
        ss[chave] = padrao


def campo(rotulo: str, chave: str, padrao: str = "", obrig: bool = False, ph: Optional[str] = None,
          area: bool = False, altura: Optional[int] = None, container=None, mono: bool = False,
          oculto_rotulo: bool = False, desabilitado: bool = False, on_change=None):
    alvo = container or st
    _init(chave, padrao)
    r = estilo.req(rotulo) if obrig else rotulo
    kw = dict(key=chave, placeholder=ph, label_visibility="collapsed" if oculto_rotulo else "visible",
              disabled=desabilitado, on_change=on_change)
    if area:
        return alvo.text_area(r, height=altura or 90, **kw)
    return alvo.text_input(r, **kw)


def escolha(rotulo: str, chave: str, opcoes: List[str], padrao: Optional[str] = None, obrig: bool = False,
            container=None, desabilitado: bool = False):
    alvo = container or st
    padrao = opcoes[0] if padrao is None else padrao
    if ss.get(chave) not in opcoes:
        ss[chave] = padrao
    r = estilo.req(rotulo) if obrig else rotulo
    return alvo.selectbox(r, opcoes, key=chave, disabled=desabilitado,
                          format_func=lambda x: x if x else "—")


def selecao_estreita(rotulo: str, chave: str, opcoes: List[str], obrig: bool = True, padrao: Optional[str] = None):
    """Select pequeno (uma coluna estreita), como nas capturas."""
    c, _ = st.columns([1, 4])
    return escolha(rotulo, chave, opcoes, padrao, obrig, container=c)


def botao_link(rotulo: str, **kw):
    with estilo.variante("lnk"):
        return st.button(rotulo, **kw)


# ---------------------------------------------------------------------------
# HOME
# ---------------------------------------------------------------------------
def tela_home() -> None:
    estilo.titulo_cartao(
        eyebrow="Gerador de Casos - Calibração", titulo="SENTINELA",
        subtitulo_forte="Confecção de casos individuais para análise",
        descricao=("Organiza o questionário do caso (alerta, KYC, movimentação, comportamentos AML 360, "
                   "parecer e diligência) em um dossiê individual e padronizado, pronto para análise e arquivo."),
        carimbo="Uso interno · Confidencial")
    st.button("Iniciar novo caso", type="primary", key="home_novo",
              on_click=lambda: (limpar_formulario(), setattr(ss, "caso_selecionado", None), ir_para("escolher_tipo")))
    st.button("Banco de dossiês", type="secondary", key="home_banco",
              on_click=lambda: (setattr(ss, "caso_selecionado", None), setattr(ss, "banco_modo", ""),
                                setattr(ss, "dossie_voltar", "banco"), ir_para("banco")))


# ---------------------------------------------------------------------------
# ESCOLHA DO TIPO DE CASO
# ---------------------------------------------------------------------------
def _escolher_tipo(tipo: str) -> None:
    ss.tipo_caso_novo = tipo
    limpar_formulario()
    ir_para("modo_preenchimento")


def tela_escolher_tipo() -> None:
    estilo.titulo_cartao("Etapa 1 de 2", "SENTINELA", pequeno=True, descricao_normal=(
        "Escolha o tipo de caso que será gerado para esta calibração."))
    with estilo.variante("opcoes"):
        for i, tipo in enumerate(TIPOS_CASO):
            st.button(tipo, key=f"tipo_{i}", type="secondary", on_click=_escolher_tipo, args=(tipo,))
    botao_link("← Voltar", key="tipo_voltar", on_click=ir_para, args=("home",))


# ---------------------------------------------------------------------------
# MODO DE PREENCHIMENTO
# ---------------------------------------------------------------------------
def tela_modo_preenchimento() -> None:
    estilo.titulo_cartao("Etapa 2 de 2", "SENTINELA", pequeno=True,
                         descricao_normal="Como você quer preencher este caso?")
    with estilo.variante("opcoes"):
        st.button("Preencher com instruções (automático)", key="modo_auto", type="primary",
                  on_click=ir_para, args=("preenchimento_ia",))
        st.button("Preencher manualmente", key="modo_manual", type="secondary",
                  on_click=ir_para, args=("formulario",))
    botao_link("← Voltar", key="modo_voltar", on_click=ir_para, args=("escolher_tipo",))


# ---------------------------------------------------------------------------
# PREENCHIMENTO AUTOMÁTICO VIA IA
# ---------------------------------------------------------------------------
def _preencher_com_ia() -> None:
    erros = []
    if not _txt("ia_fator"):
        erros.append("Nome do alerta")
    if not _txt("ia_data"):
        erros.append("Data do alerta")
    if not _txt("ia_sentenca"):
        erros.append("Sentença")
    if not _txt("ia_resumo"):
        erros.append("Resumo do caso")
    if erros:
        ss.ia_erro = "Preencha: " + ", ".join(erros) + "."
        return
    try:
        caso, avisos = ia.preencher_caso_via_ia(
            tipo_caso=ss.tipo_caso_novo or TIPOS_CASO[0],
            fator_gerador=_txt("ia_fator"), data_alerta=_txt("ia_data"), sentenca=_txt("ia_sentenca"),
            resumo=_txt("ia_resumo"), outras_movimentacoes=_txt("ia_outras"))
    except ia.ErroExtracaoIA as e:
        ss.ia_erro = str(e)
        return
    except Exception as e:  # noqa: BLE001 - erro inesperado não pode derrubar a tela
        ss.ia_erro = f"Erro inesperado ao preencher com IA: {e}"
        return
    ss.ia_erro = ""
    carregar_caso_no_formulario(caso)
    ss.ia_avisos = avisos
    ir_para("formulario")


def tela_preenchimento_ia() -> None:
    estilo.titulo_cartao("Preenchimento com instruções", "DESCREVA O CASO", pequeno=True)
    campo("Nome do alerta", "ia_fator", obrig=True)
    campo("Data do alerta", "ia_data", padrao=formatar_data_br(date.today()), obrig=True)
    campo("Sentença", "ia_sentenca", obrig=True, area=True, altura=80)
    estilo.dica("Cole ou digite um resumo com as informações do caso (cliente, movimentação, contrapartes, "
                "comportamento) para o Sentinela tentar preencher os campos automaticamente.")
    campo("Resumo do caso", "ia_resumo", area=True, altura=170, oculto_rotulo=True)
    estilo.dica("Outras Movimentações (opcional) — descreva aqui apenas movimentações que <b>não</b> sejam "
                "transferências bancárias comuns (ex: saques, boletos, gastos no cartão, empréstimos, "
                "criptomoedas, investimentos). Isso alimenta o campo \"Outras Movimentações\" do Resumo "
                "de Movimentações.")
    campo("Outras movimentações", "ia_outras", area=True, altura=110, oculto_rotulo=True)
    if ss.ia_erro:
        estilo.msg_erro(ss.ia_erro)
    with st.spinner("Chamando a IA para preencher o formulário…"):
        st.button("Preencher automaticamente", key="ia_preencher", type="primary", on_click=_preencher_com_ia)
    botao_link("← Voltar", key="ia_voltar", on_click=ir_para, args=("modo_preenchimento",))


# ---------------------------------------------------------------------------
# FORMULÁRIO
# ---------------------------------------------------------------------------
def _bloco_contraparte(nome: str, rid: int, n: int) -> None:
    def k(c):
        return _kr(nome, rid, c)

    with st.container(border=True):
        estilo.marcador("sx-sub")
        pj = ss.get(k("tipo")) == "Pessoa Jurídica"
        escolha("Tipo de contraparte", k("tipo"), TIPOS_CONTRAPARTE, obrig=True,
                container=st.columns([1, 2])[0])
        c1, c2, c3 = st.columns(3)
        campo("Porcentagem", k("pct"), obrig=True, ph="Ex: 14%", container=c1)
        campo("Valor", k("valor"), obrig=True, ph="Ex: R$70.000,00", container=c2)
        campo("Número de transações", k("ntrans"), obrig=True, container=c3)
        if pj:
            c1, c2, c3 = st.columns(3)
            campo("Nome", k("nome"), obrig=True, container=c1)
            campo("Data de abertura", k("dataab"), obrig=True, container=c2)
            campo("Cidade/Estado", k("cidade"), obrig=True, container=c3)
            c1, c2, c3 = st.columns(3)
            campo("Ramo de atividade", k("ramo"), obrig=True, container=c1)
            campo("Porte", k("porte"), container=c2)
            campo("Faturamento presumido", k("fat"), obrig=True, container=c3)
        else:
            c1, c2, c3 = st.columns(3)
            campo("Nome", k("nome"), obrig=True, container=c1)
            campo("Idade", k("idade"), obrig=True, container=c2)
            campo("Cidade/Estado", k("cidade"), obrig=True, container=c3)
            c1, c2 = st.columns(2)
            campo("Renda presumida", k("renda"), obrig=True, container=c1)
            campo("Registro profissional", k("regprof"), obrig=True, container=c2)
        for fila in ((("Registro societário", "regsoc"), ("Região de risco", "regiao"), ("PEP", "pep")),
                     (("Histórico de PLD", "hpld"), ("Histórico de fraude", "hfraude"), ("Mídia negativa", "midia"))):
            cols = st.columns(3)
            for col, (rot, c) in zip(cols, fila):
                escolha(rot, k(c), SIM_NAO, obrig=True, container=col)
            cols = st.columns(3)
            for col, (rot, c) in zip(cols, fila):
                if ss.get(k(c)) == "Sim":
                    campo(f"Detalhes — {rot}", k(c + "_d"), container=col)


def _bloco_lado(rotulo: str, nome: str, tot_chave_valor: str, tot_chave_cp: str, tipo: str) -> None:
    """Totais + contrapartes de um lado (crédito ou débito)."""
    lado = "Crédito" if nome == "cred" else "Débito"
    c1, c2 = st.columns(2)
    campo(f"Total de {lado}s", tot_chave_valor, obrig=True, ph="Exemplo: R$100.000,00", container=c1)
    campo(f"Total de contrapartes ({lado.lower()})", tot_chave_cp, obrig=True, container=c2)
    st.html(f'<div class="sx-sub-rot">Adicione contrapartes principais de {lado.lower()} ★</div>')
    for i, rid in enumerate(_lista(nome), 1):
        _bloco_contraparte(nome, rid, i)
    b1, b2, _ = st.columns([1.3, 1, 3])
    with b1, estilo.variante("sm"):
        st.button("+ Adicionar contraparte", key=f"add_{nome}", type="secondary", on_click=add_linha, args=(nome,))
    with b2, estilo.variante("sm"):
        st.button("Remover", key=f"rem_{nome}", type="secondary", on_click=rem_ultima, args=(nome,),
                  disabled=not _lista(nome))


def _gerar_grafico() -> None:
    total_c, total_d = parse_valor_br(_txt("f_tot_cred")), parse_valor_br(_txt("f_tot_deb"))
    if not (total_c or total_d):
        ss.erros_form = ["Preencha Total de Créditos/Débitos no Bloco 3 antes de gerar o gráfico."]
        return
    ss.erros_form = []
    ini, cred, deb = gerar_series_timeline(_txt("f_periodo"), total_c, total_d, _txt("f_evasao"))
    ss.timeline = {"inicio": ini, "cred": cred, "deb": deb,
                   "sig": (_txt("f_periodo"), total_c, total_d, _txt("f_evasao"))}


@st.cache_data(show_spinner=False, max_entries=24)
def _png_timeline(inicio: str, cred: tuple, deb: tuple) -> bytes:
    return renderizar_timeline_png(inicio, list(cred), list(deb))


def _gerar_dossie(tipo_caso: str) -> None:
    caso = montar_caso_do_formulario(tipo_caso)
    caso.numero_caso = gerar_numero_caso()
    faltando = validar_caso(caso)
    if faltando:
        ss.erros_form = faltando
        ss.gerado_numero = None
        return
    ss.erros_form = []
    sig = (caso.mov_periodo, parse_valor_br(caso.mov_total_credito), parse_valor_br(caso.mov_total_debito),
           caso.comp_evasao)
    tl = ss.timeline
    if caso.comp_evasao:
        if tl and tl.get("sig") == sig:
            caso.timeline_inicio, caso.timeline_creditos, caso.timeline_debitos = tl["inicio"], tl["cred"], tl["deb"]
        else:
            aplicar_timeline_ao_caso(caso)
            if caso.timeline_creditos:
                ss.timeline = {"inicio": caso.timeline_inicio, "cred": caso.timeline_creditos,
                               "deb": caso.timeline_debitos, "sig": sig}
    caso.scorecard_tipo = caso.rubrica()
    pdf_bytes = pdf_dossie.gerar_pdf(caso, "completo")
    store.salvar_caso(caso, pdf_bytes)
    ss.gerado_numero = caso.numero_caso


def _bloco_resp_legal() -> None:
    estilo.subtitulo("Campos adicionais — Caso Under 18")
    c1, c2 = st.columns(2)
    campo("Nome do responsável legal", "f_rep_nome", obrig=True, container=c1)
    campo("Renda presumida do responsável legal", "f_rep_renda", obrig=True, container=c2)
    c3, c4 = st.columns(2)
    campo("Registro profissional do responsável legal", "f_rep_regprof", obrig=True, container=c3)
    campo("Registro societário do responsável legal", "f_rep_regsoc", obrig=True, container=c4)
    c5, c6 = st.columns(2)
    campo("Histórico de PLD do responsável legal", "f_rep_hpld", obrig=True, container=c5)
    campo("Histórico de fraude do responsável legal", "f_rep_hfraude", obrig=True, container=c6)


def tela_formulario() -> None:
    tipo_caso = ss.tipo_caso_novo or TIPOS_CASO[0]
    eh_pj = tipo_caso == TIPO_PJ
    restaurar_formulario()

    if ss.ia_avisos:
        st.info("**Revise o que a IA preencheu.** " + " ".join(f"• {a}" for a in ss.ia_avisos))

    # ---- BLOCO 1 ----
    with estilo.cartao():
        estilo.cabecalho_bloco("Bloco 1", "Alerta / Sentença")
        st.html('<div class="sx-rot-fixo">Tipo de caso de calibração</div>'
                f'<div class="sx-pill-tracejada">{tipo_caso}</div>')
        c1, c2 = st.columns(2)
        campo("Fator gerador/alerta", "f_fator", obrig=True, container=c1)
        campo("Data do alerta", "f_data_alerta", padrao=formatar_data_br(date.today()), obrig=True, container=c2)
        campo("Descrição da sentença", "f_sentenca", obrig=True, area=True, altura=80)

    # ---- BLOCO 2 ----
    with estilo.cartao():
        estilo.cabecalho_bloco("Bloco 2", "KYC - Know Your Customer")
        if eh_pj:
            c1, c2, c3 = st.columns(3)
            campo("Nome da empresa", "f_empresa", obrig=True, container=c1)
            campo("Data de abertura", "f_emp_data", obrig=True, container=c2)
            campo("Ramo de atividade", "f_emp_ramo", obrig=True, container=c3)
            c4, c5, c6 = st.columns(3)
            campo("Porte", "f_emp_porte", obrig=True, container=c4)
            campo("Faturamento presumido", "f_emp_fat", obrig=True, container=c5)
            campo("Endereço", "f_emp_end", obrig=True, container=c6)
            selecao_estreita("Presença online", "f_pres_online", SIM_NAO)
            if ss.get("f_pres_online") == "Sim":
                campo("Detalhes da presença online", "f_pres_online_d", obrig=True,
                      ph="Insira o link ou informação sobre a presença online.")
            selecao_estreita("Fachada da empresa", "f_fachada", SIM_NAO)
            if ss.get("f_fachada") == "Sim":
                campo("Detalhes da fachada da empresa", "f_fachada_d", obrig=True,
                      ph="Insira o link ou informação sobre a fachada e data.")
        else:
            if tipo_caso == TIPO_UNDER18:
                _bloco_resp_legal()
            c1, c2, c3 = st.columns(3)
            campo("Nome do cliente", "f_nome", obrig=True, container=c1)
            campo("Idade", "f_idade", obrig=True, container=c2)
            campo("Cidade/Estado", "f_cidade", obrig=True, container=c3)
            nome_atual = _txt("f_nome")
            if nome_atual and inferir_genero(nome_atual) is None:
                g1, _ = st.columns([1, 2])
                escolha("Gênero do cliente (nome ambíguo)", "f_genero", list(GENEROS), padrao="", obrig=True,
                        container=g1)
                if GENEROS.get(ss.get("f_genero", ""), "") == "":
                    estilo.nota("Não foi possível inferir o gênero pelo primeiro nome. Informe para definir o "
                                "avatar do dossiê.")
            c4, c5 = st.columns(2)
            campo("Última atualização cadastral", "f_ult_atualizacao", obrig=True, container=c4)
            campo("Profissão informada pelo cliente", "f_profissao", obrig=True, container=c5)
            c6, c7, c8 = st.columns(3)
            campo("Renda presumida do cliente", "f_renda", obrig=True, container=c6)
            campo("Registros profissionais", "f_regprof", obrig=True, container=c7)
            escolha("Registros societários", "f_regsoc", SIM_NAO, obrig=True, container=c8)
            if ss.get("f_regsoc") == "Sim":
                s1, s2, s3, s4 = st.columns(4)
                campo("Razão social", "f_rs_razao", obrig=True, container=s1)
                campo("Data de abertura", "f_rs_data", obrig=True, container=s2)
                campo("Situação cadastral", "f_rs_situacao", obrig=True, container=s3)
                campo("Ramo de atividade", "f_rs_ramo", obrig=True, container=s4)

        selecao_estreita("Região de risco", "f_regiao", SIM_NAO)
        if ss.get("f_regiao") == "Sim":
            r1, r2 = st.columns(2)
            escolha("Risco da região", "f_tipo_regiao", TIPOS_REGIAO_RISCO_1, obrig=True, container=r1)
            if ss.get("f_tipo_regiao") == TIPOS_REGIAO_RISCO_1[2]:
                campo("Qual região de risco?", "f_tipo_regiao2", obrig=True, container=r2)
        selecao_estreita("PEP", "f_pep", SIM_NAO)
        if ss.get("f_pep") == "Sim":
            p1, p2 = st.columns([1, 2])
            escolha("Tipo de PEP", "f_tipo_pep", TIPOS_PEP, obrig=True, container=p1)
            campo("Descrição do PEP e carência", "f_desc_pep", obrig=True, container=p2)
        selecao_estreita("Mídia negativa", "f_midia", SIM_NAO)
        if ss.get("f_midia") == "Sim":
            campo("Detalhes da mídia negativa", "f_midia_d", obrig=True,
                  ph="Link da mídia, ou breve resumo, data e fonte")
        selecao_estreita("Histórico de PLD", "f_hpld", SIM_NAO)
        if ss.get("f_hpld") == "Sim":
            campo("Detalhes do histórico de PLD", "f_hpld_d", obrig=True)
        selecao_estreita("Histórico de fraudes", "f_hfraude", SIM_NAO)
        if ss.get("f_hfraude") == "Sim":
            campo("Detalhes do histórico de fraude", "f_hfraude_d", obrig=True)
        campo("Outras informações relevantes", "f_outras_info", area=True, altura=120,
              ph="Redes sociais, processos, compartilhamentos de dispositivo, entre outros")

    # ---- BLOCO 2.1 (PJ) ----
    if eh_pj:
        with estilo.cartao():
            estilo.cabecalho_bloco("Bloco 2.1", "Informações sobre o sócio")
            for rid in _lista("so"):
                k = lambda c, rid=rid: _kr("so", rid, c)  # noqa: E731
                with st.container(border=True):
                    estilo.marcador("sx-sub")
                    c1, c2, c3 = st.columns(3)
                    campo("Nome", k("nome"), obrig=True, container=c1)
                    campo("Idade", k("idade"), obrig=True, container=c2)
                    campo("Endereço", k("endereco"), obrig=True, container=c3)
                    c4, c5 = st.columns(2)
                    campo("Renda presumida", k("renda"), obrig=True, container=c4)
                    campo("Patrimônio", k("patrimonio"), container=c5)
                    for fila in ((("Região de risco", "regiao"), ("PEP", "pep"), ("Mídia negativa", "midia")),
                                 (("Histórico de PLD", "hpld"), ("Histórico de fraude", "hfraude"))):
                        cols = st.columns(3)
                        for col, (rot, c) in zip(cols, fila):
                            escolha(rot, k(c), SIM_NAO, obrig=True, container=col)
                        cols = st.columns(3)
                        for col, (rot, c) in zip(cols, fila):
                            if ss.get(k(c)) != "Sim":
                                continue
                            if c == "regiao":
                                escolha("Risco da região", k("tipo_regiao"), TIPOS_REGIAO_RISCO_1, container=col)
                            elif c == "pep":
                                escolha("Tipo de PEP", k("tipo_pep"), TIPOS_PEP, container=col)
                                campo("Descrição do PEP e carência", k("desc_pep"), container=col)
                            else:
                                campo(f"Detalhes — {rot}", k(c + "_d"), container=col)
            b1, b2, _ = st.columns([1.2, 1, 3])
            with b1, estilo.variante("sm"):
                st.button("+ Adicionar sócio", key="add_so", type="secondary", on_click=add_linha, args=("so",))
            with b2, estilo.variante("sm"):
                st.button("Remover", key="rem_so", type="secondary", on_click=rem_ultima, args=("so",),
                          disabled=not _lista("so"))

    # ---- BLOCO 3 ----
    with estilo.cartao():
        estilo.cabecalho_bloco("Bloco 3", "Resumo de movimentações")
        campo("Período", "f_periodo", obrig=True, ph="Ex: 01/06/2026 até 01/08/2026")
        _bloco_lado("Crédito", "cred", "f_tot_cred", "f_tot_cp_cred", tipo_caso)
        _bloco_lado("Débito", "deb", "f_tot_deb", "f_tot_cp_deb", tipo_caso)
        st.html('<div class="sx-sub-rot">Outras movimentações (opcional)</div>')
        for rid in _lista("om"):
            c1, c2 = st.columns([1, 3])
            escolha("Tipo", _kr("om", rid, "tipo"), TIPOS_OUTRAS_MOV, container=c1)
            campo("Descrição", _kr("om", rid, "info"), area=True, altura=80, container=c2)
        b1, b2, _ = st.columns([1.8, 1, 2.6])
        with b1, estilo.variante("sm"):
            st.button("+ Adicionar outra movimentação", key="add_om", type="secondary", on_click=add_linha, args=("om",))
        with b2, estilo.variante("sm"):
            st.button("Remover", key="rem_om", type="secondary", on_click=rem_ultima, args=("om",),
                      disabled=not _lista("om"))

    # ---- BLOCO 4 ----
    with estilo.cartao():
        estilo.cabecalho_bloco("Bloco 4", "Thundera - AML 360")
        selecao_estreita("Transações em perfil de arredondamento nas unidades de milhar ou em valores aproximados",
                         "f_arred", SIM_NAO)
        if ss.get("f_arred") == "Sim":
            for rid in _lista("ar"):
                c1, c2, c3 = st.columns(3)
                escolha("Créditos ou débitos", _kr("ar", rid, "cd"), ["Créditos", "Débitos"], obrig=True, container=c1)
                campo("Quantidade", _kr("ar", rid, "qtd"), obrig=True, container=c2)
                campo("Valor", _kr("ar", rid, "valor"), obrig=True, ph="Ex: R$1.000,00", container=c3)
            b1, b2, _ = st.columns([1.6, 1, 2.8])
            with b1, estilo.variante("sm"):
                st.button("+ Adicionar quantidade/valor", key="add_ar", type="secondary", on_click=add_linha,
                          args=("ar",))
            with b2, estilo.variante("sm"):
                st.button("Remover", key="rem_ar", type="secondary", on_click=rem_ultima, args=("ar",),
                          disabled=not _lista("ar"))
        selecao_estreita("Mensagens Pix", "f_pix", SIM_NAO)
        if ss.get("f_pix") == "Sim":
            for rid in _lista("px"):
                c1, c2, c3 = st.columns(3)
                escolha("Créditos ou débitos", _kr("px", rid, "cd"), ["Créditos", "Débitos"], obrig=True, container=c1)
                campo("Quantidade", _kr("px", rid, "qtd"), obrig=True, container=c2)
                campo("Mensagem Pix", _kr("px", rid, "msg"), obrig=True, container=c3)
            b1, b2, _ = st.columns([2, 1, 2.4])
            with b1, estilo.variante("sm"):
                st.button("+ Adicionar quantidade e mensagem Pix", key="add_px", type="secondary", on_click=add_linha,
                          args=("px",))
            with b2, estilo.variante("sm"):
                st.button("Remover", key="rem_px", type="secondary", on_click=rem_ultima, args=("px",),
                          disabled=not _lista("px"))
        e1, _ = st.columns([1, 2])
        escolha("Timeline de transferências", "f_evasao", OPCOES_EVASAO, padrao="", obrig=True, container=e1)
        if _txt("f_evasao"):
            estilo.nota("O gráfico é montado automaticamente com base no Total de Créditos, Total de Débitos e "
                        "Período preenchidos no Bloco 3.")
            with estilo.variante("sm"):
                st.button("+ Gerar/atualizar gráfico", key="gerar_grafico", type="secondary", on_click=_gerar_grafico)
            tl = ss.timeline
            if tl:
                st.html('<div class="sx-pills">'
                        + estilo.pilula("Créditos", "R$ " + formatar_brl(parse_valor_br(_txt("f_tot_cred"))).replace("R$", ""), "gde verde")
                        + estilo.pilula("Débitos", "R$ " + formatar_brl(parse_valor_br(_txt("f_tot_deb"))).replace("R$", ""), "gde vermelho")
                        + "</div>")
                st.image(_png_timeline(tl["inicio"], tuple(tl["cred"]), tuple(tl["deb"])), use_column_width=True)
        campo("Mudança de comportamento", "f_mudanca", area=True, altura=130)
        campo("Data de abertura da conta/data do último reporte", "f_data_conta", obrig=True)

    estilo.nota("Parecer Final do Analista, Alíneas Específicas e Diligência ficam disponíveis para preenchimento "
                "dentro do dossiê, após a geração — durante a calibração do time.")
    if ss.erros_form:
        estilo.msg_erro("Faltam campos obrigatórios: " + "; ".join(ss.erros_form) + ".")
    b1, b2, _ = st.columns([1.5, 1, 3])
    with b1:
        st.button("Gerar dossiê do caso", key="gerar_dossie", type="primary", on_click=_gerar_dossie, args=(tipo_caso,))
    with b2:
        st.button("← Voltar", key="form_voltar", type="secondary", on_click=ir_para, args=("modo_preenchimento",))

    numero = ss.gerado_numero
    if numero:
        caso = store.carregar_caso(numero)
        if caso:
            estilo.msg_ok(f"Dossiê {numero} salvo no Banco de Dossiês.")
            st.button(f"\U0001F4C4 Clique aqui para ver o dossiê {numero}", key="ver_dossie_gerado", type="primary",
                      on_click=ver_dossie, args=(numero, "formulario"))
            pdf = store.carregar_pdf(numero)
            if pdf:
                st.download_button("⬇ Baixar PDF do dossiê", data=pdf, file_name=f"dossie_{numero}.pdf",
                                   mime="application/pdf", key="dl_gerado")
            st.html(dossie_html.cabecalho_html(caso))
            for h in dossie_html.informacoes_html(caso):
                st.html(h)


# ---------------------------------------------------------------------------
# DOSSIÊ: Informações, Resolução e Avaliação
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, max_entries=48)
def _pdf_cache(numero: str, atualizado_em: str, escopo: str, extra: str, _caso: Caso) -> bytes:
    return pdf_dossie.gerar_pdf(_caso, escopo)


def _persistir(caso: Caso) -> None:
    """Grava o caso e regera o PDF completo (Informações + Resolução + Avaliação)."""
    pdf = pdf_dossie.gerar_pdf(caso, "completo")
    store.salvar_caso(caso, pdf)


def _quando(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y, %H:%M:%S")
    except (TypeError, ValueError):
        return iso or ""


def _selo_do_caso(caso: Caso) -> None:
    est = estilo_diligencia(caso.diligencia)
    if est == "pendente":
        estilo.selo("Diligência pendente", "pendente")
    else:
        estilo.selo(caso.diligencia, est)


# -- Resolução --------------------------------------------------------------

def _res_valor(caso: Caso, secao: str) -> Any:
    return {
        "parecer": caso.parecer_final, "alineas": caso.alineas,
        "jurisprudencias": caso.jurisprudencias_selecionadas,
        "razoes_clear": caso.razoes_clear_selecionadas,
        "razoes_cancelamento": caso.razoes_cancelamento_selecionadas,
        "diligencia": caso.diligencia,
    }[secao]


def _res_ler_widgets(caso: Caso, secao: str) -> None:
    n = caso.numero_caso
    if secao == "parecer":
        caso.parecer_final = ss.get(f"res_{n}_parecer", caso.parecer_final)
    elif secao == "alineas":
        caso.alineas = ss.get(f"res_{n}_alineas", caso.alineas)
    elif secao == "jurisprudencias":
        sel = []
        for grupo, opcoes in (("nupag", JURISPRUDENCIA_NUPAGAMENTOS), ("rep", JURISPRUDENCIA_REPORTAR_NUINVEST),
                              ("repcanc", JURISPRUDENCIA_REPORTAR_CANCELAR_NUINVEST)):
            sel += [o for i, o in enumerate(opcoes) if ss.get(f"res_{n}_jur_{grupo}_{i}", o in caso.jurisprudencias_selecionadas)]
        caso.jurisprudencias_selecionadas = sel
    elif secao == "razoes_clear":
        caso.razoes_clear_selecionadas = [o for i, o in enumerate(RAZOES_CLEAR)
                                          if ss.get(f"res_{n}_clear_{i}", o in caso.razoes_clear_selecionadas)]
    elif secao == "razoes_cancelamento":
        caso.razoes_cancelamento_selecionadas = [
            o for i, o in enumerate(RAZOES_CANCELAMENTO)
            if ss.get(f"res_{n}_canc_{i}", o in caso.razoes_cancelamento_selecionadas)]
    elif secao == "diligencia":
        v = ss.get(f"res_{n}_diligencia", caso.diligencia)
        caso.diligencia = v if v in DILIGENCIAS else ""


def _salvar_secao(numero: str, secao: str) -> None:
    caso = store.carregar_caso(numero)
    if not caso:
        return
    _res_ler_widgets(caso, secao)
    caso.resolucao_salva_em[secao] = agora_iso()
    _persistir(caso)


def _editar_secao(numero: str, secao: str) -> None:
    caso = store.carregar_caso(numero)
    if caso:
        caso.resolucao_salva_em.pop(secao, None)
        _persistir(caso)


def _salvar_caso_inteiro(numero: str) -> None:
    caso = store.carregar_caso(numero)
    if not caso:
        return
    agora = agora_iso()
    for secao in SECOES_RESOLUCAO:
        if secao not in caso.resolucao_salva_em:
            _res_ler_widgets(caso, secao)
            caso.resolucao_salva_em[secao] = agora
    caso.resolucao_bloqueada_em = agora
    _persistir(caso)


def _reabrir_caso(numero: str) -> None:
    caso = store.carregar_caso(numero)
    if caso:
        caso.resolucao_bloqueada_em = ""
        caso.resolucao_salva_em = {}
        _persistir(caso)


def _bloqueada(caso: Caso, secao: str) -> bool:
    return bool(caso.resolucao_bloqueada_em) or secao in caso.resolucao_salva_em


def _secao_resolucao(caso: Caso, secao: str, titulo: str, rotulo_pendente: str, corpo_fn, caixa_pendente="pend",
                     vazio_ok: bool = False) -> None:
    """Cartão de uma seção da Resolução: título, caixa (pendente/preenchida), corpo, Salvar."""
    n = caso.numero_caso
    travada = _bloqueada(caso, secao)
    em = caso.resolucao_salva_em.get(secao, "")
    with estilo.cartao():
        estilo.titulo_secao(titulo)
        with estilo.caixa("ok" if travada else caixa_pendente):
            estilo.rotulo_estado("Preenchido e bloqueado na calibração do time" if travada else rotulo_pendente, travada)
            corpo_fn(travada)
            with estilo.variante("sm"):
                st.button("Salvar", key=f"salvar_{n}_{secao}", type="secondary", disabled=travada,
                          on_click=_salvar_secao, args=(n, secao))
            if em:
                estilo.salvo_em(f"{_resumo_secao(caso, secao)}Salvo em {_quando(em)}.")
            if em and not caso.resolucao_bloqueada_em:
                with estilo.variante("lnk"):
                    st.button("Editar", key=f"editar_{n}_{secao}", on_click=_editar_secao, args=(n, secao))


def _resumo_secao(caso: Caso, secao: str) -> str:
    if secao == "jurisprudencias":
        return f"{len(caso.jurisprudencias_selecionadas)} selecionada(s) — "
    if secao == "razoes_clear":
        return f"{len(caso.razoes_clear_selecionadas)} selecionada(s) — "
    if secao == "razoes_cancelamento":
        return f"{len(caso.razoes_cancelamento_selecionadas)} selecionada(s) — "
    if secao == "diligencia" and caso.diligencia:
        return f"{caso.diligencia} — "
    return ""


def _checkboxes(caso: Caso, prefixo: str, opcoes: List[str], marcadas: List[str], travada: bool) -> None:
    for i, o in enumerate(opcoes):
        chave = f"res_{caso.numero_caso}_{prefixo}_{i}"
        _init(chave, o in marcadas)
        st.checkbox(o, key=chave, disabled=travada)


def _aba_resolucao(caso: Caso) -> None:
    n = caso.numero_caso
    _selo_do_caso(caso)
    with estilo.cartao():
        a1, a2, _ = st.columns([1.2, 1.3, 1])
        with a1:
            if caso.resolucao_bloqueada_em:
                st.button("Informações salvas e bloqueadas", key=f"bloq_{n}", disabled=True)
            else:
                st.button("Salvar informações do caso", key=f"salvar_caso_{n}", type="primary",
                          on_click=_salvar_caso_inteiro, args=(n,))
        with a2:
            if caso.resolucao_bloqueada_em:
                pdf = _pdf_cache(n, caso.atualizado_em, "resolucao", "", caso)
                st.download_button("Baixar versão atualizada em PDF", data=pdf, file_name=f"dossie_{n}_resolucao.pdf",
                                   mime="application/pdf", key=f"dl_res_{n}")
            else:
                st.button("Baixar versão atualizada em PDF", key=f"dl_res_off_{n}", disabled=True)
        if caso.resolucao_bloqueada_em:
            estilo.salvo_em(f"Caso salvo e bloqueado em {_quando(caso.resolucao_bloqueada_em)}.")
            with estilo.variante("lnk"):
                st.button("Reabrir para edição", key=f"reabrir_{n}", on_click=_reabrir_caso, args=(n,))
        else:
            estilo.nota("O botão de PDF fica disponível depois de clicar em \"Salvar informações do caso\". "
                        "O PDF gerado aqui inclui apenas as abas Informações do Caso e Resolução do Caso.")

    def parecer(tr):
        campo("Parecer", f"res_{n}_parecer", padrao=caso.parecer_final, area=True, altura=170, desabilitado=tr,
              ph="Elaboração livre do parecer, sem limite de caracteres.", oculto_rotulo=True)

    def alineas(tr):
        campo("Alíneas", f"res_{n}_alineas", padrao=caso.alineas, area=True, altura=140, desabilitado=tr,
              ph="Insira as alíneas aplicáveis, sem limite de caracteres.", oculto_rotulo=True)

    def jurisprudencias(tr):
        for titulo, prefixo, opcoes in (
                ("Opções de Jurisprudência para NuPagamentos", "jur_nupag", JURISPRUDENCIA_NUPAGAMENTOS),
                ("Jurisprudências para Reportar (NuInvest)", "jur_rep", JURISPRUDENCIA_REPORTAR_NUINVEST),
                ("Jurisprudências para Reportar e Cancelar (NuInvest)", "jur_repcanc",
                 JURISPRUDENCIA_REPORTAR_CANCELAR_NUINVEST)):
            estilo.subtitulo(titulo)
            _checkboxes(caso, prefixo, opcoes, caso.jurisprudencias_selecionadas, tr)

    def razoes_clear(tr):
        _checkboxes(caso, "clear", RAZOES_CLEAR, caso.razoes_clear_selecionadas, tr)

    def razoes_canc(tr):
        _checkboxes(caso, "canc", RAZOES_CANCELAMENTO, caso.razoes_cancelamento_selecionadas, tr)

    def diligencia(tr):
        chave = f"res_{n}_diligencia"
        opcoes = [""] + DILIGENCIAS
        if ss.get(chave) not in opcoes:
            ss[chave] = caso.diligencia if caso.diligencia in DILIGENCIAS else ""
        st.selectbox("Diligência", opcoes, key=chave, disabled=tr, label_visibility="collapsed",
                     format_func=lambda x: x if x else "Selecione")

    pend = "Pendente — preencher na calibração do time"
    _secao_resolucao(caso, "parecer", "Parecer Final do Analista", pend, parecer)
    _secao_resolucao(caso, "alineas", "Alíneas", pend, alineas)
    _secao_resolucao(caso, "jurisprudencias", "Jurisprudências", "Seleção múltipla — opcional", jurisprudencias)
    _secao_resolucao(caso, "razoes_clear", "Razões de Clear", "Seleção múltipla — opcional", razoes_clear)
    _secao_resolucao(caso, "razoes_cancelamento", "Razões de Cancelamento", "Seleção múltipla — opcional",
                     razoes_canc)
    _secao_resolucao(caso, "diligencia", "Diligência", "Pendente — definir na calibração do time", diligencia,
                     caixa_pendente="dash")


# -- Avaliação de Qualidade ------------------------------------------------

def _drivers_marcados(caso: Caso, travada: bool) -> List[str]:
    """Critérios marcados agora (widgets) ou salvos (se travada)."""
    n = caso.numero_caso
    if travada:
        return list(caso.scorecard_drivers_marcados)
    marcados = []
    for cat in listar_drivers_scorecard(caso.rubrica()):
        for i, d in enumerate(cat["drivers"]):
            chave = f"av_{n}_{cat['categoria']}_{i}"
            if ss.get(chave, d["nome"] in caso.scorecard_drivers_marcados):
                marcados.append(d["nome"])
    return marcados


def _salvar_avaliacao(numero: str) -> None:
    caso = store.carregar_caso(numero)
    if not caso:
        return
    caso.scorecard_tipo = caso.rubrica()
    caso.scorecard_drivers_marcados = _drivers_marcados(caso, False)
    caso.scorecard_feedback = ss.get(f"av_{numero}_feedback", caso.scorecard_feedback)
    caso.scorecard_salvo_em = agora_iso()
    _persistir(caso)


def _reabrir_avaliacao(numero: str) -> None:
    caso = store.carregar_caso(numero)
    if caso:
        caso.scorecard_salvo_em = ""
        _persistir(caso)


def _aba_avaliacao(caso: Caso) -> None:
    n = caso.numero_caso
    travada = bool(caso.scorecard_salvo_em)
    rubrica = caso.rubrica()
    marcados = _drivers_marcados(caso, travada)
    nota = calcular_nota_scorecard(rubrica, marcados)
    feedback_atual = ss.get(f"av_{n}_feedback", caso.scorecard_feedback)

    with estilo.cartao():
        # PDF só desta aba, com o que está na tela
        tmp = Caso.from_dict(caso.to_dict())
        tmp.scorecard_drivers_marcados = marcados
        tmp.scorecard_feedback = feedback_atual
        extra = "|".join(sorted(marcados)) + "||" + feedback_atual
        pdf = _pdf_cache(n, caso.atualizado_em, "avaliacao", extra, tmp)
        c1, _ = st.columns([1.4, 1.6])
        with c1:
            st.download_button("Baixar versão atualizada em PDF", data=pdf, file_name=f"dossie_{n}_avaliacao.pdf",
                               mime="application/pdf", key=f"dl_av_{n}")
        estilo.nota("O PDF gerado aqui inclui apenas o conteúdo desta aba (Avaliação de Qualidade).")

    with estilo.cartao():
        estilo.titulo_secao(f"Avaliação de Qualidade — {rubrica}")
        faixa = faixa_nota(nota)
        st.html('<div class="sx-nota-box"><div class="sx-nota-rot">Nota final</div>'
                f'<div class="sx-nota-val {faixa}">{formatar_nota(nota)}</div></div>')
        for cat in listar_drivers_scorecard(rubrica):
            estilo.subtitulo(f"Categoria: {cat['categoria']} — Peso {cat['peso'] * 100:.0f}%")
            for i, d in enumerate(cat["drivers"]):
                chave = f"av_{n}_{cat['categoria']}_{i}"
                _init(chave, d["nome"] in caso.scorecard_drivers_marcados)
                st.checkbox(d["nome"], key=chave, disabled=travada)
                st.html(f'<div class="sx-drv-desc">{_esc(d["aplicabilidade"])}</div>')
        estilo.subtitulo("Feedback de Qualidade")
        campo("Feedback de qualidade", f"av_{n}_feedback", padrao=caso.scorecard_feedback, area=True, altura=120,
              desabilitado=travada, oculto_rotulo=True)
        with estilo.variante("sm"):
            st.button("Salvar avaliação", key=f"salvar_av_{n}", type="primary", disabled=travada,
                      on_click=_salvar_avaliacao, args=(n,))
        if travada:
            estilo.salvo_em(f"Avaliação salva em {_quando(caso.scorecard_salvo_em)}. Nota final: {formatar_nota(nota)}.")
            with estilo.variante("lnk"):
                st.button("Editar avaliação", key=f"editar_av_{n}", on_click=_reabrir_avaliacao, args=(n,))


def _esc(texto: str) -> str:
    from html import escape
    return escape(texto or "")


def tela_dossie() -> None:
    numero = ss.get("caso_selecionado")
    caso = store.carregar_caso(numero) if numero else None
    if not caso:
        estilo.msg_erro("Caso não encontrado.")
        st.button("← Voltar ao Banco de Dossiês", key="dossie_nao_achou", type="secondary",
                  on_click=ir_para, args=("banco",))
        return

    topo1, topo2, _ = st.columns([1.8, 2.0, 2.2])
    with topo1, estilo.variante("topo"):
        st.button("← Voltar ao Sentinela", key="dossie_voltar_btn", type="primary", on_click=voltar_do_dossie)
    with topo2, estilo.variante("topo"):
        pdf = store.carregar_pdf(numero)
        if pdf:
            st.download_button("⬇ PDF completo (3 abas)", data=pdf, file_name=f"dossie_{numero}.pdf",
                               mime="application/pdf", key=f"dl_completo_{numero}")
    st.html(dossie_html.cabecalho_html(caso))
    aba1, aba2, aba3 = st.tabs(["Informações do Caso", "Resolução do Caso", "Avaliação de Qualidade"])
    with aba1:
        for h in dossie_html.informacoes_html(caso):
            st.html(h)
    with aba2:
        _aba_resolucao(caso)
    with aba3:
        _aba_avaliacao(caso)
    st.html(f'<div class="sx-rodape">Sentinela PLD · Dossiê gerado em {_quando(caso.criado_em)} '
            '· Uso interno e confidencial</div>')


# ---------------------------------------------------------------------------
# BANCO DE DOSSIÊS
# ---------------------------------------------------------------------------
def _buscar() -> None:
    ss.banco_modo = "busca"
    ss.caso_selecionado = None


def _consultar_tudo() -> None:
    ss.banco_modo = "tudo"
    ss.caso_selecionado = None


def tela_banco() -> None:
    estilo.titulo_cartao("Gerador de Casos - Calibração", "BANCO DE DOSSIÊS", pequeno=True)
    c1, c2 = st.columns([4, 1.1], vertical_alignment="bottom")
    with c1:
        campo("Consultar por número do caso", "banco_termo", ph="Ex: 2026-3E1DFA", on_change=_buscar)
    with c2:
        st.button("Buscar", key="banco_buscar", type="primary", on_click=_buscar)
    estilo.separador_ou("ou, se não tiver o número")
    with estilo.variante("larga"):
        st.button("Consultar banco de dados completo", key="banco_tudo", type="secondary", on_click=_consultar_tudo)

    modo = ss.banco_modo
    termo = (ss.get("banco_termo") or "").strip()
    if modo == "busca" and not termo:
        modo = ""
    resultados: List[Dict[str, Any]] = []
    if modo == "busca":
        resultados = store.buscar_por_numero(termo)
        if not resultados:
            estilo.vazio(f'Nenhum caso encontrado com o número "{termo}". Verifique o número digitado ou use '
                         '"Consultar banco de dados completo".')
    elif modo == "tudo":
        resultados = store.listar_indice()
        if not resultados:
            estilo.vazio("Nenhum dossiê salvo ainda. Gere um caso para ele aparecer aqui.")
    else:
        estilo.vazio('Digite um número de caso acima e clique em "Buscar", ou clique em "Consultar banco de dados '
                     'completo" para ver todos os dossiês salvos.')

    if resultados:
        with estilo.variante("linhas"):
            for item in resultados:
                rotulo = (f"{item['numero_caso']}  —  {item.get('nome_cliente', '')}   ·   "
                          f"{str(item.get('tipo_caso', '')).upper()}   ·   RISCO {item.get('risco', '—')}   "
                          f"·   {item.get('diligencia', 'Pendente')}   ↗")
                st.button(rotulo, key=f"abrir_{item['numero_caso']}", type="secondary",
                          on_click=ver_dossie, args=(item["numero_caso"], "banco"))
    botao_voltar = st.button("← Voltar", key="banco_voltar", type="secondary", on_click=ir_para, args=("home",))


# ---------------------------------------------------------------------------
# Roteamento
# ---------------------------------------------------------------------------
TELAS = {
    "home": (tela_home, "home"),
    "escolher_tipo": (tela_escolher_tipo, "tipo"),
    "modo_preenchimento": (tela_modo_preenchimento, "modo"),
    "preenchimento_ia": (tela_preenchimento_ia, "ia"),
    "formulario": (tela_formulario, "formulario"),
    "dossie": (tela_dossie, "dossie"),
    "banco": (tela_banco, "banco"),
}
_fn, _css = TELAS.get(ss.tela, TELAS["home"])
estilo.aplicar_estilo(_css)
_fn()
