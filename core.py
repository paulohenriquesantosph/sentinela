# -*- coding: utf-8 -*-
"""
Sentinela PLD - Núcleo de lógica (Databricks)
=============================================

Módulo com a lógica de negócio que não depende de interface:

- modelo de dados do caso (KYC PF/PJ, sócios, contrapartes de crédito/débito,
  Thundera - AML 360, resolução e avaliação de qualidade);
- cálculo da nota de qualidade (desconto por CATEGORIA, igual ao artefato);
- classificação de risco geral do caso;
- narrativa de "mudança de comportamento" e gráfico da timeline;
- validação dos campos obrigatórios;
- armazenamento do Banco de Dossiês (arquivos JSON + PDF num Volume).

A chamada de IA fica em ia.py e a geração do PDF em pdf_dossie.py.
A interface (Streamlit) está em app.py / estilo.py.
"""

from __future__ import annotations

import json
import os
import random
import re
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict, fields
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any, Dict, Iterator, List, Optional, Tuple

from opcoes import (
    DILIGENCIAS, SCORECARD_NUPAG, SCORECARD_NUINVEST,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

TIPOS_CASO = ["Pessoa Física (PF)", "Pessoa Jurídica (PJ)", "Cripto", "NuInvest", "Under 18"]
TIPO_PJ = "Pessoa Jurídica (PJ)"
TIPO_UNDER18 = "Under 18"
TIPO_CRIPTO = "Cripto"
TIPO_NUINVEST = "NuInvest"

TIPOS_REGIAO_RISCO_1 = [
    "Região de Fronteira",
    "Região de Extração Mineral e/ou de Extração de Madeira",
    "Outras Regiões de Risco",
]
TIPOS_PEP = ["PEP Titular", "PEP Relacionado"]
TIPOS_CONTRAPARTE = ["Pessoa Física", "Pessoa Jurídica"]
TIPOS_OUTRAS_MOV = [
    "Saques", "Boletos", "Gastos Cartão de Crédito", "Gastos Cartão de Débito",
    "Empréstimos", "Criptomoedas", "Investimentos", "Outros",
]
OPCOES_EVASAO = ["", "Rápida Evasão", "Sem Rápida Evasão"]

# Seções da aba Resolução do Caso (cada uma tem o seu próprio "Salvar").
# "anexos" só existe nos casos Cripto (ver Caso.secoes_resolucao); a Diligência é sempre a última.
SECOES_RESOLUCAO = ["parecer", "alineas", "jurisprudencias", "razoes_clear",
                    "razoes_cancelamento", "anexos", "diligencia"]

NEUTRO = "Não informado"

NOMES_MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
               "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

# Valores-base dos cinco meses que antecedem o início do período, na narrativa
# de mudança de comportamento (iguais ao artefato original).
VALORES_BASE_MUDANCA = ["R$1.000,00", "R$1.500,00", "R$2.000,00", "R$0,00", "R$0,10"]

_NUMERO_CASO_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z_-]{0,40}$")


def agora_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def gerar_numero_caso() -> str:
    """Número do caso no formato da versão Databricks: ano + 6 caracteres (2026-8058FB)."""
    return f"{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"


def numero_caso_valido(numero: str) -> bool:
    """Evita que um número de caso malformado vire caminho de arquivo."""
    return bool(numero and _NUMERO_CASO_RE.match(numero))


# ---------------------------------------------------------------------------
# Valores monetários e datas
# ---------------------------------------------------------------------------

def parse_valor_br(valor_str: Any) -> float:
    """Converte 'R$1.234,56', '1.234,56', '500 mil', '1,5 milhão'... em float.
    Retorna 0.0 se não conseguir interpretar."""
    if valor_str is None:
        return 0.0
    if isinstance(valor_str, (int, float)):
        return float(valor_str)
    texto = str(valor_str).strip().lower()
    if not texto:
        return 0.0
    multiplicador = 1.0
    if re.search(r"\bmilh(ão|ao|ões|oes)\b", texto):
        multiplicador = 1_000_000.0
    elif re.search(r"\bmil\b", texto):
        multiplicador = 1_000.0
    limpo = re.sub(r"[^\d,.\-]", "", texto)
    if not re.search(r"\d", limpo):
        return 0.0
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", limpo):
        limpo = limpo.replace(".", "")
    try:
        return float(limpo) * multiplicador
    except ValueError:
        return 0.0


# Nome antigo, usado por app.py da versão anterior.
_parse_valor_br = parse_valor_br


def formatar_brl(valor: float) -> str:
    """1234.5 -> 'R$1.234,50' (mesmo padrão dos exemplos do artefato)."""
    inteiro = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if valor < 0 else "") + "R$" + inteiro


def normalizar_valor_texto(texto: Any) -> str:
    """Se o texto é um valor monetário, devolve no formato R$1.234,56; senão, o texto original."""
    bruto = "" if texto is None else str(texto).strip()
    if not bruto:
        return ""
    valor = parse_valor_br(bruto)
    if valor == 0.0 and not re.search(r"\d", bruto):
        return bruto
    return formatar_brl(valor)


def parse_data_br(texto: str) -> Optional[date]:
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", texto or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def formatar_data_br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def somar_meses(d: date, meses: int) -> date:
    indice = d.year * 12 + (d.month - 1) + meses
    ano, mes = divmod(indice, 12)
    return date(ano, mes + 1, 1)


def parse_periodo(periodo: str) -> Optional[Tuple[date, date]]:
    """'01/04/2026 até 30/09/2026' -> (date, date). None se não houver duas datas válidas."""
    datas = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", periodo or "")
    if len(datas) < 2:
        return None
    ini, fim = parse_data_br(datas[0]), parse_data_br(datas[1])
    if not ini or not fim or fim < ini:
        return None
    return ini, fim


def periodo_padrao(hoje: Optional[date] = None) -> str:
    """Quando não há período no texto: dois meses terminando no dia 1º do mês
    anterior à data de criação do caso."""
    hoje = hoje or date.today()
    fim = somar_meses(date(hoje.year, hoje.month, 1), -1)
    ini = somar_meses(fim, -2)
    return f"{formatar_data_br(ini)} até {formatar_data_br(fim)}"


# ---------------------------------------------------------------------------
# Modelo de dados
# ---------------------------------------------------------------------------

@dataclass
class ContraparteMovimentacao:
    """Contraparte principal de crédito ou débito (Bloco 3)."""
    tipo: str = "Pessoa Física"
    nome: str = ""
    idade: str = ""
    cidade_estado: str = ""
    renda_presumida: str = ""          # PF
    registro_profissional: str = ""    # PF
    data_abertura: str = ""            # PJ
    ramo_atividade: str = ""           # PJ
    faturamento_presumido: str = ""    # PJ
    porte: str = ""                    # PJ
    porcentagem: str = ""
    valor: str = ""
    num_transacoes: str = ""
    # mini-KYC da contraparte
    registro_societario: str = "Não"
    registro_societario_detalhe: str = ""
    regiao_risco: str = "Não"
    regiao_risco_detalhe: str = ""
    pep: str = "Não"
    pep_detalhe: str = ""
    historico_pld: str = "Não"
    historico_pld_detalhe: str = ""
    historico_fraude: str = "Não"
    historico_fraude_detalhe: str = ""
    midia_negativa: str = "Não"
    midia_negativa_detalhe: str = ""


@dataclass
class OutraMovimentacao:
    tipo: str = "Outros"
    info: str = ""


@dataclass
class ItemArredondamento:
    cred_deb: str = "Créditos"
    quantidade: str = ""
    valor: str = ""


@dataclass
class MensagemPix:
    cred_deb: str = "Créditos"
    quantidade: str = ""
    mensagem: str = ""


@dataclass
class Socio:
    nome: str = ""
    idade: str = ""
    endereco: str = ""
    renda_presumida: str = ""
    patrimonio: str = ""
    regiao_risco: str = "Não"
    tipo_regiao_risco: str = ""
    pep: str = "Não"
    tipo_pep: str = ""
    descricao_pep: str = ""
    historico_pld: str = "Não"
    historico_pld_detalhe: str = ""
    historico_fraude: str = "Não"
    historico_fraude_detalhe: str = ""
    midia_negativa: str = "Não"
    midia_negativa_detalhe: str = ""


@dataclass
class Caso:
    numero_caso: str
    tipo_caso: str
    schema_version: int = 2

    # Bloco 1 - Alerta / Sentença
    fator_gerador: str = ""
    data_alerta: str = ""
    sentenca: str = ""

    # Bloco 2 - KYC (comum)
    regiao_risco: str = "Não"
    tipo_regiao_risco: str = ""       # Fronteira / Extração... / Outras
    tipo_regiao_risco_2: str = ""     # detalhe quando "Outras Regiões de Risco"
    pep: str = "Não"
    tipo_pep: str = ""
    descricao_pep: str = ""
    midia_negativa: str = "Não"
    midia_negativa_detalhe: str = ""
    historico_pld: str = "Não"
    historico_pld_detalhe: str = ""
    historico_fraude: str = "Não"
    historico_fraude_detalhe: str = ""
    outras_info: str = ""

    # KYC - PF
    nome_cliente: str = ""
    genero: str = ""                  # "M", "F" (define o avatar do dossiê)
    idade: str = ""
    cidade_estado: str = ""
    ultima_atualizacao_cadastral: str = ""
    profissao_informada: str = ""
    renda_presumida: str = ""
    registro_profissional: str = ""
    registro_societario: str = "Não"
    reg_soc_razao_social: str = ""
    reg_soc_data_abertura: str = ""
    reg_soc_situacao_cadastral: str = ""
    reg_soc_ramo_atividade: str = ""
    reg_soc_porte: str = ""
    reg_soc_faturamento_presumido: str = ""
    reg_soc_endereco: str = ""

    # KYC - PJ
    nome_empresa: str = ""
    data_abertura: str = ""
    ramo_atividade: str = ""
    porte: str = ""
    faturamento_presumido: str = ""
    endereco: str = ""
    presenca_online: str = "Não"
    fachada_empresa: str = "Não"
    socios: List[Socio] = field(default_factory=list)

    # KYC - Under 18 (responsável legal)
    rep_nome: str = ""
    rep_renda_presumida: str = ""
    rep_reg_prof: str = ""
    rep_reg_soc: str = ""
    rep_hist_pld: str = ""
    rep_hist_fraude: str = ""

    # Bloco 3 - Resumo de Movimentações
    mov_periodo: str = ""
    mov_total_credito: str = ""
    mov_total_contrapartes_credito: str = ""
    mov_total_debito: str = ""
    mov_total_contrapartes_debito: str = ""
    contrapartes_credito: List[ContraparteMovimentacao] = field(default_factory=list)
    contrapartes_debito: List[ContraparteMovimentacao] = field(default_factory=list)
    outras_movimentacoes: List[OutraMovimentacao] = field(default_factory=list)

    # Bloco 4 - Thundera / AML 360
    comp_arredondamento: str = "Não"
    arredondamento_itens: List[ItemArredondamento] = field(default_factory=list)
    comp_pix: str = "Não"
    pix_itens: List[MensagemPix] = field(default_factory=list)
    comp_evasao: str = ""             # "Rápida Evasão" ou "Sem Rápida Evasão"
    comp_mudanca_comportamento: str = ""
    comp_data_abertura_ultimo_reporte: str = ""
    # Séries diárias do gráfico (guardadas para o gráfico não mudar a cada abertura)
    timeline_inicio: str = ""         # DD/MM/AAAA do primeiro dia
    timeline_creditos: List[float] = field(default_factory=list)
    timeline_debitos: List[float] = field(default_factory=list)

    # Aba Resolução do Caso
    parecer_final: str = ""
    alineas: str = ""
    jurisprudencias_selecionadas: List[str] = field(default_factory=list)
    razoes_clear_selecionadas: List[str] = field(default_factory=list)
    razoes_cancelamento_selecionadas: List[str] = field(default_factory=list)
    anexos: str = ""                  # só Cripto: descrição dos documentos anexados, um por linha
    diligencia: str = ""
    resolucao_salva_em: Dict[str, str] = field(default_factory=dict)  # seção -> timestamp
    resolucao_bloqueada_em: str = ""  # "Salvar informações do caso" (trava a aba inteira)

    # Aba Avaliação de Qualidade
    scorecard_tipo: str = "AML Nupag"   # redefinido pelo tipo do caso (ver rubrica())
    scorecard_drivers_marcados: List[str] = field(default_factory=list)
    scorecard_feedback: str = ""
    scorecard_salvo_em: str = ""

    criado_em: str = field(default_factory=agora_iso)
    atualizado_em: str = field(default_factory=agora_iso)

    # -- helpers ---------------------------------------------------------
    def eh_pj(self) -> bool:
        return self.tipo_caso == TIPO_PJ

    def rubrica(self) -> str:
        """AML NuInvest para casos NuInvest; AML Nupag para os demais."""
        return "AML NuInvest" if self.tipo_caso == TIPO_NUINVEST else "AML Nupag"

    def nome_display(self) -> str:
        return self.nome_empresa if self.eh_pj() else self.nome_cliente

    def nota_qualidade(self) -> float:
        return calcular_nota_scorecard(self.rubrica(), self.scorecard_drivers_marcados)

    def secoes_resolucao(self) -> List[str]:
        """Seções da Resolução deste caso: "anexos" só aparece no tipo Cripto."""
        return [x for x in SECOES_RESOLUCAO if x != "anexos" or self.tipo_caso == TIPO_CRIPTO]

    def lista_anexos(self) -> List[str]:
        return [l.strip() for l in (self.anexos or "").splitlines() if l.strip()]

    def resolucao_travada(self) -> bool:
        return bool(self.resolucao_bloqueada_em)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Caso":
        """Reconstrói o Caso ignorando chaves desconhecidas (casos antigos ou
        de versões futuras continuam abrindo)."""
        d = dict(d)

        def _lista(chave, classe):
            return [_construir(classe, x) for x in d.get(chave, []) or []]

        d["socios"] = _lista("socios", Socio)
        d["contrapartes_credito"] = _lista("contrapartes_credito", ContraparteMovimentacao)
        d["contrapartes_debito"] = _lista("contrapartes_debito", ContraparteMovimentacao)
        d["outras_movimentacoes"] = _lista("outras_movimentacoes", OutraMovimentacao)
        d["arredondamento_itens"] = _lista("arredondamento_itens", ItemArredondamento)
        d["pix_itens"] = _lista("pix_itens", MensagemPix)
        return _construir(Caso, d)


def _construir(classe, dados: Dict[str, Any]):
    validos = {f.name for f in fields(classe)}
    return classe(**{k: v for k, v in dados.items() if k in validos})


# ---------------------------------------------------------------------------
# Avatar / gênero
# ---------------------------------------------------------------------------

_NOMES_FEMININOS = {
    "isabel", "beatriz", "raquel", "carmen", "ester", "ingrid", "lais", "laís", "iris", "íris", "ruth",
    "miriam", "míriam", "rachel", "abigail", "alice", "aline", "luz", "mirian", "thais", "thaís", "marisol",
    "liz", "rose", "joyce", "michele", "nicole", "simone", "denise", "elisabete", "elizabeth",
}
_NOMES_MASCULINOS = {
    "luca", "joshua", "jonas", "elias", "lucas", "matheus", "mateus", "thomas", "tomas", "tomás", "joão", "joao",
    "jose", "josé", "marcos", "marcio", "márcio", "paulo", "pedro", "rafael", "gabriel", "miguel", "daniel",
    "samuel", "manuel", "rodrigo", "diego", "thiago", "tiago", "bruno", "carlos", "ricardo", "felipe", "fernando",
    "gustavo", "henrique", "leonardo", "eduardo", "marcelo", "fabio", "fábio", "andre", "andré", "caio", "davi",
    "lorenzo", "enzo", "vitor", "victor", "arthur", "artur", "heitor", "bernardo", "nicolas", "nicolau",
}
_NOMES_AMBIGUOS = {
    "alex", "cris", "dani", "jean", "juan", "ariel", "noa", "sasha", "ale", "gabi", "jamie", "andrea", "robin",
    "val", "kelly", "kely", "mel", "nico", "rennan", "renan", "lui", "luan", "dayan", "yuri", "jô", "jo",
}


def inferir_genero(nome: str) -> Optional[str]:
    """'M' ou 'F' a partir do primeiro nome; None se for ambíguo ou desconhecido
    (nesse caso o Sentinela pergunta ao analista)."""
    partes = (nome or "").strip().split()
    if not partes:
        return None
    p = partes[0].lower()
    if p in _NOMES_AMBIGUOS:
        return None
    if p in _NOMES_FEMININOS:
        return "F"
    if p in _NOMES_MASCULINOS:
        return "M"
    if p.endswith(("a", "ã", "e")) and p not in ("jose", "dante", "felipe", "alexandre", "henrique", "jorge", "wellington"):
        return "F" if p.endswith(("a", "ã")) else None
    if p.endswith(("o", "r", "s", "l", "n", "m", "u", "z", "k", "d", "t", "i")):
        return "M"
    return None


# ---------------------------------------------------------------------------
# Campos obrigatórios (os mesmos do artefato original)
# ---------------------------------------------------------------------------

def validar_caso(caso: Caso) -> List[str]:
    """Devolve os rótulos dos campos obrigatórios que faltam.

    Todos os tipos, exceto PJ: nome, idade, renda presumida e gênero.
    PJ: nome da empresa e faturamento presumido.
    Todos: período, totais de créditos e débitos e total de contrapartes."""
    faltando: List[str] = []
    if caso.eh_pj():
        if not caso.nome_empresa.strip():
            faltando.append("Nome da Empresa")
        if not caso.faturamento_presumido.strip():
            faltando.append("Faturamento Presumido")
    else:
        if not caso.nome_cliente.strip():
            faltando.append("Nome do Cliente")
        if not caso.idade.strip():
            faltando.append("Idade")
        if not caso.renda_presumida.strip():
            faltando.append("Renda Presumida do Cliente")
        if caso.genero not in ("M", "F"):
            faltando.append("Gênero do cliente")
    if not caso.mov_periodo.strip():
        faltando.append("Período")
    if not caso.mov_total_credito.strip():
        faltando.append("Total de Créditos")
    if not caso.mov_total_debito.strip():
        faltando.append("Total de Débitos")
    if not caso.mov_total_contrapartes_credito.strip():
        faltando.append("Total de Contrapartes (Crédito)")
    if not caso.mov_total_contrapartes_debito.strip():
        faltando.append("Total de Contrapartes (Débito)")
    return faltando


def percentual_restante(contrapartes: List[ContraparteMovimentacao]) -> Optional[float]:
    """100% menos a soma das porcentagens listadas; None se nenhuma tiver porcentagem."""
    pcts = [parse_valor_br(c.porcentagem) for c in contrapartes if (c.porcentagem or "").strip()]
    if not pcts:
        return None
    return max(0.0, 100.0 - sum(pcts))


# ---------------------------------------------------------------------------
# Scorecard (avaliação de qualidade)
# ---------------------------------------------------------------------------

def listar_drivers_scorecard(tipo: str) -> List[Dict[str, Any]]:
    return SCORECARD_NUINVEST if tipo == "AML NuInvest" else SCORECARD_NUPAG


def calcular_nota_scorecard(tipo: str, drivers_marcados: List[str]) -> float:
    """Nota de qualidade, de 0 a 100.

    Regra do artefato original: a nota parte de 100% e perde o peso de cada
    CATEGORIA que tenha ao menos um critério marcado, uma única vez. Marcar três
    critérios de Customer Critical desconta 15% (não 45%). Um critério de
    Regulatory Critical (peso 100%) zera a nota. Business Intelligence (peso 0%)
    registra o problema sem descontar."""
    marcados = set(drivers_marcados or [])
    nota = 100.0
    for categoria in listar_drivers_scorecard(tipo):
        if any(d["nome"] in marcados for d in categoria["drivers"]):
            nota -= categoria["peso"] * 100
    return max(0.0, round(nota, 2))


def faixa_nota(nota: float) -> str:
    """Faixa de cor da nota: verde a partir de 90%, âmbar de 70% a 89%, vermelho abaixo de 70%."""
    if nota >= 90:
        return "verde"
    if nota >= 70:
        return "ambar"
    return "vermelho"


def formatar_nota(nota: float) -> str:
    return f"{nota:.0f}%" if abs(nota - round(nota)) < 1e-9 else f"{nota:.1f}%".replace(".", ",")


def resumo_scorecard(caso: Caso) -> List[Dict[str, Any]]:
    """Por categoria: peso, critérios marcados (com a aplicabilidade) e total de critérios."""
    marcados = set(caso.scorecard_drivers_marcados)
    out = []
    for cat in listar_drivers_scorecard(caso.rubrica()):
        sel = [d for d in cat["drivers"] if d["nome"] in marcados]
        out.append({
            "categoria": cat["categoria"], "peso": cat["peso"],
            "total": len(cat["drivers"]), "marcados": sel,
        })
    return out


def estilo_diligencia(diligencia: str) -> str:
    """Cor do selo: verde (Clear), âmbar (Reportar), vermelho (Reportar e Cancelar), neutro (Cancelar)."""
    d = (diligencia or "").lower()
    if d.startswith("clear"):
        return "verde"
    if d.startswith("reportar e cancelar"):
        return "vermelho"
    if d.startswith("reportar"):
        return "ambar"
    if d.startswith("cancelar"):
        return "neutro"
    return "pendente"


# ---------------------------------------------------------------------------
# Mudança de comportamento
# ---------------------------------------------------------------------------

def gerar_narrativa_mudanca_comportamento(periodo_texto: str, valor_aproximado: str,
                                          hoje: Optional[date] = None) -> str:
    """Narrativa mês a mês, igual à do artefato original.

    Os cinco meses anteriores ao início do período recebem valores-base fixos
    (R$1.000,00; R$1.500,00; R$2.000,00; R$0,00 e R$0,10) e o pico informado é
    atribuído ao PRIMEIRO mês do período. Sem período válido, usa o período
    padrão (dois meses terminando no dia 1º do mês anterior à criação)."""
    pr = parse_periodo(periodo_texto) or parse_periodo(periodo_padrao(hoje))
    inicio = pr[0]
    pico = normalizar_valor_texto(valor_aproximado) or "R$0,00"
    linhas = []
    for k, valor in zip(range(5, 0, -1), VALORES_BASE_MUDANCA):
        mes = somar_meses(inicio, -k)
        linhas.append(f"{NOMES_MESES[mes.month - 1]} {valor}")
    linhas.append(f"{NOMES_MESES[inicio.month - 1]} {pico}")
    return "\n".join(linhas)


def pico_mudanca_sugerido(total_credito: float, total_debito: float,
                          rng: Optional[random.Random] = None) -> str:
    """Valor elevado para o mês da mudança, sempre abaixo do maior total movimentado
    no período do alerta (entre 40% e 70% dele, arredondado a R$100)."""
    rng = rng or random.Random()
    teto = max(total_credito, total_debito)
    if teto <= 0:
        return "R$0,00"
    valor = teto * rng.uniform(0.4, 0.7)
    return formatar_brl(min(round(valor / 100.0) * 100.0 or valor, teto))


def gerar_narrativa_mudanca_mensal(inicio: date, fim: date, mes_mudanca: date, valor_pico: str) -> str:
    """Narrativa mês a mês do mês `inicio` ao mês `fim`: os meses comuns recebem os
    valores-base (repetidos em ciclo) e o mês da mudança recebe o pico."""
    meses, atual = [], date(inicio.year, inicio.month, 1)
    while atual <= date(fim.year, fim.month, 1) and len(meses) < 24:
        meses.append(atual)
        atual = somar_meses(atual, 1)
    com_ano = inicio.year != fim.year
    pico = normalizar_valor_texto(valor_pico) or "R$0,00"
    linhas, i = [], 0
    for mes in meses:
        nome = NOMES_MESES[mes.month - 1] + (f"/{mes.year}" if com_ano else "")
        if (mes.year, mes.month) == (mes_mudanca.year, mes_mudanca.month):
            linhas.append(f"{nome} {pico}")
        else:
            linhas.append(f"{nome} {VALORES_BASE_MUDANCA[i % len(VALORES_BASE_MUDANCA)]}")
            i += 1
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Timeline de transferências (gráfico)
# ---------------------------------------------------------------------------

def gerar_series_timeline(periodo: str, total_credito: float, total_debito: float,
                          evasao: str, rng: Optional[random.Random] = None
                          ) -> Tuple[str, List[float], List[float]]:
    """Distribui os totais dia a dia ao longo do período.

    Com rápida evasão, créditos e débitos usam os mesmos pesos diários (o
    dinheiro entra e sai no mesmo dia). Sem rápida evasão, os dois lados
    alternam dias. A distribuição é sorteada: o gráfico ilustra o padrão, não
    reproduz um extrato."""
    rng = rng or random.Random()
    pr = parse_periodo(periodo) or parse_periodo(periodo_padrao())
    ini, fim = pr
    dias = min(max((fim - ini).days + 1, 1), 400)
    pesos = [rng.random() ** 3 + 0.01 for _ in range(dias)]

    def _normalizar(ws: List[float], total: float) -> List[float]:
        soma = sum(ws)
        if not soma:
            return [0.0 for _ in ws]
        valores = [round(total * w / soma, 2) for w in ws]
        # joga a diferença de arredondamento no maior dia, para a soma bater com o total
        resto = round(total - sum(valores), 2)
        if resto:
            i = max(range(len(valores)), key=lambda k: valores[k])
            valores[i] = round(valores[i] + resto, 2)
        return valores

    if evasao == "Rápida Evasão" or dias == 1:
        cred = _normalizar(pesos, total_credito)
        deb = _normalizar(pesos, total_debito)
    else:
        pc = [w if i % 2 == 0 else 0.0 for i, w in enumerate(pesos)]
        pd = [w if i % 2 == 1 else 0.0 for i, w in enumerate(pesos)]
        cred = _normalizar(pc, total_credito)
        deb = _normalizar(pd, total_debito)
    return formatar_data_br(ini), cred, deb


def aplicar_timeline_ao_caso(caso: Caso, rng: Optional[random.Random] = None) -> bool:
    """(Re)gera a série diária do caso a partir do período, dos totais e da escolha de
    evasão. Devolve False se não houver totais para montar o gráfico."""
    total_c = parse_valor_br(caso.mov_total_credito)
    total_d = parse_valor_br(caso.mov_total_debito)
    if not caso.comp_evasao or not (total_c or total_d):
        return False
    caso.timeline_inicio, caso.timeline_creditos, caso.timeline_debitos = gerar_series_timeline(
        caso.mov_periodo, total_c, total_d, caso.comp_evasao, rng)
    return True


def _escala_eixo(valor_max: float) -> Tuple[float, float]:
    """(topo, passo) do eixo Y: topo é o próximo múltiplo do passo acima do maior valor."""
    if valor_max <= 0:
        return 10.0, 5.0
    bruto = valor_max / 1.0
    magnitude = 10 ** (len(str(int(bruto))) - 1) if bruto >= 1 else 1
    passo = magnitude
    topo = (int(valor_max // passo) + 1) * passo
    if topo / passo < 2:
        topo += passo
    return float(topo), float(passo)


def renderizar_timeline_png(inicio: str, creditos: List[float], debitos: List[float],
                            largura_pol: float = 8.6, altura_pol: float = 3.3, dpi: int = 130) -> bytes:
    """Gráfico de barras espelhadas (créditos acima, débitos abaixo), no estilo do dossiê."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(creditos)
    ini = parse_data_br(inicio) or date.today()
    fig, ax = plt.subplots(figsize=(largura_pol, altura_pol), dpi=dpi)
    xs = list(range(n))
    ax.bar(xs, creditos, color="#2F6F62", width=0.78, linewidth=0)
    ax.bar(xs, [-d for d in debitos], color="#A13D2E", width=0.78, linewidth=0)
    ax.axhline(0, color="#2A2035", linewidth=1.0)

    vmax = max([*creditos, *debitos, 0.0])
    topo, passo = _escala_eixo(vmax)
    ax.set_ylim(-topo, topo)
    ticks = [-topo, -topo / 2, 0, topo / 2, topo]
    if topo / passo >= 2:
        ticks = [v * passo for v in range(-int(topo // passo), int(topo // passo) + 1)]
        if len(ticks) > 5:
            ticks = [-topo, -topo / 2, 0, topo / 2, topo]
    ax.set_yticks(ticks)

    def _fmt(v, _pos=None):
        s = f"R$ {abs(v) / 1000:.2f}K".replace(".", ",")
        return ("-" + s) if v < 0 else s

    ax.set_yticklabels([_fmt(v) for v in ticks], fontsize=7, family="DejaVu Sans Mono", color="#2A2035")
    ax.grid(axis="y", color="#C9B6DE", linewidth=0.8)
    ax.set_axisbelow(True)
    passo_x = max(1, round(n / 12)) if n else 1
    pos = list(range(0, n, passo_x))
    ax.set_xticks(pos)
    ax.set_xticklabels([formatar_data_br(ini + timedelta(days=p)) for p in pos],
                       fontsize=7, family="DejaVu Sans Mono", color="#2A2035")
    ax.set_xlim(-1, max(n, 1))
    for lado in ("top", "right", "left", "bottom"):
        ax.spines[lado].set_visible(False)
    ax.tick_params(length=0)
    ax.tick_params(axis="x", pad=9)
    ax.set_title("Timeline de Transferências", fontsize=10.5, family="DejaVu Sans Mono",
                 fontweight="bold", color="#2A2035", pad=10)
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    plt.close(fig)
    return buf.getvalue()


def grafico_do_caso(caso: Caso, **kw) -> Optional[bytes]:
    """PNG do gráfico do caso (None se o caso não tiver timeline)."""
    if not caso.timeline_creditos:
        return None
    return renderizar_timeline_png(caso.timeline_inicio, caso.timeline_creditos,
                                   caso.timeline_debitos, **kw)


# ---------------------------------------------------------------------------
# Armazenamento (Banco de Dossiês)
# ---------------------------------------------------------------------------

class ArmazenamentoLocal:
    """Banco de Dossiês em arquivos: um JSON por caso, um índice leve e o PDF
    mais recente de cada caso. Funciona igual em disco local e em um Volume do
    Unity Catalog (SENTINELA_DATA_DIR).

    Layout:
        <base>/indice_dossies.json
        <base>/caso_<numero>.json
        <base>/pdfs/dossie_<numero>.pdf
    """

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.environ.get("SENTINELA_DATA_DIR", "./data")
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self._pasta_pdfs(), exist_ok=True)
        self._indice_path = os.path.join(self.base_dir, "indice_dossies.json")
        self._lock_path = os.path.join(self.base_dir, ".indice.lock")
        if not os.path.exists(self._indice_path):
            self._escrever_indice([])

    # -- caminhos --------------------------------------------------------
    def _pasta_pdfs(self) -> str:
        return os.path.join(self.base_dir, "pdfs")

    def _caso_path(self, numero_caso: str) -> str:
        if not numero_caso_valido(numero_caso):
            raise ValueError(f"Número de caso inválido: {numero_caso!r}")
        return os.path.join(self.base_dir, f"caso_{numero_caso}.json")

    def _pdf_path(self, numero_caso: str) -> str:
        if not numero_caso_valido(numero_caso):
            raise ValueError(f"Número de caso inválido: {numero_caso!r}")
        return os.path.join(self._pasta_pdfs(), f"dossie_{numero_caso}.pdf")

    # -- escrita atômica e trava ----------------------------------------
    @staticmethod
    def _escrever_atomico(path: str, dados: bytes) -> None:
        pasta = os.path.dirname(path) or "."
        fd, tmp = tempfile.mkstemp(dir=pasta, prefix=".tmp_", suffix=".part")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(dados)
            os.replace(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    @contextmanager
    def _trava(self, timeout: float = 10.0) -> Iterator[None]:
        """Evita que duas gravações simultâneas do índice se atropelem (a última
        gravação não apaga mais o caso da outra). Usa um arquivo de trava criado
        com O_EXCL, que funciona em disco local e em Volumes."""
        inicio = time.time()
        fd = None
        while True:
            try:
                fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                try:  # trava velha (processo que caiu)
                    if time.time() - os.path.getmtime(self._lock_path) > 30:
                        os.remove(self._lock_path)
                        continue
                except OSError:
                    pass
                if time.time() - inicio > timeout:
                    break  # segue sem trava em vez de travar o app
                time.sleep(0.05)
        try:
            yield
        finally:
            if fd is not None:
                os.close(fd)
                try:
                    os.remove(self._lock_path)
                except OSError:
                    pass

    # -- índice ----------------------------------------------------------
    def _ler_indice(self) -> List[Dict[str, Any]]:
        try:
            with open(self._indice_path, "r", encoding="utf-8") as f:
                dados = json.load(f)
            if isinstance(dados, list):
                return dados
        except (OSError, ValueError):
            pass
        return self.reconstruir_indice(gravar=False)

    def _escrever_indice(self, indice: List[Dict[str, Any]]) -> None:
        self._escrever_atomico(
            self._indice_path,
            json.dumps(indice, ensure_ascii=False, indent=2).encode("utf-8"))

    @staticmethod
    def _entrada_indice(caso: Caso) -> Dict[str, Any]:
        return {
            "numero_caso": caso.numero_caso,
            "nome_cliente": caso.nome_display() or "Sem nome",
            "tipo_caso": caso.tipo_caso,
            "diligencia": caso.diligencia or "Pendente",
            "criado_em": caso.criado_em,
            "atualizado_em": caso.atualizado_em,
        }

    def reconstruir_indice(self, gravar: bool = True) -> List[Dict[str, Any]]:
        """Reconstrói o índice lendo os arquivos caso_*.json (recupera um índice
        corrompido ou casos que ficaram de fora)."""
        entradas = []
        for nome in os.listdir(self.base_dir):
            if nome.startswith("caso_") and nome.endswith(".json"):
                try:
                    with open(os.path.join(self.base_dir, nome), "r", encoding="utf-8") as f:
                        entradas.append(self._entrada_indice(Caso.from_dict(json.load(f))))
                except (OSError, ValueError, TypeError):
                    continue
        entradas.sort(key=lambda e: e.get("criado_em", ""), reverse=True)
        if gravar:
            with self._trava():
                self._escrever_indice(entradas)
        return entradas

    # -- API pública -----------------------------------------------------
    def salvar_caso(self, caso: Caso, pdf_bytes: Optional[bytes] = None) -> None:
        caso.atualizado_em = datetime.now().isoformat()  # precisão total: serve de chave de cache
        self._escrever_atomico(
            self._caso_path(caso.numero_caso),
            json.dumps(caso.to_dict(), ensure_ascii=False, indent=2).encode("utf-8"))
        if pdf_bytes:
            self._escrever_atomico(self._pdf_path(caso.numero_caso), pdf_bytes)
        with self._trava():
            indice = [i for i in self._ler_indice() if i.get("numero_caso") != caso.numero_caso]
            entrada = self._entrada_indice(caso)
            # mantém a ordem "mais recente primeiro" pela data de criação
            indice.append(entrada)
            indice.sort(key=lambda e: e.get("criado_em", ""), reverse=True)
            self._escrever_indice(indice)

    def carregar_caso(self, numero_caso: str) -> Optional[Caso]:
        if not numero_caso_valido(numero_caso):
            return None
        path = self._caso_path(numero_caso)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return Caso.from_dict(json.load(f))

    def carregar_pdf(self, numero_caso: str) -> Optional[bytes]:
        if not numero_caso_valido(numero_caso):
            return None
        path = self._pdf_path(numero_caso)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            return f.read()

    def listar_indice(self) -> List[Dict[str, Any]]:
        """Todos os dossiês, do mais recente para o mais antigo."""
        return self._ler_indice()

    def buscar_por_numero(self, termo: str) -> List[Dict[str, Any]]:
        """Casos cujo número contém o trecho digitado (maiúsculas e minúsculas não importam)."""
        termo = (termo or "").strip().lower()
        if not termo:
            return []
        return [i for i in self._ler_indice() if termo in str(i.get("numero_caso", "")).lower()]
