# -*- coding: utf-8 -*-
"""
Sentinela PLD - Preenchimento automático por IA
===============================================

Lê o resumo em texto livre de um caso e devolve os dados estruturados que o
formulário precisa. Regras do manual (seções 6 e 7) codificadas aqui:

- Nome do alerta, data do alerta e sentença são SEMPRE do analista: a IA nunca
  os recebe nem os preenche (não existem no schema).
- "Outras movimentações (não bancárias)" é a única fonte da seção de mesmo
  nome; o que está no resumo principal não vai para ela.
- A IA preenche só o que o texto afirma, salvo quando o texto autoriza inventar
  ("aleatório", "invente", "à sua escolha"): aí cria valores plausíveis,
  respeitando as restrições dadas. O código calcula essa autorização e a
  escreve na mensagem (INVENÇÃO AUTORIZADA: SIM/NÃO).
- Profissão informada (declarada pelo cliente) x Registro profissional
  (constatação do analista): na dúvida, vai para o registro profissional.
- Muitas contrapartes: total como número e só 3 a 5 principais descritas.
- Percentuais e valores coerentes com os totais; sem menção a concentração,
  nenhuma contraparte passa de 50%.
- Termos vagos ("diversas", "muitas") viram números plausíveis, nunca palavras.
- Mudança de comportamento: a IA devolve só Sim/Não e o valor aproximado do
  pico; a narrativa é montada pelo Sentinela (core).

Configuração do endpoint (variáveis de ambiente): ver _config_llm().
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import requests

from core import (
    Caso, ContraparteMovimentacao, OutraMovimentacao, ItemArredondamento,
    MensagemPix, Socio, NEUTRO, TIPO_PJ, TIPO_UNDER18, TIPOS_REGIAO_RISCO_1,
    TIPOS_PEP, TIPOS_OUTRAS_MOV, parse_valor_br, formatar_brl,
    normalizar_valor_texto, parse_periodo, periodo_padrao,
    gerar_narrativa_mudanca_comportamento, inferir_genero,
    gerar_narrativa_mudanca_mensal, pico_mudanca_sugerido, parse_data_br, somar_meses,
)


class ErroExtracaoIA(Exception):
    pass


# ---------------------------------------------------------------------------
# Prompts (dois modelos de resposta: PJ e os demais tipos)
# ---------------------------------------------------------------------------

_MINI_KYC = ('"registroSocietario": "Sim ou Não", "registroSocietarioDetalhe": "razão social, data de abertura, '
             'situação cadastral e ramo", "regiaoRisco": "Sim ou Não", "regiaoRiscoDetalhe": "cidade/estado e risco", '
             '"pep": "Sim ou Não", "pepDetalhe": "tipo de PEP, descrição e carência", "historicoPld": "Sim ou Não", '
             '"historicoPldDetalhe": "", "historicoFraude": "Sim ou Não", "historicoFraudeDetalhe": "", '
             '"midiaNegativa": "Sim ou Não", "midiaNegativaDetalhe": "link (se houver), data e fonte"')

_CONTRAPARTE_PF = ('{"tipo": "Pessoa Física", "porcentagem": "14%", "valor": "R$70.000,00", "numTransacoes": "23", '
                   '"nome": "", "idade": "", "cidadeEstado": "", "rendaPresumida": "R$X,00", '
                   '"registroProfissional": "", ' + _MINI_KYC + '}')
_CONTRAPARTE_PJ = ('{"tipo": "Pessoa Jurídica", "porcentagem": "", "valor": "R$X,00", "numTransacoes": "", '
                   '"nome": "", "dataAbertura": "DD/MM/AAAA", "cidadeEstado": "", "faturamentoPresumido": "R$X,00", '
                   '"ramoAtividade": "", "porte": "", ' + _MINI_KYC + '}')

_BLOCO_MOVIMENTACOES = (
    '"movimentacoes": {\n'
    '    "periodo": "DD/MM/AAAA até DD/MM/AAAA", "totalCredito": "R$X,00", "totalContrapartesCredito": "número",\n'
    '    "totalDebito": "R$X,00", "totalContrapartesDebito": "número",\n'
    '    "contrapartesCredito": [' + _CONTRAPARTE_PF + ', ' + _CONTRAPARTE_PJ + '],\n'
    '    "contrapartesDebito": [' + _CONTRAPARTE_PF + ']\n'
    '  },\n'
    '  "thundera": {\n'
    '    "arredondamento": "Sim, Não ou vazio",\n'
    '    "arredondamentoItens": [{"credDeb": "Créditos ou Débitos", "quantidade": "84", "valor": "R$1.000,00"}],\n'
    '    "pix": "Sim, Não ou vazio",\n'
    '    "pixItens": [{"credDeb": "Créditos ou Débitos", "quantidade": "12", "mensagem": "exemplo de mensagem Pix"}],\n'
    '    "evasao": "Rápida Evasão ou Sem Rápida Evasão ou vazio",\n'
    '    "mudancaComportamento": {"houve": "Sim ou Não", "valorAproximado": "R$X,00"},\n'
    '    "dataAberturaContaUltimoReporte": "DD/MM/AAAA"\n'
    '  },\n'
    '  "outrasMovimentacoes": [{"tipo": "Saques ou Boletos ou Gastos Cartão de Crédito ou Gastos Cartão de Débito '
    'ou Empréstimos ou Criptomoedas ou Investimentos ou Outros", "info": ""}]\n'
)

SCHEMA_EXTRACAO_PF = (
    '{\n'
    '  "kyc": {\n'
    '    "nome": "", "idade": "", "cidadeEstado": "", "ultimaAtualizacaoCadastral": "DD/MM/AAAA",\n'
    '    "profissaoInformada": "", "rendaPresumida": "R$X,00", "registroProfissional": "",\n'
    '    "registroSocietario": "Sim ou Não",\n'
    '    "registroSocietarioDetalhes": {"razaoSocial": "", "dataAbertura": "DD/MM/AAAA", "situacaoCadastral": "", "ramoAtividade": ""},\n'
    '    "regiaoRisco": "Sim ou Não",\n'
    '    "tipoRegiaoRisco": "Região de Fronteira ou Região de Extração Mineral e/ou de Extração de Madeira ou Outras Regiões de Risco",\n    "descricaoRegiaoRisco": "nome da região, só se for Outras Regiões de Risco",\n'
    '    "pep": "Sim ou Não", "tipoPep": "PEP Titular ou PEP Relacionado", "descricaoPep": "",\n'
    '    "historicoPld": "Sim ou Não", "historicoPldDetalhe": "",\n'
    '    "historicoFraude": "Sim ou Não", "historicoFraudeDetalhe": "",\n'
    '    "midiaNegativa": "Sim ou Não", "midiaNegativaDetalhe": "",\n'
    '    "outrasInformacoes": "",\n'
    '    "responsavelLegal": {"nome": "", "rendaPresumida": "R$X,00", "registroProfissional": "", '
    '"registroSocietario": "", "historicoPld": "", "historicoFraude": ""}\n'
    '  },\n  '
    + _BLOCO_MOVIMENTACOES +
    '}'
)

SCHEMA_EXTRACAO_PJ = (
    '{\n'
    '  "kyc": {\n'
    '    "nomeEmpresa": "", "dataAbertura": "DD/MM/AAAA", "ramoAtividade": "", "porte": "",\n'
    '    "faturamentoPresumido": "R$X,00", "endereco": "",\n'
    '    "presencaOnline": "Sim ou Não", "fachadaEmpresa": "Sim ou Não",\n'
    '    "regiaoRisco": "Sim ou Não",\n'
    '    "tipoRegiaoRisco": "Região de Fronteira ou Região de Extração Mineral e/ou de Extração de Madeira ou Outras Regiões de Risco",\n    "descricaoRegiaoRisco": "nome da região, só se for Outras Regiões de Risco",\n'
    '    "pep": "Sim ou Não", "historicoPld": "Sim ou Não", "historicoFraude": "Sim ou Não",\n'
    '    "midiaNegativa": "Sim ou Não", "outrasInformacoes": "",\n'
    '    "socios": [{"nome": "", "idade": "", "endereco": "", "rendaPresumida": "R$X,00", "patrimonio": "R$X,00", '
    '"regiaoRisco": "Sim ou Não", "tipoRegiaoRisco": "Região de Fronteira ou Região de Extração Mineral e/ou de Extração de Madeira ou Outras Regiões de Risco", '
    '"pep": "Sim ou Não", "tipoPep": "PEP Titular ou PEP Relacionado", "descricaoPep": "cargo e carência", '
    '"historicoPld": "Sim ou Não", "historicoPldDetalhe": "", "historicoFraude": "Sim ou Não", '
    '"historicoFraudeDetalhe": "", "midiaNegativa": "Sim ou Não", "midiaNegativaDetalhe": "link (se houver), data e fonte"}]\n'
    '  },\n  '
    + _BLOCO_MOVIMENTACOES +
    '}'
)

_REGRAS = """
REGRAS (siga todas):
1. Preencha SOMENTE o que o texto afirma. Se uma informação não está no texto, use "" (ou [] para listas); não presuma relações, motivações nem conclusões. EXCEÇÃO: se a primeira linha da mensagem do usuário for "INVENÇÃO AUTORIZADA: SIM" (o texto pediu algo como "aleatório", "invente" ou "à sua escolha"), crie valores plausíveis para o que faltar, respeitando as restrições dadas (ex.: "renda baixa", "sem vínculo aparente"). Com "INVENÇÃO AUTORIZADA: NÃO", nunca invente.
2. Distinga Profissão informada (o que o CLIENTE declarou) de Registro profissional (constatação do ANALISTA sobre a ocupação real). Na dúvida, coloque no registroProfissional.
3. Muitas contrapartes: informe o total como NÚMERO em totalContrapartesCredito/totalContrapartesDebito e descreva apenas as 3 a 5 principais em cada lista. O restante é calculado pelo dossiê; não crie contrapartes "demais".
4. Mantenha percentuais e valores coerentes com os totais (valor = porcentagem x total do lado). Sem menção a concentração no texto, NENHUMA contraparte passa de 50% do total; com concentração mencionada, a principal fica acima de 50%. A soma das porcentagens listadas nunca passa de 100%.
5. Termos vagos como "diversas", "várias" ou "muitas" viram números plausíveis (ex.: "diversas contrapartes" -> "12"), nunca palavras.
6. Mudança de comportamento: devolva só {"houve": "Sim" ou "Não", "valorAproximado": "R$X,00"} (valor aproximado do pico). Não escreva narrativa.
7. Datas no formato DD/MM/AAAA. Campos de Sim/Não devem ser exatamente "Sim" ou "Não". Valores monetários no formato R$1.234,56.
8. Arredondamento: uma linha em arredondamentoItens por valor de referência (R$1.000,00, R$2.000,00, R$5.000,00...), separando Créditos e Débitos. Pix: uma linha em pixItens por grupo de mensagens, com um exemplo da mensagem. Sem menção, deixe "" e [].
9. Cada contraparte traz o mini-KYC (registroSocietario, regiaoRisco, pep, historicoPld, historicoFraude, midiaNegativa): "Sim" ou "Não"; na falta de informação, "Não".
10. A seção outrasMovimentacoes (saques, boletos, cartões, empréstimos, criptomoedas, investimentos) vem EXCLUSIVAMENTE do bloco "OUTRAS MOVIMENTAÇÕES (NÃO BANCÁRIAS)" da mensagem. O que estiver no bloco "RESUMO DO CASO" não vai para essa seção; se o bloco de outras movimentações estiver vazio, devolva [].
11. Se não houver período no texto, deixe periodo "". Seja conciso nos campos de texto livre.
12. Com INVENÇÃO AUTORIZADA: SIM e pedido de contrapartes aleatórias, crie nomes, idades, cidades/estados, rendas e cargos plausíveis, OBEDECENDO ao perfil pedido. Ex.: "diversas pessoas físicas sem capacidade financeira elevada" -> rendaPresumida BAIXA e variada em cada contraparte (ex.: R$1.300,00 a R$3.500,00), coerente com o cargo. Se o texto não disser as profissões, crie cargos aleatórios compatíveis com o perfil (ex.: auxiliar administrativo, vendedor, atendente, motorista, diarista) em registroProfissional. Perfil de empresa (PJ): ramo, porte e faturamento compatíveis com o pedido. Nunca contrarie uma instrução dada.
13. KYC: registroSocietario = "Sim" só se o texto disser que o cliente tem registro societário; nesse caso preencha registroSocietarioDetalhes (razaoSocial, dataAbertura, situacaoCadastral, ramoAtividade) com o que o texto trouxer. Região de risco: se o texto indicar cidade/estado da região, coloque em cidadeEstado (PF); se o tipo for "Outras Regiões de Risco", descreva a região em descricaoRegiaoRisco. PEP: tipoPep e descricaoPep (cargo e carência). Mídia negativa, histórico de PLD e de fraude: detalhe (link, data e fonte, quando houver) em seus campos "...Detalhe". Nunca invente detalhes que o texto não traz (sem INVENÇÃO AUTORIZADA).
14. outrasInformacoes: coloque aqui TODA informação adicional de KYC que o texto trouxer e que não tenha campo próprio (compartilhamento de dispositivo, redes sociais, processos, dados específicos de NuInvest/Crypto e outras informações não convencionais), UMA INFORMAÇÃO POR LINHA, separadas por quebra de linha, no formato "Rótulo: valor". Não repita o que já tem campo próprio.
15. Contrapartes com sinais de KYC (sócia de empresa/registro societário, PEP, mídia negativa, histórico de PLD, histórico de fraude, região de risco): marque "Sim" no item de CADA contraparte envolvida e preencha o campo "...Detalhe" correspondente com o que o texto trouxer. Se o texto indicar MAIS DE UMA contraparte com o sinal (ex.: "3 contrapartes são PEP"), CRIE uma entrada por contraparte na lista (mesmo passando de 5 entradas), cada uma com o sinal marcado, mantendo valores e porcentagens coerentes com o total. Sem INVENÇÃO AUTORIZADA, deixe nome e demais dados dessas contrapartes em branco; com INVENÇÃO AUTORIZADA, crie-os respeitando a regra 12. Nunca invente os detalhes dos sinais.
16. Saída: APENAS um objeto JSON válido, sem markdown, sem crases e sem texto antes ou depois.
"""

_REGRAS_PJ = """
REGRAS ESPECÍFICAS DE PESSOA JURÍDICA:
- O titular do caso é uma EMPRESA: preencha nomeEmpresa, dataAbertura, ramoAtividade, porte, faturamentoPresumido e endereco. Presença online e fachada da empresa são só "Sim" ou "Não" (presencaOnline, fachadaEmpresa), sem detalhes; deixe "" se o texto não falar.
- Informações sobre os sócios vão em "socios" (nome, idade, endereco, rendaPresumida, patrimonio, regiaoRisco, tipoRegiaoRisco, pep, tipoPep, descricaoPep, historicoPld, historicoFraude, midiaNegativa e os campos "...Detalhe"). Marque "Sim" em cada sócio envolvido e preencha só os detalhes que o texto trouxer. Não crie sócios que o texto não cite, EXCETO quando o texto indicar mais de um sócio com um sinal (ex.: "2 sócios são PEP"): aí CRIE uma entrada por sócio, cada uma com o sinal marcado; sem INVENÇÃO AUTORIZADA deixe nome e demais dados em branco, com INVENÇÃO AUTORIZADA crie-os. Nunca invente os detalhes dos sinais.
- Não preencha campos de pessoa física do titular (nome, idade, renda).
"""

_REGRAS_PF = """
REGRAS ESPECÍFICAS DE PESSOA FÍSICA (inclui Cripto, NuInvest e Under 18):
- O titular é uma PESSOA: preencha nome, idade, cidadeEstado, ultimaAtualizacaoCadastral, profissaoInformada, rendaPresumida, registroProfissional e os campos de risco.
- "responsavelLegal" só deve ser preenchido se o texto falar do responsável legal de um menor de idade; caso contrário, deixe os campos "".
"""

SYSTEM_PROMPT_PF = (
    "Você extrai dados estruturados de um resumo em texto livre de um caso de compliance PLD/AML "
    "(pessoa física) e devolve APENAS um objeto JSON, seguindo EXATAMENTE este formato de campos:\n\n"
    + SCHEMA_EXTRACAO_PF + "\n" + _REGRAS + _REGRAS_PF
)

SYSTEM_PROMPT_PJ = (
    "Você extrai dados estruturados de um resumo em texto livre de um caso de compliance PLD/AML "
    "(pessoa jurídica) e devolve APENAS um objeto JSON, seguindo EXATAMENTE este formato de campos:\n\n"
    + SCHEMA_EXTRACAO_PJ + "\n" + _REGRAS + _REGRAS_PJ
)


def prompt_para_tipo(tipo_caso: str) -> str:
    return SYSTEM_PROMPT_PJ if tipo_caso == TIPO_PJ else SYSTEM_PROMPT_PF


# ---------------------------------------------------------------------------
# Invenção autorizada
# ---------------------------------------------------------------------------

def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


_RE_INVENCAO = re.compile(
    r"aleatori|\binvent|\bcrie\s+(?:os\s+|uns\s+)?(?:valores|dados|nomes)|\bgere\s+(?:os\s+|uns\s+)?(?:valores|dados|nomes)"
    r"|\b(?:a|na)\s+sua\s+escolha|\bsua\s+escolha\b|livre\s+escolha|escolha\s+livre"
)


def autoriza_invencao(texto: str) -> bool:
    """True se o texto autoriza a IA a criar valores ('aleatório', 'invente', 'à sua escolha'...)."""
    return bool(_RE_INVENCAO.search(_sem_acento(texto)))


_RE_MUDANCA = re.compile(r"(?:mudanca|mudou|alteracao|alterou)\s+(?:de\s+|o\s+|do\s+|no\s+)?(?:seu\s+)?comportament")


def menciona_mudanca_comportamento(texto: str) -> bool:
    """True se o texto diz que houve mudança de comportamento (aí o app pergunta os meses)."""
    return bool(_RE_MUDANCA.search(_sem_acento(texto)))


def validar_mudanca(data_conta: str, data_alerta: str, valor: str = "") -> Tuple[Dict[str, Any], List[str]]:
    """Valida as respostas sobre a mudança de comportamento. Devolve (dados, erros).

    A janela é sempre de 6 meses: o último é o mês do alerta (mês da mudança) e os 5
    anteriores vêm antes dele. A abertura da conta/último reporte tem de ser anterior
    à data do alerta."""
    erros: List[str] = []
    alerta = parse_data_br(data_alerta)
    conta = parse_data_br(data_conta)
    if not alerta:
        erros.append("Data do alerta válida (DD/MM/AAAA), usada para definir os 6 meses")
    if not conta:
        erros.append("Data de abertura da conta e/ou último reporte (use DD/MM/AAAA)")
    elif alerta and conta >= alerta:
        erros.append("A data de abertura/último reporte deve ser anterior à data do alerta")
    fim = date(alerta.year, alerta.month, 1) if alerta else None
    return {"inicio": somar_meses(fim, -5) if fim else None, "fim": fim, "mes_mudanca": fim,
            "data_conta": (data_conta or "").strip(), "valor": (valor or "").strip()}, erros


def _menciona_concentracao(texto: str) -> bool:
    return "concentra" in _sem_acento(texto)


# ---------------------------------------------------------------------------
# Chamada ao serviço de IA
# ---------------------------------------------------------------------------

def _config_llm() -> Dict[str, str]:
    """Descobre como falar com o serviço de IA, a partir de variáveis de ambiente.

    1. API da Anthropic direta (padrão): ANTHROPIC_API_KEY=sk-ant-...
       Usa https://api.anthropic.com/v1/messages com header x-api-key.
    2. Proxy LiteLLM (formato OpenAI): ANTHROPIC_API_KEY=<key do LiteLLM> e
       ANTHROPIC_BASE_URL=https://litellm.suaempresa.com
       Usa <base>/v1/chat/completions com Authorization: Bearer. É o padrão
       quando a base NÃO é api.anthropic.com.
    3. Proxy LiteLLM (passthrough Anthropic): SENTINELA_LLM_FORMATO=anthropic
       força <base>/v1/messages mesmo em um proxy.

    SENTINELA_LLM_MODELO: nome do modelo (no proxy pode ser diferente, ex.
    "anthropic/claude-sonnet-4-6").
    """
    base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    eh_anthropic_oficial = "api.anthropic.com" in base
    formato = os.environ.get(
        "SENTINELA_LLM_FORMATO", "anthropic" if eh_anthropic_oficial else "openai",
    ).strip().lower()
    return {"base": base, "formato": formato}


def montar_mensagem_usuario(texto: str, texto_outras_movimentacoes: str = "") -> str:
    """Mensagem enviada à IA: linha de autorização de invenção + dois blocos rotulados
    e separados (resumo principal e outras movimentações não bancárias)."""
    outras = (texto_outras_movimentacoes or "").strip()
    invencao = autoriza_invencao(texto) or autoriza_invencao(outras)
    return (
        f"INVENÇÃO AUTORIZADA: {'SIM' if invencao else 'NÃO'}\n\n"
        "### RESUMO DO CASO\n" + (texto or "").strip() + "\n\n"
        "### OUTRAS MOVIMENTAÇÕES (NÃO BANCÁRIAS)\n" + (outras or "(vazio)")
    )


def extrair_dados_do_texto(
    texto: str,
    texto_outras_movimentacoes: str = "",
    tipo_caso: str = "Pessoa Física (PF)",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """Chama o serviço de IA e devolve o JSON extraído do texto (dict).

    A IA nunca recebe nome do alerta, data do alerta nem sentença. A seção
    outrasMovimentacoes só é aproveitada se o campo próprio foi preenchido."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ErroExtracaoIA(
            "ANTHROPIC_API_KEY não configurada. Defina a variável de ambiente "
            "ANTHROPIC_API_KEY (via Secret do Databricks) -- ver README.md."
        )
    cfg = _config_llm()
    model = model or os.environ.get("SENTINELA_LLM_MODELO", "claude-sonnet-4-6")
    system = prompt_para_tipo(tipo_caso)
    mensagem = montar_mensagem_usuario(texto, texto_outras_movimentacoes)

    if cfg["formato"] == "openai":
        url = cfg["base"] + "/v1/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + api_key}
        payload = {
            "model": model, "max_tokens": 8000,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": mensagem}],
        }
    else:
        url = cfg["base"] + "/v1/messages"
        headers = {"Content-Type": "application/json", "x-api-key": api_key,
                   "anthropic-version": "2023-06-01"}
        payload = {"model": model, "max_tokens": 8000, "system": system,
                   "messages": [{"role": "user", "content": mensagem}]}

    ultimo_erro: Optional[Exception] = None
    dados: Optional[Dict[str, Any]] = None
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
            dados = _extrair_json_da_resposta(resp.json(), cfg["formato"])
            break
        except ErroExtracaoIA:
            raise
        except Exception as e:  # noqa: BLE001
            ultimo_erro = e
    if dados is None:
        raise ErroExtracaoIA(
            "Não foi possível conectar ao serviço de IA em " + url + " depois de duas "
            f"tentativas ({ultimo_erro}). Verifique a credencial e o acesso de rede "
            "a esse endereço."
        )

    if not (texto_outras_movimentacoes or "").strip():
        dados["outrasMovimentacoes"] = []  # só o campo próprio alimenta essa seção
    return dados


def _extrair_json_da_resposta(data: Dict[str, Any], formato: str) -> Dict[str, Any]:
    """Tira o texto da resposta (formato Anthropic ou OpenAI) e faz o parse do JSON."""
    msg_cortada = ("A resposta da IA foi cortada por ser muito longa. Tente um resumo "
                   "mais curto ou com menos contrapartes de uma vez.")
    if formato == "openai":
        escolhas = data.get("choices") or []
        if not escolhas:
            raise ErroExtracaoIA("O serviço de IA devolveu uma resposta vazia.")
        if escolhas[0].get("finish_reason") == "length":
            raise ErroExtracaoIA(msg_cortada)
        texto_resposta = (escolhas[0].get("message") or {}).get("content") or ""
    else:
        if data.get("stop_reason") == "max_tokens":
            raise ErroExtracaoIA(msg_cortada)
        texto_resposta = "".join(b.get("text", "") for b in data.get("content", [])
                                 if b.get("type") == "text")

    limpo = re.sub(r"```(?:json)?", "", texto_resposta).strip()
    candidatos = [limpo]
    i, j = limpo.find("{"), limpo.rfind("}")
    if 0 <= i < j:
        candidatos.append(limpo[i:j + 1])
    for c in candidatos:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    raise ErroExtracaoIA(
        "A IA não devolveu um JSON válido. Tente novamente ou reescreva o resumo do caso.")


# ---------------------------------------------------------------------------
# Normalização dos valores devolvidos
# ---------------------------------------------------------------------------

def _pick(d: Any, *chaves: str) -> Any:
    if not isinstance(d, dict):
        return ""
    for k in chaves:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return ""


def _txt(v: Any) -> str:
    if v is None or isinstance(v, (dict, list)):
        return ""
    return str(v).strip()


def _simnao(v: Any) -> str:
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    s = _sem_acento(_txt(v))
    if s in ("sim", "s", "yes", "true", "1"):
        return "Sim"
    if s in ("nao", "n", "no", "false", "0"):
        return "Não"
    return ""


_RE_DINHEIRO = re.compile(r"^\s*(?:r\$)?\s*[\d.,]+\s*(?:mil|milh\w+)?\s*$", re.I)


def _dinheiro(v: Any) -> str:
    s = _txt(v)
    if not s:
        return ""
    return normalizar_valor_texto(s) if _RE_DINHEIRO.match(s) else s


def _numero(v: Any) -> str:
    """Contagem como texto: '63', 63, '63 contrapartes' -> '63'; palavras ficam como vieram
    (coerencia_extracao troca termos vagos por números)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(int(v))
    s = _txt(v)
    m = re.fullmatch(r"\D*(\d+)\D*", s)
    return m.group(1) if m else s


def _pct(v: Any) -> str:
    s = _txt(v)
    if not s:
        return ""
    if isinstance(v, (int, float)) or re.fullmatch(r"[\d.,]+", s):
        return _fmt_pct(parse_valor_br(s))
    return s


def _fmt_pct(x: float) -> str:
    if abs(x - round(x)) < 0.05:
        return f"{round(x)}%"
    return f"{x:.1f}%".replace(".", ",")


def _tipo_contraparte(v: Any) -> str:
    s = _sem_acento(_txt(v))
    return "Pessoa Jurídica" if s in ("pj", "pessoa juridica", "empresa", "juridica") or "jurid" in s else "Pessoa Física"


def _tipo_regiao(v: Any) -> str:
    s = _sem_acento(_txt(v))
    if not s:
        return ""
    if "fronteira" in s:
        return TIPOS_REGIAO_RISCO_1[0]
    if "extra" in s or "madeira" in s or "mineral" in s:
        return TIPOS_REGIAO_RISCO_1[1]
    return TIPOS_REGIAO_RISCO_1[2]


def _tipo_pep(v: Any) -> str:
    s = _sem_acento(_txt(v))
    if not s:
        return ""
    return TIPOS_PEP[1] if "relacion" in s else TIPOS_PEP[0]


def _tipo_credeb(v: Any) -> str:
    s = _sem_acento(_txt(v))
    return "Débitos" if s.startswith(("deb", "saida")) else "Créditos"


def _tipo_outra_mov(v: Any) -> str:
    s = _sem_acento(_txt(v))
    for t in TIPOS_OUTRAS_MOV:
        if _sem_acento(t) == s:
            return t
    if "saque" in s:
        return "Saques"
    if "boleto" in s:
        return "Boletos"
    if "credito" in s and "cartao" in s:
        return "Gastos Cartão de Crédito"
    if "debito" in s and "cartao" in s:
        return "Gastos Cartão de Débito"
    if "emprest" in s:
        return "Empréstimos"
    if "cripto" in s:
        return "Criptomoedas"
    if "invest" in s:
        return "Investimentos"
    return "Outros"


def _evasao(v: Any) -> str:
    s = _sem_acento(_txt(v))
    if not s:
        return ""
    if s.startswith("sem") or "nao" in s:
        return "Sem Rápida Evasão"
    if "evas" in s or "rapid" in s:
        return "Rápida Evasão"
    return ""


def _set(caso: Any, attr: str, valor: str) -> None:
    """Nunca sobrescreve um campo com vazio."""
    if valor not in (None, ""):
        setattr(caso, attr, valor)


def _mapear_contrapartes(lista: Any) -> List[ContraparteMovimentacao]:
    out: List[ContraparteMovimentacao] = []
    for c in (lista if isinstance(lista, list) else []):
        if not isinstance(c, dict):
            continue
        cp = ContraparteMovimentacao(
            tipo=_tipo_contraparte(c.get("tipo")),
            nome=_txt(c.get("nome")),
            idade=_numero(c.get("idade")),
            cidade_estado=_txt(_pick(c, "cidadeEstado", "cidade_estado")),
            renda_presumida=_dinheiro(c.get("rendaPresumida")),
            registro_profissional=_txt(c.get("registroProfissional")),
            data_abertura=_txt(_pick(c, "dataAbertura", "dataAberturaEmpresa")),
            ramo_atividade=_txt(c.get("ramoAtividade")),
            faturamento_presumido=_dinheiro(c.get("faturamentoPresumido")),
            porte=_txt(c.get("porte")),
            porcentagem=_pct(c.get("porcentagem")),
            valor=_dinheiro(c.get("valor")),
            num_transacoes=_numero(_pick(c, "numTransacoes", "numeroTransacoes")),
        )
        for campo, chave in (("registro_societario", "registroSocietario"), ("regiao_risco", "regiaoRisco"),
                             ("pep", "pep"), ("historico_pld", "historicoPld"),
                             ("historico_fraude", "historicoFraude"), ("midia_negativa", "midiaNegativa")):
            setattr(cp, campo, _simnao(c.get(chave)) or "Não")
            setattr(cp, campo + "_detalhe", _txt(c.get(chave + "Detalhe")))
        out.append(cp)
    return out


def _mapear_socios(lista: Any) -> List[Socio]:
    out: List[Socio] = []
    for s in (lista if isinstance(lista, list) else []):
        if not isinstance(s, dict):
            continue
        sinais = ("regiaoRisco", "pep", "historicoPld", "historicoFraude", "midiaNegativa")
        if not _txt(s.get("nome")) and not any(_simnao(s.get(k)) == "Sim" for k in sinais):
            continue  # sócio sem nome só entra se carregar algum sinal de KYC
        socio = Socio(
            nome=_txt(s.get("nome")), idade=_numero(s.get("idade")), endereco=_txt(s.get("endereco")),
            renda_presumida=_dinheiro(s.get("rendaPresumida")), patrimonio=_dinheiro(s.get("patrimonio")),
        )
        for campo, chave in (("regiao_risco", "regiaoRisco"), ("pep", "pep"), ("historico_pld", "historicoPld"),
                             ("historico_fraude", "historicoFraude"), ("midia_negativa", "midiaNegativa")):
            setattr(socio, campo, _simnao(s.get(chave)) or "Não")
        socio.tipo_regiao_risco = _tipo_regiao(s.get("tipoRegiaoRisco")) if socio.regiao_risco == "Sim" else ""
        socio.tipo_pep = _tipo_pep(s.get("tipoPep")) if socio.pep == "Sim" else ""
        socio.descricao_pep = _txt(s.get("descricaoPep"))
        for campo in ("historico_pld", "historico_fraude", "midia_negativa"):
            chave = {"historico_pld": "historicoPld", "historico_fraude": "historicoFraude",
                     "midia_negativa": "midiaNegativa"}[campo]
            setattr(socio, campo + "_detalhe", _txt(s.get(chave + "Detalhe")))
        out.append(socio)
    return out


def _mapear_itens(dados_thun: Dict[str, Any], chave_lista: str, classe: type, extras: Tuple[str, str],
                  chaves_antigas: Tuple[str, str, str, str]) -> list:
    """Lista de itens de arredondamento/Pix; aceita o formato antigo de item único."""
    itens = []
    lista = dados_thun.get(chave_lista)
    if isinstance(lista, list):
        for it in lista:
            if not isinstance(it, dict):
                continue
            qtd = _numero(it.get("quantidade"))
            if not qtd and not _txt(it.get(extras[1])):
                continue
            itens.append((_tipo_credeb(it.get("credDeb")), qtd,
                          _dinheiro(it.get(extras[1])) if extras[1] == "valor" else _txt(it.get(extras[1]))))
    elif _txt(dados_thun.get(chaves_antigas[0])):  # formato antigo
        itens.append((_tipo_credeb(dados_thun.get(chaves_antigas[3])), _numero(dados_thun.get(chaves_antigas[0])),
                      _dinheiro(dados_thun.get(chaves_antigas[1])) if extras[1] == "valor"
                      else _txt(dados_thun.get(chaves_antigas[2]))))
    return [classe(cred_deb=cd, quantidade=q, **{extras[1]: v}) for cd, q, v in itens]


# ---------------------------------------------------------------------------
# Aplicação no Caso
# ---------------------------------------------------------------------------

def aplicar_dados_extraidos(caso: Caso, dados: Dict[str, Any], hoje: Optional[date] = None) -> Caso:
    """Aplica o JSON da IA nos campos do Caso. Nunca sobrescreve um campo com vazio.
    Nome do alerta, data do alerta e sentença não são tocados."""
    dados = dados if isinstance(dados, dict) else {}
    kyc = dados.get("kyc") or {}
    mov = dados.get("movimentacoes") or {}
    thun = dados.get("thundera") or {}
    outras = dados.get("outrasMovimentacoes")

    # ---- KYC do titular -------------------------------------------------
    if caso.eh_pj():
        _set(caso, "nome_empresa", _txt(_pick(kyc, "nomeEmpresa", "nome")))
        _set(caso, "data_abertura", _txt(_pick(kyc, "dataAbertura", "dataAberturaEmpresa")))
        _set(caso, "ramo_atividade", _txt(_pick(kyc, "ramoAtividade", "ramo")))
        _set(caso, "porte", _txt(kyc.get("porte")))
        _set(caso, "faturamento_presumido", _dinheiro(_pick(kyc, "faturamentoPresumido", "faturamento")))
        _set(caso, "endereco", _txt(kyc.get("endereco")))
        _set(caso, "presenca_online", _simnao(kyc.get("presencaOnline")))
        _set(caso, "fachada_empresa", _simnao(kyc.get("fachadaEmpresa")))
        socios = _mapear_socios(kyc.get("socios"))
        if socios:
            caso.socios = socios
    else:
        _set(caso, "nome_cliente", _txt(kyc.get("nome")))
        _set(caso, "idade", _numero(kyc.get("idade")))
        _set(caso, "cidade_estado", _txt(kyc.get("cidadeEstado")))
        _set(caso, "ultima_atualizacao_cadastral", _txt(kyc.get("ultimaAtualizacaoCadastral")))
        _set(caso, "profissao_informada", _txt(kyc.get("profissaoInformada")))
        _set(caso, "renda_presumida", _dinheiro(kyc.get("rendaPresumida")))
        _set(caso, "registro_profissional", _txt(kyc.get("registroProfissional")))
        _set(caso, "registro_societario", _simnao(kyc.get("registroSocietario")))
        det = kyc.get("registroSocietarioDetalhes") or {}
        if isinstance(det, dict):
            _set(caso, "reg_soc_razao_social", _txt(det.get("razaoSocial")))
            _set(caso, "reg_soc_data_abertura", _txt(det.get("dataAbertura")))
            _set(caso, "reg_soc_situacao_cadastral", _txt(det.get("situacaoCadastral")))
            _set(caso, "reg_soc_ramo_atividade", _txt(det.get("ramoAtividade")))
        if caso.tipo_caso == TIPO_UNDER18 and isinstance(kyc.get("responsavelLegal"), dict):
            r = kyc["responsavelLegal"]
            _set(caso, "rep_nome", _txt(r.get("nome")))
            _set(caso, "rep_renda_presumida", _dinheiro(r.get("rendaPresumida")))
            _set(caso, "rep_reg_prof", _txt(r.get("registroProfissional")))
            _set(caso, "rep_reg_soc", _txt(r.get("registroSocietario")))
            _set(caso, "rep_hist_pld", _txt(r.get("historicoPld")))
            _set(caso, "rep_hist_fraude", _txt(r.get("historicoFraude")))
        if caso.nome_cliente and not caso.genero:
            _set(caso, "genero", inferir_genero(caso.nome_cliente) or "")

    # ---- Região, PEP e históricos (comuns) ---------------------------------
    _set(caso, "regiao_risco", _simnao(kyc.get("regiaoRisco")))
    if caso.regiao_risco == "Sim":
        _set(caso, "tipo_regiao_risco", _tipo_regiao(kyc.get("tipoRegiaoRisco")))
        _set(caso, "tipo_regiao_risco_2", _txt(kyc.get("descricaoRegiaoRisco")))
    _set(caso, "pep", _simnao(kyc.get("pep")))
    if caso.pep == "Sim":
        _set(caso, "tipo_pep", _tipo_pep(kyc.get("tipoPep")))
        _set(caso, "descricao_pep", _txt(kyc.get("descricaoPep")))
    for attr, chave in (("historico_pld", "historicoPld"), ("historico_fraude", "historicoFraude"),
                        ("midia_negativa", "midiaNegativa")):
        _set(caso, attr, _simnao(kyc.get(chave)))
        _set(caso, attr + "_detalhe", _txt(kyc.get(chave + "Detalhe")))
    outras_info = kyc.get("outrasInformacoes")
    if isinstance(outras_info, list):
        outras_info = "\n".join(_txt(x) for x in outras_info if _txt(x))
    _set(caso, "outras_info", _txt(outras_info))

    # ---- Bloco 3: movimentações ----------------------------------------------
    periodo = _txt(mov.get("periodo"))
    if periodo and parse_periodo(periodo):
        caso.mov_periodo = periodo
    elif not caso.mov_periodo:
        caso.mov_periodo = periodo_padrao(hoje)  # texto sem período válido
    _set(caso, "mov_total_credito", _dinheiro(mov.get("totalCredito")))
    _set(caso, "mov_total_contrapartes_credito", _numero(mov.get("totalContrapartesCredito")))
    _set(caso, "mov_total_debito", _dinheiro(mov.get("totalDebito")))
    _set(caso, "mov_total_contrapartes_debito", _numero(mov.get("totalContrapartesDebito")))
    novas_c = _mapear_contrapartes(mov.get("contrapartesCredito"))
    novas_d = _mapear_contrapartes(mov.get("contrapartesDebito"))
    if novas_c:
        caso.contrapartes_credito = novas_c
    if novas_d:
        caso.contrapartes_debito = novas_d

    # ---- Bloco 4: Thundera -------------------------------------------------------
    arred = _mapear_itens(thun, "arredondamentoItens", ItemArredondamento, ("cred_deb", "valor"),
                          ("arredondamentoQuantidade", "arredondamentoValor", "", "arredondamentoCredDeb"))
    pix = _mapear_itens(thun, "pixItens", MensagemPix, ("cred_deb", "mensagem"),
                        ("pixQuantidade", "", "pixMensagem", "pixCredDeb"))
    _set(caso, "comp_arredondamento", _simnao(thun.get("arredondamento")) or ("Sim" if arred else ""))
    if arred and caso.comp_arredondamento == "Sim":
        caso.arredondamento_itens = arred
    _set(caso, "comp_pix", _simnao(thun.get("pix")) or ("Sim" if pix else ""))
    if pix and caso.comp_pix == "Sim":
        caso.pix_itens = pix
    _set(caso, "comp_evasao", _evasao(thun.get("evasao")))
    mud = thun.get("mudancaComportamento")
    if isinstance(mud, dict) and _simnao(mud.get("houve")) == "Sim":
        caso.comp_mudanca_comportamento = gerar_narrativa_mudanca_comportamento(
            caso.mov_periodo, _txt(mud.get("valorAproximado")), hoje)
    _set(caso, "comp_data_abertura_ultimo_reporte", _txt(thun.get("dataAberturaContaUltimoReporte")))

    if isinstance(outras, list):
        itens = [OutraMovimentacao(tipo=_tipo_outra_mov(o.get("tipo")), info=_txt(o.get("info")))
                 for o in outras if isinstance(o, dict) and _txt(o.get("info"))]
        if itens:
            caso.outras_movimentacoes = itens
    return caso


# ---------------------------------------------------------------------------
# Coerência (correções determinísticas) e campos obrigatórios
# ---------------------------------------------------------------------------

def _tem_digito(s: str) -> bool:
    return bool(re.search(r"\d", s or ""))


def coerencia_extracao(caso: Caso, texto: str = "", invencao_autorizada: Optional[bool] = None) -> List[str]:
    """Ajusta percentuais, valores e totais de contrapartes e devolve avisos em português.

    `texto` (resumo + outras movimentações) serve para saber se houve autorização
    de invenção e menção a concentração."""
    avisos: List[str] = []
    invencao = autoriza_invencao(texto) if invencao_autorizada is None else invencao_autorizada
    concentracao = _menciona_concentracao(texto)

    for rotulo, lista, attr_total, attr_cont in (
        ("crédito", caso.contrapartes_credito, "mov_total_credito", "mov_total_contrapartes_credito"),
        ("débito", caso.contrapartes_debito, "mov_total_debito", "mov_total_contrapartes_debito"),
    ):
        total = parse_valor_br(getattr(caso, attr_total))
        # 1) preencher porcentagem ou valor que faltam
        for c in lista:
            pct_txt, val_txt = (c.porcentagem or "").strip(), (c.valor or "").strip()
            if total > 0:
                if pct_txt and not val_txt:
                    c.valor = formatar_brl(parse_valor_br(pct_txt) / 100.0 * total)
                elif val_txt and not pct_txt:
                    c.porcentagem = _fmt_pct(parse_valor_br(val_txt) / total * 100.0)
                elif pct_txt and val_txt:
                    esperado = parse_valor_br(pct_txt) / 100.0 * total
                    if esperado and abs(parse_valor_br(val_txt) - esperado) / esperado > 0.05:
                        avisos.append(
                            f"Contraparte de {rotulo} {c.nome or '(sem nome)'}: o valor {c.valor} não bate com "
                            f"{c.porcentagem} do total de {rotulo}s. Confira.")
        # 2) soma > 100%
        pcts = [parse_valor_br(c.porcentagem) for c in lista if (c.porcentagem or "").strip()]
        soma = sum(pcts)
        if soma > 100.0 + 1e-9:
            avisos.append(f"A soma das porcentagens das contrapartes de {rotulo} era {soma:.0f}% (acima de 100%); "
                          "os percentuais foram reescalados proporcionalmente.")
            fator = 100.0 / soma
            for c in lista:
                if (c.porcentagem or "").strip():
                    novo = parse_valor_br(c.porcentagem) * fator
                    c.porcentagem = _fmt_pct(novo)
                    if total > 0:
                        c.valor = formatar_brl(novo / 100.0 * total)
        # 3) total de contrapartes: número, nunca palavra
        valor_cont = (getattr(caso, attr_cont) or "").strip()
        if valor_cont and not _tem_digito(valor_cont):
            novo = max(len(lista) + 5, 8)
            setattr(caso, attr_cont, str(novo))
            avisos.append(f"O total de contrapartes de {rotulo} veio como \"{valor_cont}\"; "
                          f"foi trocado pelo número plausível {novo}. Confira.")
        elif valor_cont and lista and int(re.search(r"\d+", valor_cont).group()) < len(lista):
            novo = len(lista)
            setattr(caso, attr_cont, str(novo))
            avisos.append(f"O total de contrapartes de {rotulo} ({valor_cont}) era menor que o número de "
                          f"contrapartes descritas; foi ajustado para {novo}.")
        # 4) regra de concentração (só avisa)
        if not invencao and not concentracao:
            for c in lista:
                if parse_valor_br(c.porcentagem) > 50.0:
                    avisos.append(
                        f"A contraparte de {rotulo} {c.nome or '(sem nome)'} tem {c.porcentagem} do total, mas o "
                        "texto não menciona concentração. Confira o percentual.")
    return avisos


def completar_obrigatorios(caso: Caso, hoje: Optional[date] = None) -> Caso:
    """Completa com marcações neutras os campos obrigatórios que o texto não detalha,
    para não travar a geração. Não toca no nome do alerta, na data do alerta, na
    sentença nem no gênero (o app pergunta quando o nome é ambíguo)."""

    def _txt_neutro(attr: str) -> None:
        if not (getattr(caso, attr) or "").strip():
            setattr(caso, attr, NEUTRO)

    def _valor_neutro(attr: str) -> None:
        if not (getattr(caso, attr) or "").strip():
            setattr(caso, attr, "R$0,00")

    if caso.eh_pj():
        for attr in ("nome_empresa", "data_abertura", "ramo_atividade", "porte", "endereco"):
            _txt_neutro(attr)
        _valor_neutro("faturamento_presumido")
    else:
        for attr in ("nome_cliente", "idade", "cidade_estado", "ultima_atualizacao_cadastral",
                     "registro_profissional"):
            _txt_neutro(attr)
        _valor_neutro("renda_presumida")

    if caso.regiao_risco == "Sim" and not (caso.tipo_regiao_risco or "").strip():
        caso.tipo_regiao_risco = TIPOS_REGIAO_RISCO_1[2]
    if caso.pep == "Sim" and not (caso.tipo_pep or "").strip():
        caso.tipo_pep = TIPOS_PEP[0]
    for socio in caso.socios:
        if socio.regiao_risco == "Sim" and not (socio.tipo_regiao_risco or "").strip():
            socio.tipo_regiao_risco = TIPOS_REGIAO_RISCO_1[2]
        if socio.pep == "Sim" and not (socio.tipo_pep or "").strip():
            socio.tipo_pep = TIPOS_PEP[0]

    if not (caso.mov_periodo or "").strip() or not parse_periodo(caso.mov_periodo):
        caso.mov_periodo = periodo_padrao(hoje)
    _valor_neutro("mov_total_credito")
    _valor_neutro("mov_total_debito")
    if not (caso.mov_total_contrapartes_credito or "").strip():
        caso.mov_total_contrapartes_credito = str(len(caso.contrapartes_credito))
    if not (caso.mov_total_contrapartes_debito or "").strip():
        caso.mov_total_contrapartes_debito = str(len(caso.contrapartes_debito))
    return caso


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

# Perguntas de KYC do titular: (rótulo, dica). Só entram as que ficaram sem resposta.
_ROTULOS_KYC = {
    "reg_soc_razao_social": ("Razão social (registro societário)", ""),
    "reg_soc_data_abertura": ("Data de abertura (registro societário)", "DD/MM/AAAA"),
    "reg_soc_situacao_cadastral": ("Situação cadastral (registro societário)", "Ex: Ativa"),
    "reg_soc_ramo_atividade": ("Ramo de atividade (registro societário)", ""),
    "cidade_estado": ("Cidade/Estado da região de risco", "Ex: Foz do Iguaçu/PR"),
    "tipo_regiao_risco": ("Risco da região", ""),
    "tipo_regiao_risco_2": ("Qual região de risco?", ""),
    "tipo_pep": ("Tipo de PEP", ""),
    "descricao_pep": ("Descrição do PEP e carência", "Cargo, órgão e carência"),
    "midia_negativa_detalhe": ("Detalhes da mídia negativa", "Link (se houver), resumo, data e fonte"),
    "historico_pld_detalhe": ("Detalhes do histórico de PLD", ""),
    "historico_fraude_detalhe": ("Detalhes do histórico de fraude", ""),
}
OPCOES_KYC = {"tipo_regiao_risco": TIPOS_REGIAO_RISCO_1, "tipo_pep": TIPOS_PEP}

# Perguntas de KYC das contrapartes (Bloco 3): campo do Caso -> (rótulo, dica).
_SINAIS_CONTRAPARTE = {
    "registro_societario": ("Registro societário", "Razão social, data de abertura, situação cadastral e ramo"),
    "regiao_risco": ("Região de risco", "Cidade/Estado e risco da região"),
    "pep": ("PEP", "Tipo de PEP, descrição e carência"),
    "historico_pld": ("Histórico de PLD", "Detalhes"),
    "historico_fraude": ("Histórico de fraude", "Detalhes"),
    "midia_negativa": ("Mídia negativa", "Link (se houver), data e fonte"),
}
_LADOS = {"cred": ("crédito", "contrapartes_credito"), "deb": ("débito", "contrapartes_debito")}
_SEP = "__"  # chaves de contraparte: cp__<cred|deb>__<índice>__<campo>_detalhe


def _vazio(v: Any) -> bool:
    return not (v or "").strip()


def _chave_cp(lado: str, i: int, campo: str) -> str:
    return _SEP.join(("cp", lado, str(i), campo + "_detalhe"))


def _chave_so(i: int, attr: str) -> str:
    return _SEP.join(("so", str(i), attr))


def _ler_chave_so(chave: str) -> Tuple[int, str]:
    _, i, attr = chave.split(_SEP)
    return int(i), attr


def _ler_chave_cp(chave: str) -> Tuple[str, int, str]:
    _, lado, i, campo = chave.split(_SEP)
    return lado, int(i), campo


def faltas_kyc(caso: Caso) -> List[str]:
    """Chaves das informações de KYC que o analista ainda precisa dar: toda vez que a IA marcou "Sim"
    (registro societário, região de risco, PEP, mídia negativa, histórico de PLD ou de fraude), no
    titular ou em uma contraparte, sem trazer os detalhes pedidos pelo formulário. Chaves do titular
    são nomes de atributos do Caso; as das contrapartes seguem `_chave_cp`."""
    f: List[str] = []
    if not caso.eh_pj() and caso.registro_societario == "Sim":
        f += [a for a in ("reg_soc_razao_social", "reg_soc_data_abertura", "reg_soc_situacao_cadastral",
                          "reg_soc_ramo_atividade") if _vazio(getattr(caso, a))]
    if caso.regiao_risco == "Sim":
        if not caso.eh_pj() and _vazio(caso.cidade_estado):
            f.append("cidade_estado")
        if _vazio(caso.tipo_regiao_risco):
            f.append("tipo_regiao_risco")
        if caso.tipo_regiao_risco in ("", TIPOS_REGIAO_RISCO_1[2]) and _vazio(caso.tipo_regiao_risco_2):
            f.append("tipo_regiao_risco_2")
    if caso.pep == "Sim":
        f += [a for a in ("tipo_pep", "descricao_pep") if _vazio(getattr(caso, a))]
    for sim, det in (("midia_negativa", "midia_negativa_detalhe"), ("historico_pld", "historico_pld_detalhe"),
                     ("historico_fraude", "historico_fraude_detalhe")):
        if getattr(caso, sim) == "Sim" and _vazio(getattr(caso, det)):
            f.append(det)
    for lado, (_, attr_lista) in _LADOS.items():
        for i, cp in enumerate(getattr(caso, attr_lista)):
            for campo in _SINAIS_CONTRAPARTE:
                if getattr(cp, campo) == "Sim" and _vazio(getattr(cp, campo + "_detalhe")):
                    f.append(_chave_cp(lado, i, campo))
    for i, so in enumerate(caso.socios):
        if so.regiao_risco == "Sim" and _vazio(so.tipo_regiao_risco):
            f.append(_chave_so(i, "tipo_regiao_risco"))
        if so.pep == "Sim":
            f += [_chave_so(i, a) for a in ("tipo_pep", "descricao_pep") if _vazio(getattr(so, a))]
        for sim, det in (("midia_negativa", "midia_negativa_detalhe"), ("historico_pld", "historico_pld_detalhe"),
                         ("historico_fraude", "historico_fraude_detalhe")):
            if getattr(so, sim) == "Sim" and _vazio(getattr(so, det)):
                f.append(_chave_so(i, det))
    return f


def rotulo_kyc(caso: Caso, chave: str) -> Tuple[str, str]:
    """(rótulo, dica) da pergunta de KYC."""
    if chave.startswith("cp" + _SEP):
        _, _, campo = _ler_chave_cp(chave)
        return _SINAIS_CONTRAPARTE[campo.removesuffix("_detalhe")]
    if chave.startswith("so" + _SEP):
        return _ROTULOS_KYC[_ler_chave_so(chave)[1]]
    return _ROTULOS_KYC[chave]


def opcoes_kyc(chave: str) -> Optional[List[str]]:
    """Opções de seleção da pergunta (None quando a resposta é texto livre)."""
    attr = _ler_chave_so(chave)[1] if chave.startswith("so" + _SEP) else chave
    return OPCOES_KYC.get(attr)


def grupo_kyc(caso: Caso, chave: str) -> str:
    """Título do grupo da pergunta: o titular ou uma contraparte específica."""
    if chave.startswith("so" + _SEP):
        i, _ = _ler_chave_so(chave)
        so = caso.socios[i]
        return f"Sócio {i + 1}" + (f" — {so.nome}" if (so.nome or "").strip() else "")
    if not chave.startswith("cp" + _SEP):
        return "Cliente (KYC)"
    lado, i, _ = _ler_chave_cp(chave)
    nome_lado, attr_lista = _LADOS[lado]
    cp = getattr(caso, attr_lista)[i]
    return f"Contraparte de {nome_lado} {i + 1}" + (f" — {cp.nome}" if (cp.nome or "").strip() else "")


def aplicar_respostas_kyc(caso: Caso, respostas: Dict[str, str]) -> None:
    """Grava no Caso o que o analista respondeu às perguntas de KYC (ignora respostas vazias)."""
    for chave, valor in respostas.items():
        valor = (valor or "").strip()
        if not valor:
            continue
        if chave.startswith("cp" + _SEP):
            lado, i, campo = _ler_chave_cp(chave)
            setattr(getattr(caso, _LADOS[lado][1])[i], campo, valor)
        elif chave.startswith("so" + _SEP):
            i, attr = _ler_chave_so(chave)
            setattr(caso.socios[i], attr, valor)
        elif chave in _ROTULOS_KYC:
            setattr(caso, chave, valor)
    if caso.tipo_regiao_risco != TIPOS_REGIAO_RISCO_1[2]:
        caso.tipo_regiao_risco_2 = ""  # só existe quando o risco é "Outras Regiões de Risco"


def aplicar_mudanca_respondida(caso: Caso, mudanca: Dict[str, Any], avisos: List[str]) -> None:
    """Monta a narrativa com os meses que o analista informou e a data de abertura/último reporte.
    Sem valor informado, cria um pico elevado abaixo do total movimentado no período."""
    total_c, total_d = parse_valor_br(caso.mov_total_credito), parse_valor_br(caso.mov_total_debito)
    teto = max(total_c, total_d)
    valor = mudanca.get("valor") or ""
    if valor:
        if teto and parse_valor_br(valor) > teto:
            avisos.append(f"O valor do mês da mudança ({normalizar_valor_texto(valor)}) é maior que o total "
                          f"movimentado no período ({formatar_brl(teto)}). Confira.")
    else:
        valor = pico_mudanca_sugerido(total_c, total_d)
        avisos.append(f"Valor do mês da mudança criado pelo Sentinela ({valor}), abaixo do total movimentado "
                      "no período. Ajuste se necessário.")
    caso.comp_mudanca_comportamento = gerar_narrativa_mudanca_mensal(
        mudanca["inicio"], mudanca["fim"], mudanca["mes_mudanca"], valor)
    if mudanca.get("data_conta"):
        caso.comp_data_abertura_ultimo_reporte = mudanca["data_conta"]


def extrair_caso_via_ia(tipo_caso: str, fator_gerador: str, data_alerta: str, sentenca: str,
                          resumo: str, outras_movimentacoes: str = "", hoje: Optional[date] = None,
                          mudanca: Optional[Dict[str, Any]] = None,
                          **kw: Any) -> Tuple[Caso, List[str]]:
    """Extrai, aplica e ajusta a coerência, SEM completar os obrigatórios (o app ainda pode
    perguntar o que faltou no KYC). Devolve (caso, avisos). Os três campos do alerta são
    copiados como o analista digitou."""
    caso = Caso(numero_caso="tmp", tipo_caso=tipo_caso)
    caso.fator_gerador = fator_gerador
    caso.data_alerta = data_alerta
    caso.sentenca = sentenca
    dados = extrair_dados_do_texto(resumo, outras_movimentacoes, tipo_caso=tipo_caso, **kw)
    aplicar_dados_extraidos(caso, dados, hoje)
    texto_total = f"{resumo}\n{outras_movimentacoes}"
    avisos = coerencia_extracao(caso, texto_total)
    if mudanca:
        aplicar_mudanca_respondida(caso, mudanca, avisos)
    return caso, avisos


def preencher_caso_via_ia(*args: Any, hoje: Optional[date] = None, **kw: Any) -> Tuple[Caso, List[str]]:
    """Extrai e completa os obrigatórios numa só chamada. Devolve (caso, avisos)."""
    caso, avisos = extrair_caso_via_ia(*args, hoje=hoje, **kw)
    completar_obrigatorios(caso, hoje)
    return caso, avisos
