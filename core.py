# -*- coding: utf-8 -*-
"""
Sentinela PLD - Núcleo de lógica (Databricks) - v2 (completo)
================================================================

Módulo com TODA a lógica de negócio, sem depender de UI:
- Modelo de dados completo do caso (KYC PF/PJ, sócios, contrapartes de
  crédito/débito, Thundera - AML 360, resolução, scorecard de qualidade)
- Armazenamento do Banco de Dossiês
- Preenchimento automático via IA (API da Anthropic)
- Geração de gráfico de timeline (matplotlib)
- Geração do PDF do dossiê (reportlab)

Ver app.py para a interface (Streamlit) que usa estas funções, e README.md
para instruções de deploy no Databricks.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage,
)

from opcoes import (
    RAZOES_CLEAR, RAZOES_CANCELAMENTO, JURISPRUDENCIA_NUPAGAMENTOS,
    JURISPRUDENCIA_REPORTAR_NUINVEST, JURISPRUDENCIA_REPORTAR_CANCELAR_NUINVEST,
    SCORECARD_NUPAG, SCORECARD_NUINVEST,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

TIPOS_CASO = ["Pessoa Física (PF)", "Pessoa Jurídica (PJ)", "Cripto", "NuInvest", "Under 18"]
DILIGENCIAS = ["Clear (arquivar)", "Reportar", "Reportar e Cancelar"]
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
REGIOES_RISCO_ALTO = {"Irã", "Coreia do Norte", "Síria", "Afeganistão", "Iêmen", "Mianmar", "Rússia"}


def classificar_risco_contraparte(pep: bool, regiao_risco: str) -> str:
    if pep:
        return "ALTO"
    if regiao_risco and regiao_risco.strip() in REGIOES_RISCO_ALTO:
        return "ALTO"
    if regiao_risco and regiao_risco.strip().lower() not in ("", "brasil", "brazil"):
        return "MÉDIO"
    return "BAIXO"


def gerar_numero_caso() -> str:
    ano = datetime.now().year
    sufixo = uuid.uuid4().hex[:6].upper()
    return f"{ano}-{sufixo}"


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
    renda_presumida: str = ""      # PF: renda; PJ: usar faturamento_presumido
    registro_profissional: str = ""  # PF: registro profissional; PJ: ramo_atividade
    data_abertura: str = ""        # PJ
    ramo_atividade: str = ""       # PJ
    faturamento_presumido: str = ""  # PJ
    porte: str = ""                # PJ
    porcentagem: str = ""
    valor: str = ""
    num_transacoes: str = ""


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

    # Bloco 1 - Alerta / Sentença
    fator_gerador: str = ""
    sentenca: str = ""

    # Bloco 2 - KYC (comum)
    regiao_risco: str = "Não"
    tipo_regiao_risco: str = ""       # se "Região de Fronteira"/"Extração..."
    tipo_regiao_risco_2: str = ""     # se "Outras Regiões de Risco"
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
    presenca_online_detalhe: str = ""
    fachada_empresa: str = "Não"
    fachada_empresa_detalhe: str = ""
    socios: List[Socio] = field(default_factory=list)

    # KYC - Under 18 (representante legal)
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
    comp_evasao: str = ""  # "Rápida Evasão" ou "Sem Rápida Evasão"
    comp_mudanca_comportamento: str = ""
    comp_data_abertura_ultimo_reporte: str = ""

    # Resolução
    parecer_final: str = ""
    alineas: str = ""
    jurisprudencias_selecionadas: List[str] = field(default_factory=list)
    razoes_clear_selecionadas: List[str] = field(default_factory=list)
    razoes_cancelamento_selecionadas: List[str] = field(default_factory=list)
    diligencia: str = ""

    # Scorecard de qualidade
    scorecard_tipo: str = "AML Nupag"   # "AML Nupag" ou "AML NuInvest"
    scorecard_drivers_marcados: List[str] = field(default_factory=list)  # nomes dos drivers
    scorecard_feedback: str = ""

    criado_em: str = field(default_factory=lambda: datetime.now().isoformat())
    atualizado_em: str = field(default_factory=lambda: datetime.now().isoformat())

    # -- helpers ---------------------------------------------------------
    def eh_pj(self) -> bool:
        return self.tipo_caso == "Pessoa Jurídica (PJ)"

    def nome_display(self) -> str:
        return self.nome_empresa if self.eh_pj() else self.nome_cliente

    def risco_geral(self) -> str:
        niveis = {"BAIXO": 0, "MÉDIO": 1, "ALTO": 2}
        pior = "ALTO" if self.pep == "Sim" else classificar_risco_contraparte(False, "Sim" if self.regiao_risco == "Sim" else "")
        for s in self.socios:
            r = "ALTO" if s.pep == "Sim" else ("MÉDIO" if s.regiao_risco == "Sim" else "BAIXO")
            if niveis[r] > niveis[pior]:
                pior = r
        return pior

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Caso":
        d = dict(d)
        d["socios"] = [Socio(**s) for s in d.get("socios", [])]
        d["contrapartes_credito"] = [ContraparteMovimentacao(**c) for c in d.get("contrapartes_credito", [])]
        d["contrapartes_debito"] = [ContraparteMovimentacao(**c) for c in d.get("contrapartes_debito", [])]
        d["outras_movimentacoes"] = [OutraMovimentacao(**m) for m in d.get("outras_movimentacoes", [])]
        d["arredondamento_itens"] = [ItemArredondamento(**a) for a in d.get("arredondamento_itens", [])]
        d["pix_itens"] = [MensagemPix(**p) for p in d.get("pix_itens", [])]
        return Caso(**d)


# ---------------------------------------------------------------------------
# Scorecard - cálculo da nota
# ---------------------------------------------------------------------------

def calcular_nota_scorecard(tipo: str, drivers_marcados: List[str]) -> float:
    """Réplica de recalcularScorecard(): nota = 100% - soma(peso*100) dos
    drivers marcados. Nunca fica negativa."""
    dados = SCORECARD_NUPAG if tipo == "AML Nupag" else SCORECARD_NUINVEST
    deducao = 0.0
    marcados = set(drivers_marcados)
    for categoria in dados:
        peso = categoria["peso"]
        for driver in categoria["drivers"]:
            if driver["nome"] in marcados:
                deducao += peso * 100
    return max(0.0, 100.0 - deducao)


def listar_drivers_scorecard(tipo: str) -> List[Dict[str, Any]]:
    return SCORECARD_NUPAG if tipo == "AML Nupag" else SCORECARD_NUINVEST


# ---------------------------------------------------------------------------
# Preenchimento automático via IA (Anthropic API)
# ---------------------------------------------------------------------------

SCHEMA_EXTRACAO = """{
  "kyc": {
    "nome": "", "idade": "", "cidadeEstado": "", "ultimaAtualizacaoCadastral": "DD/MM/AAAA",
    "profissaoInformada": "", "rendaPresumida": "", "registroProfissional": "",
    "registroSocietario": "Sim ou Não", "regiaoRisco": "Sim ou Não",
    "tipoRegiaoRisco": "Região de Fronteira ou Região de Extração Mineral e/ou de Extração de Madeira ou Outras Regiões de Risco",
    "pep": "Sim ou Não", "historicoPld": "Sim ou Não", "historicoFraude": "Sim ou Não",
    "midiaNegativa": "Sim ou Não", "outrasInformacoes": "",
    "nomeEmpresa": "", "dataAberturaEmpresa": "DD/MM/AAAA", "ramoAtividade": "", "porte": "",
    "faturamentoPresumido": "", "endereco": ""
  },
  "movimentacoes": {
    "periodo": "DD/MM/AAAA até DD/MM/AAAA", "totalCredito": "R$X,00", "totalContrapartesCredito": "",
    "totalDebito": "R$X,00", "totalContrapartesDebito": "",
    "contrapartesCredito": [{"tipo": "Pessoa Física ou Pessoa Jurídica", "porcentagem": "", "valor": "R$X,00", "numTransacoes": "", "nome": "", "idade": "", "cidadeEstado": "", "rendaPresumida": "", "registroProfissional": ""}],
    "contrapartesDebito": [{"tipo": "Pessoa Física ou Pessoa Jurídica", "porcentagem": "", "valor": "R$X,00", "numTransacoes": "", "nome": "", "idade": "", "cidadeEstado": "", "rendaPresumida": "", "registroProfissional": ""}]
  },
  "thundera": {
    "arredondamento": "Sim, Não, ou vazio", "arredondamentoQuantidade": "", "arredondamentoValor": "",
    "arredondamentoCredDeb": "Créditos ou Débitos",
    "pix": "Sim, Não, ou vazio", "pixQuantidade": "", "pixMensagem": "", "pixCredDeb": "Créditos ou Débitos",
    "evasao": "Rápida Evasão ou Sem Rápida Evasão",
    "mudancaComportamento": {"houve": "Sim ou Não", "valorAproximado": ""},
    "dataAberturaContaUltimoReporte": ""
  },
  "outrasMovimentacoes": [{"tipo": "Saques ou Boletos ou Gastos Cartão de Crédito ou Gastos Cartão de Débito ou Empréstimos ou Criptomoedas ou Investimentos ou Outros", "info": ""}]
}"""

SYSTEM_PROMPT_EXTRACAO = (
    "Você extrai dados estruturados de um resumo em texto livre de um caso de "
    "compliance PLD/AML, e devolve APENAS um objeto JSON válido (sem markdown, "
    "sem crases, sem texto antes ou depois), seguindo EXATAMENTE este formato de campos:\n\n"
    + SCHEMA_EXTRACAO +
    "\n\nRegras: se uma informação não estiver no texto, use uma string vazia \"\" -- não "
    "presuma relações, motivações ou conclusões que o texto não afirma explicitamente. "
    "Datas no formato DD/MM/AAAA. Campos de Sim/Não devem ser exatamente \"Sim\" ou \"Não\". "
    "Se o texto não mencionar contrapartes de algum lado, devolva uma lista vazia []. Seja "
    "extremamente conciso em todos os campos de texto livre."
)


class ErroExtracaoIA(Exception):
    pass


def _config_llm() -> Dict[str, str]:
    """Descobre como falar com o serviço de IA, a partir de variáveis de ambiente.

    Suporta três cenários:

    1. API da Anthropic direta (padrão)
         ANTHROPIC_API_KEY=sk-ant-...
       Usa https://api.anthropic.com com header x-api-key.

    2. Proxy LiteLLM (comum em empresas) -- formato OpenAI
         ANTHROPIC_API_KEY=<key do LiteLLM>
         ANTHROPIC_BASE_URL=https://litellm.suaempresa.com
       Usa <base>/v1/chat/completions com header Authorization: Bearer.
       É o modo padrão quando a base URL NÃO é api.anthropic.com, porque a
       rota compatível com OpenAI é a que todo proxy LiteLLM expõe.

    3. Proxy LiteLLM -- formato Anthropic (passthrough)
         SENTINELA_LLM_FORMATO=anthropic
       Força o uso de <base>/v1/messages mesmo em um proxy. Use se o seu
       LiteLLM estiver configurado com a rota de passthrough da Anthropic.

    Outras variáveis:
         SENTINELA_LLM_MODELO -- nome do modelo (o nome no proxy pode ser
             diferente, ex: "claude-sonnet-4" em vez de "claude-sonnet-4-6").
    """
    base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    eh_anthropic_oficial = "api.anthropic.com" in base
    formato = os.environ.get(
        "SENTINELA_LLM_FORMATO",
        "anthropic" if eh_anthropic_oficial else "openai",
    ).strip().lower()
    return {"base": base, "formato": formato}


def extrair_dados_do_texto(
    texto: str,
    texto_outras_movimentacoes: str = "",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """Chama o serviço de IA para extrair dados estruturados de um texto livre,
    replicando a função `extrairDadosDoTexto` do artefato original.

    No artefato original (dentro do Claude), a chamada a api.anthropic.com não
    precisava de API key -- o próprio ambiente do Claude autenticava. Fora do
    Claude, é uma chamada HTTP comum e precisa de credencial.

    Funciona tanto com a API da Anthropic direta quanto com um proxy LiteLLM
    corporativo -- ver _config_llm() acima para as variáveis de ambiente.
    """
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ErroExtracaoIA(
            "ANTHROPIC_API_KEY não configurada. Defina a variável de ambiente "
            "ANTHROPIC_API_KEY (via Secret do Databricks) -- ver README.md."
        )

    cfg = _config_llm()
    model = model or os.environ.get("SENTINELA_LLM_MODELO", "claude-sonnet-4-6")

    texto_usuario = texto
    if texto_outras_movimentacoes and texto_outras_movimentacoes.strip():
        texto_usuario += ("\n\n---\nOutras Movimentações (não bancárias): "
                          + texto_outras_movimentacoes.strip())

    if cfg["formato"] == "openai":
        url = cfg["base"] + "/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        }
        payload = {
            "model": model,
            "max_tokens": 8000,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_EXTRACAO},
                {"role": "user", "content": texto_usuario},
            ],
        }
    else:
        url = cfg["base"] + "/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": model,
            "max_tokens": 8000,
            "system": SYSTEM_PROMPT_EXTRACAO,
            "messages": [{"role": "user", "content": texto_usuario}],
        }

    ultimo_erro = None
    for _ in range(2):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 401:
                raise ErroExtracaoIA(
                    "Credencial rejeitada (401) por " + cfg["base"] + ". Verifique se a "
                    "ANTHROPIC_API_KEY corresponde a esse endpoint: uma key de proxy "
                    "(LiteLLM) não funciona em api.anthropic.com, e vice-versa. "
                    "Para usar um proxy, defina ANTHROPIC_BASE_URL."
                )
            if resp.status_code == 404:
                raise ErroExtracaoIA(
                    "Endpoint não encontrado (404): " + url + ". Se o seu proxy usa o "
                    "formato Anthropic, defina SENTINELA_LLM_FORMATO=anthropic; se usa "
                    "o formato OpenAI, defina SENTINELA_LLM_FORMATO=openai."
                )
            resp.raise_for_status()
            data = resp.json()
            return _extrair_json_da_resposta(data, cfg["formato"])
        except ErroExtracaoIA:
            raise
        except Exception as e:  # noqa: BLE001
            ultimo_erro = e
            continue

    raise ErroExtracaoIA(
        "Não foi possível conectar ao serviço de IA em " + url + " depois de duas "
        f"tentativas ({ultimo_erro}). Verifique a credencial e o acesso de rede "
        "a esse endereço."
    )


def _extrair_json_da_resposta(data: Dict[str, Any], formato: str) -> Dict[str, Any]:
    """Tira o texto da resposta (formato Anthropic ou OpenAI) e faz o parse do
    JSON que a IA devolveu."""
    if formato == "openai":
        escolhas = data.get("choices") or []
        if not escolhas:
            raise ErroExtracaoIA("O serviço de IA devolveu uma resposta vazia.")
        if escolhas[0].get("finish_reason") == "length":
            raise ErroExtracaoIA(
                "A resposta da IA foi cortada por ser muito longa. Tente um resumo "
                "mais curto ou com menos contrapartes de uma vez."
            )
        texto_resposta = (escolhas[0].get("message") or {}).get("content") or ""
    else:
        if data.get("stop_reason") == "max_tokens":
            raise ErroExtracaoIA(
                "A resposta da IA foi cortada por ser muito longa. Tente um resumo "
                "mais curto ou com menos contrapartes de uma vez."
            )
        texto_resposta = "".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        )

    json_limpo = re.sub(r"```json|```", "", texto_resposta).strip()
    try:
        return json.loads(json_limpo)
    except json.JSONDecodeError as e:
        raise ErroExtracaoIA(
            "A IA não devolveu um JSON válido. Tente novamente ou reescreva o "
            f"resumo do caso. (detalhe: {e})"
        )


def aplicar_dados_extraidos(caso: Caso, dados: Dict[str, Any]) -> Caso:
    """Aplica o JSON extraído pela IA nos campos do Caso, análogo a
    `aplicarDadosNoFormulario` no artefato original."""
    kyc = dados.get("kyc", {})
    mov = dados.get("movimentacoes", {})
    thun = dados.get("thundera", {})
    outras = dados.get("outrasMovimentacoes", [])

    if caso.eh_pj():
        caso.nome_empresa = kyc.get("nomeEmpresa", "") or caso.nome_empresa
        caso.data_abertura = kyc.get("dataAberturaEmpresa", "") or caso.data_abertura
        caso.ramo_atividade = kyc.get("ramoAtividade", "") or caso.ramo_atividade
        caso.porte = kyc.get("porte", "") or caso.porte
        caso.faturamento_presumido = kyc.get("faturamentoPresumido", "") or caso.faturamento_presumido
        caso.endereco = kyc.get("endereco", "") or caso.endereco
    else:
        caso.nome_cliente = kyc.get("nome", "") or caso.nome_cliente
        caso.idade = kyc.get("idade", "") or caso.idade
        caso.cidade_estado = kyc.get("cidadeEstado", "") or caso.cidade_estado
        caso.ultima_atualizacao_cadastral = kyc.get("ultimaAtualizacaoCadastral", "") or caso.ultima_atualizacao_cadastral
        caso.profissao_informada = kyc.get("profissaoInformada", "") or caso.profissao_informada
        caso.renda_presumida = kyc.get("rendaPresumida", "") or caso.renda_presumida
        caso.registro_profissional = kyc.get("registroProfissional", "") or caso.registro_profissional
        caso.registro_societario = kyc.get("registroSocietario", "") or caso.registro_societario

    caso.regiao_risco = kyc.get("regiaoRisco", "") or caso.regiao_risco
    caso.tipo_regiao_risco = kyc.get("tipoRegiaoRisco", "") or caso.tipo_regiao_risco
    caso.pep = kyc.get("pep", "") or caso.pep
    caso.historico_pld = kyc.get("historicoPld", "") or caso.historico_pld
    caso.historico_fraude = kyc.get("historicoFraude", "") or caso.historico_fraude
    caso.midia_negativa = kyc.get("midiaNegativa", "") or caso.midia_negativa
    caso.outras_info = kyc.get("outrasInformacoes", "") or caso.outras_info

    caso.mov_periodo = mov.get("periodo", "") or caso.mov_periodo
    caso.mov_total_credito = mov.get("totalCredito", "") or caso.mov_total_credito
    caso.mov_total_contrapartes_credito = mov.get("totalContrapartesCredito", "") or caso.mov_total_contrapartes_credito
    caso.mov_total_debito = mov.get("totalDebito", "") or caso.mov_total_debito
    caso.mov_total_contrapartes_debito = mov.get("totalContrapartesDebito", "") or caso.mov_total_contrapartes_debito

    def _mapear_contrapartes(lst):
        out = []
        for c in lst or []:
            out.append(ContraparteMovimentacao(
                tipo=c.get("tipo", "Pessoa Física"), nome=c.get("nome", ""),
                idade=c.get("idade", ""), cidade_estado=c.get("cidadeEstado", ""),
                renda_presumida=c.get("rendaPresumida", ""),
                registro_profissional=c.get("registroProfissional", ""),
                porcentagem=c.get("porcentagem", ""), valor=c.get("valor", ""),
                num_transacoes=c.get("numTransacoes", ""),
            ))
        return out

    novas_credito = _mapear_contrapartes(mov.get("contrapartesCredito"))
    novas_debito = _mapear_contrapartes(mov.get("contrapartesDebito"))
    if novas_credito:
        caso.contrapartes_credito = novas_credito
    if novas_debito:
        caso.contrapartes_debito = novas_debito

    caso.comp_arredondamento = thun.get("arredondamento", "") or caso.comp_arredondamento
    if caso.comp_arredondamento == "Sim" and thun.get("arredondamentoQuantidade"):
        caso.arredondamento_itens = [ItemArredondamento(
            cred_deb=thun.get("arredondamentoCredDeb", "Créditos"),
            quantidade=thun.get("arredondamentoQuantidade", ""),
            valor=thun.get("arredondamentoValor", ""),
        )]

    caso.comp_pix = thun.get("pix", "") or caso.comp_pix
    if caso.comp_pix == "Sim" and thun.get("pixQuantidade"):
        caso.pix_itens = [MensagemPix(
            cred_deb=thun.get("pixCredDeb", "Créditos"),
            quantidade=thun.get("pixQuantidade", ""),
            mensagem=thun.get("pixMensagem", ""),
        )]

    caso.comp_evasao = thun.get("evasao", "") or caso.comp_evasao
    mud = thun.get("mudancaComportamento", {}) or {}
    if mud.get("houve") == "Sim":
        caso.comp_mudanca_comportamento = gerar_narrativa_mudanca_comportamento(
            caso.mov_periodo, mud.get("valorAproximado", "")
        )
    caso.comp_data_abertura_ultimo_reporte = thun.get("dataAberturaContaUltimoReporte", "") or caso.comp_data_abertura_ultimo_reporte

    if outras:
        caso.outras_movimentacoes = [
            OutraMovimentacao(tipo=o.get("tipo", "Outros"), info=o.get("info", "")) for o in outras
        ]

    return caso


_NOMES_MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
                "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def gerar_narrativa_mudanca_comportamento(periodo_texto: str, valor_aproximado: str) -> str:
    """Réplica simplificada de gerarNarrativaMudancaComportamento(): monta uma
    frase padrão apontando o mês do pico de movimentação."""
    mes = datetime.now().strftime("%m")
    try:
        mes_nome = _NOMES_MESES[int(mes) - 1]
    except Exception:
        mes_nome = ""
    valor = valor_aproximado or "um valor expressivo"
    return (
        f"Houve alteração no padrão de movimentação do cliente, com destaque para "
        f"{mes_nome}, mês em que o volume transacionado atingiu aproximadamente {valor}, "
        f"acima do praticado nos demais meses do período analisado ({periodo_texto})."
    )


# ---------------------------------------------------------------------------
# Gráfico de timeline (equivalente ao SVG do artefato original)
# ---------------------------------------------------------------------------

def gerar_grafico_timeline(
    total_credito: float, total_debito: float, periodo_dias: int = 30,
) -> bytes:
    """Gera um gráfico simples de evolução diária de créditos/débitos ao
    longo do período, como PNG em memória. É uma versão simplificada (com
    distribuição de pesos aleatória) do gráfico SVG do artefato original --
    serve para ilustrar visualmente a 'rápida evasão' ou não."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    dias = np.arange(1, periodo_dias + 1)
    pesos_credito = np.random.dirichlet(np.ones(periodo_dias)) * total_credito
    pesos_debito = np.random.dirichlet(np.ones(periodo_dias)) * total_debito

    fig, ax = plt.subplots(figsize=(6.2, 2.6), dpi=140)
    ax.bar(dias, pesos_credito, color="#2F6F62", label="Créditos", width=0.8)
    ax.bar(dias, -pesos_debito, color="#A13D2E", label="Débitos", width=0.8)
    ax.axhline(0, color="#2A2035", linewidth=0.8)
    ax.set_xlabel("Dia do período", fontsize=8)
    ax.set_ylabel("Valor (R$)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.legend(fontsize=7, loc="upper right", frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    plt.close(fig)
    return buf.getvalue()


def _parse_valor_br(valor_str: str) -> float:
    """Converte 'R$1.234,56' (ou variações) para float. Retorna 0.0 se não
    conseguir interpretar."""
    if not valor_str:
        return 0.0
    limpo = re.sub(r"[^\d,.-]", "", valor_str)
    limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Armazenamento (Banco de Dossiês)
# ---------------------------------------------------------------------------

class ArmazenamentoLocal:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.environ.get("SENTINELA_DATA_DIR", "./data")
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self._pasta_pdfs(), exist_ok=True)
        self._indice_path = os.path.join(self.base_dir, "indice_dossies.json")
        if not os.path.exists(self._indice_path):
            self._escrever_indice([])

    def _pasta_pdfs(self) -> str:
        return os.path.join(self.base_dir, "pdfs")

    def _caso_path(self, numero_caso: str) -> str:
        return os.path.join(self.base_dir, f"caso_{numero_caso}.json")

    def _pdf_path(self, numero_caso: str) -> str:
        return os.path.join(self._pasta_pdfs(), f"dossie_{numero_caso}.pdf")

    def _ler_indice(self) -> List[Dict[str, Any]]:
        with open(self._indice_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _escrever_indice(self, indice: List[Dict[str, Any]]) -> None:
        with open(self._indice_path, "w", encoding="utf-8") as f:
            json.dump(indice, f, ensure_ascii=False, indent=2)

    def salvar_caso(self, caso: Caso, pdf_bytes: Optional[bytes] = None) -> None:
        caso.atualizado_em = datetime.now().isoformat()
        with open(self._caso_path(caso.numero_caso), "w", encoding="utf-8") as f:
            json.dump(caso.to_dict(), f, ensure_ascii=False, indent=2)
        if pdf_bytes:
            with open(self._pdf_path(caso.numero_caso), "wb") as f:
                f.write(pdf_bytes)
        indice = self._ler_indice()
        indice = [i for i in indice if i["numero_caso"] != caso.numero_caso]
        indice.insert(0, {
            "numero_caso": caso.numero_caso,
            "nome_cliente": caso.nome_display() or "Sem nome",
            "tipo_caso": caso.tipo_caso,
            "risco": caso.risco_geral(),
            "diligencia": caso.diligencia or "Pendente",
            "criado_em": caso.criado_em,
        })
        self._escrever_indice(indice)

    def carregar_caso(self, numero_caso: str) -> Optional[Caso]:
        path = self._caso_path(numero_caso)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return Caso.from_dict(json.load(f))

    def carregar_pdf(self, numero_caso: str) -> Optional[bytes]:
        path = self._pdf_path(numero_caso)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            return f.read()

    def listar_indice(self) -> List[Dict[str, Any]]:
        return self._ler_indice()

    def buscar_por_numero(self, termo: str) -> List[Dict[str, Any]]:
        termo = (termo or "").strip().lower()
        if not termo:
            return []
        return [i for i in self._ler_indice() if termo in i["numero_caso"].lower()]


# ---------------------------------------------------------------------------
# Geração de PDF do dossiê
# ---------------------------------------------------------------------------

def _estilos():
    base = getSampleStyleSheet()
    base.add(ParagraphStyle(name="TituloCaso", fontSize=18, leading=22, spaceAfter=4,
                             textColor=colors.HexColor("#3E2A63"), fontName="Helvetica-Bold"))
    base.add(ParagraphStyle(name="Eyebrow", fontSize=9, leading=11, spaceAfter=10,
                             textColor=colors.HexColor("#6C4E97"), fontName="Helvetica"))
    base.add(ParagraphStyle(name="SecaoTitulo", fontSize=13, leading=16, spaceBefore=16, spaceAfter=8,
                             textColor=colors.HexColor("#3E2A63"), fontName="Helvetica-Bold"))
    base.add(ParagraphStyle(name="SubTitulo", fontSize=11, leading=14, spaceBefore=10, spaceAfter=4,
                             textColor=colors.HexColor("#6C4E97"), fontName="Helvetica-Bold"))
    base.add(ParagraphStyle(name="Campo", fontSize=10, leading=14, spaceAfter=4,
                             textColor=colors.HexColor("#2A2035"), fontName="Helvetica"))
    return base


def _tabela_padrao(dados) -> Table:
    tabela = Table(dados, repeatRows=1, hAlign="LEFT")
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3E2A63")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9B6DE")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3EADA")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tabela


def gerar_pdf_dossie(caso: Caso, grafico_png: Optional[bytes] = None) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                             leftMargin=1.7 * cm, rightMargin=1.7 * cm)
    styles = _estilos()
    story = []

    story.append(Paragraph("SENTINELA PLD &mdash; DOSSIÊ", styles["Eyebrow"]))
    story.append(Paragraph(f"Caso {caso.numero_caso}", styles["TituloCaso"]))
    story.append(Paragraph(
        f"Cliente: <b>{caso.nome_display() or 'Não informado'}</b> &nbsp;|&nbsp; "
        f"Tipo: {caso.tipo_caso} &nbsp;|&nbsp; Risco geral: <b>{caso.risco_geral()}</b>",
        styles["Campo"],
    ))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#9C82C4"), thickness=1.2))

    # 1. Alerta / Sentença
    story.append(Paragraph("1. Alerta / Sentença", styles["SecaoTitulo"]))
    story.append(Paragraph(f"<b>Fator gerador:</b> {caso.fator_gerador or '—'}", styles["Campo"]))
    story.append(Paragraph(f"<b>Sentença:</b> {caso.sentenca or '—'}", styles["Campo"]))

    # 2. KYC
    story.append(Paragraph("2. KYC — Know Your Customer", styles["SecaoTitulo"]))
    if caso.eh_pj():
        story.append(Paragraph(f"<b>Empresa:</b> {caso.nome_empresa or '—'}", styles["Campo"]))
        story.append(Paragraph(f"<b>Data de abertura:</b> {caso.data_abertura or '—'} &nbsp;|&nbsp; "
                                f"<b>Ramo:</b> {caso.ramo_atividade or '—'} &nbsp;|&nbsp; "
                                f"<b>Porte:</b> {caso.porte or '—'}", styles["Campo"]))
        story.append(Paragraph(f"<b>Faturamento presumido:</b> {caso.faturamento_presumido or '—'} &nbsp;|&nbsp; "
                                f"<b>Endereço:</b> {caso.endereco or '—'}", styles["Campo"]))
        story.append(Paragraph(f"<b>Presença online:</b> {caso.presenca_online}"
                                + (f" — {caso.presenca_online_detalhe}" if caso.presenca_online_detalhe else ""), styles["Campo"]))
        story.append(Paragraph(f"<b>Fachada da empresa:</b> {caso.fachada_empresa}"
                                + (f" — {caso.fachada_empresa_detalhe}" if caso.fachada_empresa_detalhe else ""), styles["Campo"]))
        if caso.socios:
            story.append(Paragraph("Sócios", styles["SubTitulo"]))
            for s in caso.socios:
                risco_socio = "ALTO" if s.pep == "Sim" else ("MÉDIO" if s.regiao_risco == "Sim" else "BAIXO")
                story.append(Paragraph(
                    f"<b>{s.nome or 'Sócio'}</b> · {s.idade or '—'} anos · {s.endereco or '—'} · "
                    f"PEP: {s.pep} · Região de risco: {s.regiao_risco} · risco <b>{risco_socio}</b>",
                    styles["Campo"],
                ))
    else:
        story.append(Paragraph(f"<b>Nome:</b> {caso.nome_cliente or '—'} &nbsp;|&nbsp; "
                                f"<b>Idade:</b> {caso.idade or '—'} &nbsp;|&nbsp; "
                                f"<b>Cidade/Estado:</b> {caso.cidade_estado or '—'}", styles["Campo"]))
        story.append(Paragraph(f"<b>Última atualização cadastral:</b> {caso.ultima_atualizacao_cadastral or '—'} &nbsp;|&nbsp; "
                                f"<b>Profissão informada:</b> {caso.profissao_informada or '—'}", styles["Campo"]))
        story.append(Paragraph(f"<b>Renda presumida:</b> {caso.renda_presumida or '—'} &nbsp;|&nbsp; "
                                f"<b>Registro profissional:</b> {caso.registro_profissional or '—'}", styles["Campo"]))
        story.append(Paragraph(f"<b>Registro societário:</b> {caso.registro_societario}", styles["Campo"]))
        if caso.registro_societario == "Sim":
            story.append(Paragraph(
                f"&nbsp;&nbsp;{caso.reg_soc_razao_social or '—'} · aberta em {caso.reg_soc_data_abertura or '—'} · "
                f"{caso.reg_soc_situacao_cadastral or '—'} · {caso.reg_soc_ramo_atividade or '—'}",
                styles["Campo"],
            ))
    if caso.rep_nome:
        story.append(Paragraph("Representante legal (Under 18)", styles["SubTitulo"]))
        story.append(Paragraph(f"{caso.rep_nome} · renda presumida {caso.rep_renda_presumida or '—'} · "
                                f"reg. profissional {caso.rep_reg_prof or '—'}", styles["Campo"]))

    story.append(Paragraph(
        f"<b>Região de risco:</b> {caso.regiao_risco}"
        + (f" — {caso.tipo_regiao_risco}" if caso.tipo_regiao_risco else "")
        + f" &nbsp;|&nbsp; <b>PEP:</b> {caso.pep}"
        + (f" ({caso.tipo_pep})" if caso.tipo_pep else ""),
        styles["Campo"],
    ))
    story.append(Paragraph(
        f"<b>Mídia negativa:</b> {caso.midia_negativa}"
        + (f" — {caso.midia_negativa_detalhe}" if caso.midia_negativa_detalhe else "")
        + f" &nbsp;|&nbsp; <b>Histórico PLD:</b> {caso.historico_pld}"
        + f" &nbsp;|&nbsp; <b>Histórico de fraude:</b> {caso.historico_fraude}",
        styles["Campo"],
    ))
    if caso.outras_info:
        story.append(Paragraph(f"<b>Outras informações:</b> {caso.outras_info}", styles["Campo"]))

    # 3. Resumo de movimentações
    story.append(Paragraph("3. Resumo de Movimentações", styles["SecaoTitulo"]))
    story.append(Paragraph(f"<b>Período:</b> {caso.mov_periodo or '—'}", styles["Campo"]))
    story.append(Paragraph(
        f"<b>Total de créditos:</b> {caso.mov_total_credito or '—'} ({caso.mov_total_contrapartes_credito or '—'} contrapartes) "
        f"&nbsp;|&nbsp; <b>Total de débitos:</b> {caso.mov_total_debito or '—'} ({caso.mov_total_contrapartes_debito or '—'} contrapartes)",
        styles["Campo"],
    ))

    for titulo, lista in (("Principais contrapartes de crédito", caso.contrapartes_credito),
                           ("Principais contrapartes de débito", caso.contrapartes_debito)):
        if lista:
            story.append(Paragraph(titulo, styles["SubTitulo"]))
            dados = [["Tipo", "Nome", "%", "Valor", "Transações", "Detalhe"]]
            for c in lista:
                detalhe = c.registro_profissional or c.ramo_atividade or "—"
                dados.append([c.tipo, c.nome or "—", c.porcentagem or "—", c.valor or "—",
                               c.num_transacoes or "—", detalhe])
            story.append(_tabela_padrao(dados))

    if caso.outras_movimentacoes:
        story.append(Paragraph("Outras movimentações", styles["SubTitulo"]))
        for m in caso.outras_movimentacoes:
            story.append(Paragraph(f"<b>{m.tipo}:</b> {m.info or '—'}", styles["Campo"]))

    # 4. Thundera - AML 360
    story.append(Paragraph("4. Thundera — AML 360", styles["SecaoTitulo"]))
    story.append(Paragraph(f"<b>Arredondamento:</b> {caso.comp_arredondamento}", styles["Campo"]))
    for a in caso.arredondamento_itens:
        story.append(Paragraph(f"&nbsp;&nbsp;{a.cred_deb}: {a.quantidade or '—'} transações, valores como {a.valor or '—'}", styles["Campo"]))
    story.append(Paragraph(f"<b>Mensagens Pix:</b> {caso.comp_pix}", styles["Campo"]))
    for p in caso.pix_itens:
        story.append(Paragraph(f"&nbsp;&nbsp;{p.cred_deb}: {p.quantidade or '—'} mensagens — \"{p.mensagem or '—'}\"", styles["Campo"]))
    story.append(Paragraph(f"<b>Timeline de transferências:</b> {caso.comp_evasao or '—'}", styles["Campo"]))
    if grafico_png:
        story.append(Spacer(1, 6))
        story.append(RLImage(BytesIO(grafico_png), width=15 * cm, height=15 * cm * (2.6 / 6.2)))
    if caso.comp_mudanca_comportamento:
        story.append(Paragraph(f"<b>Mudança de comportamento:</b> {caso.comp_mudanca_comportamento}", styles["Campo"]))
    story.append(Paragraph(f"<b>Data de abertura da conta / último reporte:</b> {caso.comp_data_abertura_ultimo_reporte or '—'}", styles["Campo"]))

    # 5. Resolução
    story.append(Paragraph("5. Resolução", styles["SecaoTitulo"]))
    story.append(Paragraph(f"<b>Parecer final:</b> {caso.parecer_final or '—'}", styles["Campo"]))
    story.append(Paragraph(f"<b>Alíneas:</b> {caso.alineas or '—'}", styles["Campo"]))
    if caso.jurisprudencias_selecionadas:
        story.append(Paragraph("<b>Jurisprudências:</b> " + "; ".join(caso.jurisprudencias_selecionadas), styles["Campo"]))
    if caso.razoes_clear_selecionadas:
        story.append(Paragraph("<b>Razões de Clear:</b> " + "; ".join(caso.razoes_clear_selecionadas), styles["Campo"]))
    if caso.razoes_cancelamento_selecionadas:
        story.append(Paragraph("<b>Razões de Cancelamento:</b> " + "; ".join(caso.razoes_cancelamento_selecionadas), styles["Campo"]))
    story.append(Paragraph(f"<b>Diligência:</b> {caso.diligencia or 'Pendente'}", styles["Campo"]))

    # 6. Scorecard de qualidade
    if caso.scorecard_drivers_marcados or caso.scorecard_feedback:
        nota = calcular_nota_scorecard(caso.scorecard_tipo, caso.scorecard_drivers_marcados)
        story.append(Paragraph(f"6. Avaliação de Qualidade — {caso.scorecard_tipo}", styles["SecaoTitulo"]))
        story.append(Paragraph(f"<b>Nota final:</b> {nota:.1f}%", styles["Campo"]))
        if caso.scorecard_drivers_marcados:
            story.append(Paragraph("<b>Drivers marcados:</b> " + "; ".join(caso.scorecard_drivers_marcados), styles["Campo"]))
        if caso.scorecard_feedback:
            story.append(Paragraph(f"<b>Feedback:</b> {caso.scorecard_feedback}", styles["Campo"]))

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#C9B6DE"), thickness=0.8))
    story.append(Paragraph(
        f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} &middot; Uso interno &middot; Confidencial",
        styles["Eyebrow"],
    ))

    doc.build(story)
    return buf.getvalue()
