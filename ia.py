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
import random
import re
import unicodedata
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import requests

from core import (
    Caso, ContraparteMovimentacao, OutraMovimentacao, ItemArredondamento,
    MensagemPix, Socio, TIPO_PJ, TIPO_UNDER18, TIPO_CRIPTO, TIPOS_REGIAO_RISCO_1,
    TIPOS_PEP, TIPOS_OUTRAS_MOV, parse_valor_br, formatar_brl,
    normalizar_valor_texto, parse_periodo, periodo_padrao,
    gerar_narrativa_mudanca_comportamento, inferir_genero, montante_cripto,
    CRIPTO_SO_CREDITOS, CRIPTO_SO_DEBITOS, EVASAO_PARCIAL,
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
    '    "evasao": "Rápida Evasão, Sem Rápida Evasão, Só Créditos (Sem Débitos), Só Débitos (Sem Créditos), Evasão Parcial (Pequena Parcela nos Débitos) ou vazio",\n'
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
1. Preencha SOMENTE o que o texto afirma. Se uma informação não está no texto, use "" (ou [] para listas); não presuma relações, motivações nem conclusões. EXCEÇÃO: se a primeira linha da mensagem do usuário for "INVENÇÃO AUTORIZADA: SIM" (o texto pediu algo como "aleatório", "invente" ou "à sua escolha"), crie valores plausíveis para o que faltar, respeitando as restrições dadas (ex.: "renda baixa", "sem vínculo aparente"). Com "INVENÇÃO AUTORIZADA: NÃO", nunca invente, SALVO nas exceções das regras 20 a 23 e 25, que valem sempre, e só nos lados em que a linha "PREENCHER CONTRAPARTES AUTOMATICAMENTE" disser SIM; com "APENAS O PEDIDO: SIM" vale a regra 27.
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
12. Com INVENÇÃO AUTORIZADA: SIM e pedido de contrapartes aleatórias, crie nomes, idades, cidades/estados, rendas e cargos plausíveis, OBEDECENDO ao perfil pedido. Ex.: "diversas pessoas físicas sem capacidade financeira elevada" -> rendaPresumida BAIXA e variada em cada contraparte (ex.: R$1.300,00 a R$3.200,00), coerente com o cargo. Se o texto não disser as profissões, crie cargos aleatórios compatíveis com o perfil (ex.: auxiliar administrativo, vendedor, atendente, motorista, diarista) em registroProfissional. Perfil de empresa (PJ): ramo, porte e faturamento compatíveis com o pedido. Nunca contrarie uma instrução dada.
13. KYC: registroSocietario = "Sim" só se o texto disser que o cliente tem registro societário; nesse caso preencha registroSocietarioDetalhes (razaoSocial, dataAbertura, situacaoCadastral, ramoAtividade) com o que o texto trouxer. Região de risco: se o texto indicar cidade/estado da região, coloque em cidadeEstado (PF); se o tipo for "Outras Regiões de Risco", descreva a região em descricaoRegiaoRisco. PEP: tipoPep e descricaoPep (cargo e carência). Mídia negativa, histórico de PLD e de fraude: detalhe (link, data e fonte, quando houver) em seus campos "...Detalhe". Nunca invente detalhes que o texto não traz (sem INVENÇÃO AUTORIZADA).
14. outrasInformacoes: coloque aqui TODA informação adicional de KYC que o texto trouxer e que não tenha campo próprio (compartilhamento de dispositivo, redes sociais, processos, dados específicos de NuInvest/Crypto e outras informações não convencionais), UMA INFORMAÇÃO POR LINHA, separadas por quebra de linha, no formato "Rótulo: valor". Não repita o que já tem campo próprio.
15. Contrapartes com sinais de KYC (sócia de empresa/registro societário, PEP, mídia negativa, histórico de PLD, histórico de fraude, região de risco): marque "Sim" no item de CADA contraparte envolvida e preencha o campo "...Detalhe" correspondente com o que o texto trouxer. Se o texto indicar MAIS DE UMA contraparte com o sinal (ex.: "3 contrapartes são PEP"), CRIE uma entrada por contraparte na lista (mesmo passando de 5 entradas), cada uma com o sinal marcado, mantendo valores e porcentagens coerentes com o total. Nome, idade, cidade/estado e data de abertura dessas contrapartes seguem a regra 20. Nunca invente os detalhes dos sinais.
16. FRAGMENTAÇÃO (linha "FRAGMENTAÇÃO: SIM"): fragmentação = ALTO número de contrapartes. Coloque em totalContrapartesCredito e/ou totalContrapartesDebito um número alto (ex.: entre 60 e 200; use o número do texto, se houver) e NÃO indique concentração em nenhuma contraparte: as descritas ficam com porcentagens baixas e DIFERENTES entre si (ex.: 7%, 5%, 3,5%, 2%), NUNCA todas iguais nem todas no teto; nenhuma passa de cerca de 8% e nenhuma prevalece sobre as demais. Vale para os lados citados no texto (crédito, débito ou ambos, se não especificado). Esta regra prevalece sobre a regra 4.
17. FRACIONAMENTO ENTRE CONTRAPARTES (linha "FRACIONAMENTO ENTRE CONTRAPARTES: SIM"): alto fracionamento = CADA contraparte enviou ou recebeu um ALTO número de transações. Em numTransacoes de TODAS as contrapartes descritas coloque números altos (ex.: entre 30 e 150 cada), em crédito e em débito, com valor médio por transação plausível (valor da contraparte / numTransacoes).
17b. Se as linhas "FRAGMENTAÇÃO: SIM" e "FRACIONAMENTO ENTRE CONTRAPARTES: SIM" aparecerem JUNTAS, os DOIS comportamentos existem ao mesmo tempo: total alto de contrapartes (regra 16) E alto número de transações em cada contraparte descrita (regra 17).
18. ARREDONDAMENTO DIVERSO (linha "ARREDONDAMENTO DIVERSO: SIM"): o texto fala em várias transações em valores arredondados/unidades de milhar sem dar os números. Crie VÁRIAS linhas em arredondamentoItens, uma por valor de referência e por lado (Créditos e Débitos), com "arredondamento": "Sim". Ex.: 43 transações de R$1.000,00 nos créditos e 54 nos débitos; 20 de R$2.000,00 nos créditos e 33 nos débitos; 9 de R$5.000,00 nos créditos e 12 nos débitos; e assim sucessivamente (valores de referência crescentes, quantidades altas e geralmente decrescentes). A soma (quantidade x valor) de cada lado nunca passa do total do lado. Se o texto trouxer os números, use os do texto.
20. PREENCHIMENTO ALEATÓRIO DAS CONTRAPARTES, em QUALQUER tipo de caso, SOMENTE por lado em que a linha "PREENCHER CONTRAPARTES AUTOMATICAMENTE" disser SIM (crédito e/ou débito): se o texto não informar nome, idade (PF), cidade/estado ou data de abertura (PJ), INVENTE valores plausíveis e diferentes entre as contrapartes; SEMPRE crie nomes aleatórios quando não houver nome (contraparte PJ: nome coerente com o ramo de atividade). Onde disser NÃO, as contrapartes ficam só com o que o texto informou (campos não informados ficam ""). Se o texto só descreve o perfil das contrapartes (ex.: "contrapartes sem renda elevada") e o montante, aplique também a regra 25 nos lados com SIM.
21. LOCALIDADE DAS CONTRAPARTES (linha "LOCALIDADE DAS CONTRAPARTES"), em QUALQUER tipo de caso: "MESMA" = todas moram na mesma cidade/estado do titular (use a cidade/estado do titular em cidadeEstado de cada contraparte). "DIFERENTE" (localidades diferentes do titular ou sem vínculo aparente) = cada contraparte em OUTRA cidade/estado, aleatórios e variados, nunca a do titular. Sem a linha, só preencha o que o texto disser.
22. RENDA PRESUMIDA DAS CONTRAPARTES PF, em QUALQUER tipo de caso: se o texto indicar renda BAIXA (qualquer termo: baixa, modesta, sem capacidade financeira, reduzida etc.), preencha rendaPresumida com um valor aleatório BAIXO, entre R$1.300,00 e R$3.200,00 (até cerca de 2 salários mínimos; salário mínimo 2026 = R$1.621,00). Se indicar renda ALTA (qualquer termo: alta, elevada, alto poder aquisitivo etc.), preencha com um valor aleatório ALTO, entre R$35.000,00 e R$150.000,00 (acima de 20 salários mínimos, o patamar da classe A no Brasil). Cada contraparte recebe um valor DIFERENTE dos demais; nunca repita o mesmo valor em todas.
23. FATURAMENTO PRESUMIDO E PORTE (empresas): o faturamento presumido é ANUAL e o porte segue a receita bruta anual da regulamentação brasileira (LC 123/2006 e BNDES): MEI até R$81.000,00; Microempresa (ME) até R$360.000,00; Pequeno Porte (EPP) de R$360.000,01 a R$4.800.000,00; Médio Porte de R$4.800.000,01 a R$300.000.000,00; Grande Porte acima de R$300.000.000,00. Aplique às CONTRAPARTES PJ de qualquer tipo de caso. Faturamento BAIXO = até R$100.000,00: valor aleatório entre R$20.000,00 e R$100.000,00 (porte MEI ou Microempresa). Faturamento ELEVADO: use o porte informado e um valor aleatório dentro da faixa dele (Pequeno Porte, Médio Porte ou Grande Porte; Grande entre R$300.000.000,00 e R$2.000.000.000,00); se o porte não vier, use Médio Porte. Se o texto trouxer o valor, use-o e deduza o porte pela tabela.
25. CONTRAPARTES DETALHADAS QUANDO PERMITIDO, em QUALQUER tipo de caso: nos lados em que a linha "PREENCHER CONTRAPARTES AUTOMATICAMENTE" disser SIM (há fragmentação, fracionamento, "muitas/diversas contrapartes", perfil descrito ou pedido explícito) e houver total movimentado, CRIE de 3 a 5 contrapartes principais naquele lado se o texto não as listar, em contrapartesCredito/contrapartesDebito, cada uma com TODOS os campos: tipo (Pessoa Física, salvo se o texto disser empresa), nome, idade, cidadeEstado, rendaPresumida, registroProfissional (cargo), porcentagem, valor (porcentagem x total do lado) e numTransacoes; contraparte PJ: nome, dataAbertura, cidadeEstado, ramoAtividade, porte, faturamentoPresumido, porcentagem, valor e numTransacoes. As porcentagens são diferentes entre si e a soma não passa de 100%. Informe também o total de contrapartes (número). Nos lados com NÃO, NÃO crie contrapartes além das que o texto descreve.
27. APENAS O PEDIDO (linha "APENAS O PEDIDO: SIM", que prevalece sobre as regras 3, 20 e 25): o analista pediu SÓ o que informou (ex.: "uma contraparte de crédito e uma de débito", "transações pontuais", "preencha apenas..."). Insira SOMENTE o que o texto pediu ou informou e NÃO preencha o resto: campos não informados ficam "" (nada de nomes, idades, cidades, rendas, cargos ou transações aleatórios) e não crie contrapartes, sócios nem dados além dos pedidos. A linha "NÚMERO DE CONTRAPARTES PEDIDO: CRÉDITO N, DÉBITO M" dá a quantidade EXATA por lado (para N = 1: uma entrada, com totalContrapartes igual a 1 e valor igual ao total do lado), preenchidas só com o que o texto trouxe; lado sem número na linha segue o texto. Instruções explícitas continuam valendo (ex.: "renda baixa", "mesma localidade", "nome aleatório"). Só se preenche o restante quando o analista pedir ("preencha as demais", "pode preencher") ou descrever fragmentação, fracionamento ou muitas contrapartes, o que a linha "PREENCHER CONTRAPARTES AUTOMATICAMENTE" já resume.
28. TIMELINE DE TRANSFERÊNCIAS (campo "evasao" de "thundera", créditos e débitos bancários do caso), em QUALQUER tipo de caso: "Rápida Evasão" (o texto diz que os valores recebidos foram rapidamente evadidos/repassados), "Sem Rápida Evasão" (diz que não houve), "Só Créditos (Sem Débitos)" (os valores foram recebidos, mas NÃO evadidos: só créditos, sem débitos), "Só Débitos (Sem Créditos)" (não houve recebimentos; os valores já estavam na conta e foram transferidos nos débitos), "Evasão Parcial (Pequena Parcela nos Débitos)" (recebeu os valores, mas evadiu apenas uma parcela pequena nos débitos). "" se o texto não disser nada. Nos modos de um lado só e na evasão parcial, mantenha em totalCredito/totalDebito os totais que o texto trouxe.
29. Saída: APENAS um objeto JSON válido, sem markdown, sem crases e sem texto antes ou depois.
"""

_REGRAS_PJ = """
REGRAS ESPECÍFICAS DE PESSOA JURÍDICA:
- O titular do caso é uma EMPRESA: preencha nomeEmpresa, dataAbertura, ramoAtividade, porte, faturamentoPresumido e endereco. Presença online e fachada da empresa são só "Sim" ou "Não" (presencaOnline, fachadaEmpresa), sem detalhes; deixe "" se o texto não falar.
- Informações sobre os sócios vão em "socios" (nome, idade, endereco, rendaPresumida, patrimonio, regiaoRisco, tipoRegiaoRisco, pep, tipoPep, descricaoPep, historicoPld, historicoFraude, midiaNegativa e os campos "...Detalhe"). Marque "Sim" em cada sócio envolvido e preencha só os detalhes que o texto trouxer. Não crie sócios que o texto não cite, EXCETO quando o texto indicar mais de um sócio com um sinal (ex.: "2 sócios são PEP"): aí CRIE uma entrada por sócio, cada uma com o sinal marcado; sem INVENÇÃO AUTORIZADA deixe nome e demais dados em branco, com INVENÇÃO AUTORIZADA crie-os. Nunca invente os detalhes dos sinais.
- Não preencha campos de pessoa física do titular (nome, idade, renda).
- EXCEÇÕES ALEATÓRIAS DA PJ (valem sempre, como a regra 20): se não houver nome da empresa, invente um coerente com o ramo de atividade. Se faltarem nome, idade ou renda presumida de um sócio, invente valores plausíveis; endereço do sócio não informado = o mesmo endereço da empresa.
- Aplique a regra 23 (faturamento presumido e porte) também ao TITULAR PJ. Na regra 21, a cidade/estado do titular é a da empresa, extraída do endereço.
"""

_REGRAS_PF = """
REGRAS ESPECÍFICAS DE PESSOA FÍSICA (inclui Cripto, NuInvest e Under 18):
- O titular é uma PESSOA: preencha nome, idade, cidadeEstado, ultimaAtualizacaoCadastral, profissaoInformada, rendaPresumida, registroProfissional e os campos de risco.
- "responsavelLegal" só deve ser preenchido se o texto falar do responsável legal de um menor de idade; caso contrário, deixe os campos "".
- Aplique a regra 22 (renda baixa ou alta, com os mesmos valores aleatórios) também à rendaPresumida do TITULAR e, no Under 18, à renda presumida do responsável legal. Na regra 21, a cidade/estado do titular é a cidadeEstado dele.
"""

_REGRAS_CRIPTO = """
REGRAS ESPECÍFICAS DE CRIPTO:
- Em "thundera", inclua também "evasaoCripto": "Rápida Evasão", "Sem Rápida Evasão", "Só Créditos (Sem Débitos)", "Só Débitos (Sem Créditos)" ou "". Ela vale SÓ para os valores de criptomoedas informados em "OUTRAS MOVIMENTAÇÕES (NÃO BANCÁRIAS)" (tipo Criptomoedas), com o montante citado na descrição. "Rápida Evasão": a instrução diz que os valores de cripto foram rapidamente movimentados/repassados/evadidos (ex.: "recebeu e enviou em seguida", "rápida evasão", "repasses rápidos"). "Sem Rápida Evasão": diz que não houve (ex.: "sem rápida evasão", "não houve repasse rápido"). "Só Créditos (Sem Débitos)": os valores foram recebidos, mas NÃO evadidos, sem saídas (ex.: "só créditos", "sem débitos", "recebeu e manteve"). "Só Débitos (Sem Créditos)": não houve recebimentos, e os valores, que já estavam na conta, foram transferidos nos débitos (ex.: "só débitos", "sem créditos", "sem recebimentos", "já estavam na conta"). "" quando a instrução não disser nada. Não confunda com "evasao", que é dos créditos e débitos bancários do caso.
- Em "outrasMovimentacoes", mantenha na "info" da linha de Criptomoedas o montante em R$ que o texto trouxe (ex.: "R$ 200.000,00") e a instrução dada; não invente montante.
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


SYSTEM_PROMPT_CRIPTO = SYSTEM_PROMPT_PF + _REGRAS_CRIPTO


def prompt_para_tipo(tipo_caso: str) -> str:
    if tipo_caso == TIPO_PJ:
        return SYSTEM_PROMPT_PJ
    return SYSTEM_PROMPT_CRIPTO if tipo_caso == TIPO_CRIPTO else SYSTEM_PROMPT_PF


# ---------------------------------------------------------------------------
# Invenção autorizada
# ---------------------------------------------------------------------------

def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


_RE_INVENCAO = re.compile(
    r"aleatori|\binvent|\bcrie\s+(?:os\s+|uns\s+)?(?:valores|dados|nomes)|\bgere\s+(?:os\s+|uns\s+)?(?:valores|dados|nomes)"
    r"|\b(?:a|na)\s+sua\s+escolha|\bsua\s+escolha\b|livre\s+escolha|escolha\s+livre"
)


_RE_NEGA_INVENCAO = re.compile(r"\b(?:nao|sem|nunca)\s+(?:\w+\s+)?(?:invent\w*|cri[ae]\w*|ger[ae]\w*|aleatori\w*)")


def autoriza_invencao(texto: str) -> bool:
    """True se o texto autoriza a IA a criar valores ('aleatório', 'invente', 'à sua escolha'...).
    Negações ("não invente", "sem valores aleatórios") não autorizam."""
    t = _RE_NEGA_INVENCAO.sub(" ", _sem_acento(texto))
    return bool(_RE_INVENCAO.search(t))


# ---- Quando o Sentinela pode preencher as contrapartes sozinho --------------------------------------
# Regra do analista: com um número LIMITADO de contrapartes (1 a 5) ou comandos como "preencha só o que informei",
# só se faz o que foi pedido. O resto só é preenchido quando há fragmentação/fracionamento, "muitas/diversas
# contrapartes" (ou termos parecidos), perfil descrito para as contrapartes, ou pedido explícito para preencher.
_NUMEROS = {"um": 1, "uma": 1, "1": 1, "dois": 2, "duas": 2, "2": 2, "tres": 3, "3": 3, "quatro": 4, "4": 4,
            "cinco": 5, "5": 5}
_N = r"(um|uma|dois|duas|tres|quatro|cinco|[1-5])"
_LADO_CRED = r"(?:credito|entrada|recebimento|recebidos?)"
_LADO_DEB = r"(?:debito|saida|envio|enviados?)"
_RE_LIM_CRED = re.compile(rf"\b{_N}\s+(?:unic[ao]\s+|so\s+)?contrapartes?\s+(?:de|do|no|na|em)\s+{_LADO_CRED}"
                          rf"|\b{_N}\s+(?:de|do|no|na)\s+{_LADO_CRED}")
_RE_LIM_DEB = re.compile(rf"\b{_N}\s+(?:unic[ao]\s+|so\s+)?contrapartes?\s+(?:de|do|no|na|em)\s+{_LADO_DEB}"
                         rf"|\b{_N}\s+(?:de|do|no|na)\s+{_LADO_DEB}")
_RE_N_CONTRAPARTES_SO = re.compile(rf"(?:so|apenas|somente|unicamente|exclusivamente)\s+{_N}\s+contrapart")
_RE_UMA_CONTRAPARTE_QUALIFICADA = re.compile(
    r"\b(?:um|uma|1)\s+(?:so|unica|unico)\s+contraparte\b|contraparte\s+(?:unica|so)\b|\bunica\s+contraparte"
    r"|\b(?:so|apenas|somente)\s+(?:uma|um|1)\s+contraparte")
_RE_UMA_CONTRAPARTE = re.compile(r"\b(?:um|uma|1)\s+contraparte\b")
_RE_MUITAS = re.compile(
    r"(?:divers[ao]s?|vari[ao]s|muit[ao]s|grande\s+(?:numero|quantidade|volume)|alto\s+numero|elevad[oa]\s+"
    r"(?:numero|quantidade)|inumer\w+|dezenas|centenas|multipl[ao]s|numeros[ao]s)\s+(?:de\s+)?contrapart"
    r"|contrapartes?\s+(?:em\s+)?(?:grande|alto|elevado)\s+(?:numero|quantidade)")
_RE_MUITAS_N = re.compile(r"\b(?:[6-9]|\d{2,})\s+contrapartes?(?:\s+(?:de|do|no|na)\s+(credito|entrada|debito|saida))?")
_RE_PONTUAL = re.compile(r"\bpontua(?:l|is)\b|poucas\s+(?:contrapartes|transacoes)|algumas\s+contrapartes|apenas\s+algumas")
_RE_SO_O_PEDIDO = re.compile(
    r"\b(?:so|apenas|somente|unicamente|exclusivamente)\s+(?:o|os|a|as)?\s*(?:que\s+(?:eu\s+|ela\s+|ele\s+)?(?:pedi|peco|pedir|informei|informar|disse|falei)|"
    r"informac\w+|dados|isso|esses|essas|esse|essa)"
    r"|\bpreench[ae]\w*\s+(?:so|apenas|somente)\b|\b(?:so|apenas|somente)\s+preench\w+"
    r"|\bnao\s+(?:preench\w+|complet\w+)\s+(?:o\s+|os\s+|as\s+|a\s+)?(?:resto|restante|demais|mais\s+nada|outros|outras|nada)"
    r"|\bsem\s+(?:preencher|completar)\s+(?:o\s+|os\s+|as\s+|a\s+)?(?:resto|restante|demais)"
    r"|\bnao\s+(?:invent\w+|complet\w+)\b|\bnada\s+alem\s+d(?:o|isso)")
_RE_NEGADO = re.compile(r"\b(?:nao|sem|nunca)\s+(?:\w+\s+){0,2}(?:preench\w+|complet\w+|cri\w+|invent\w+|ger\w+)[^.;,\n]*")
_RE_PERMISSAO = re.compile(
    r"preench\w+\s+(?:as\s+|os\s+|o\s+)?(?:demais|restante|resto|outr\w+|que\s+falt\w+|campos\s+faltantes|todas?)"
    r"|\bpode(?:m|s)?\s+(?:preencher|completar|criar|inventar|gerar)"
    r"|\bcomplet[ae]\w*\s+(?:o\s+|os\s+|as\s+)?(?:resto|restante|demais|campos)"
    r"|preench\w+\s+automaticamente|fique\s+a\s+vontade")


def _limite_lado(t: str, regex: "re.Pattern[str]") -> Optional[int]:
    m = regex.search(t)
    if not m:
        return None
    return _NUMEROS[next(g for g in m.groups() if g)]


def limite_contrapartes(texto: str) -> Dict[str, Optional[int]]:
    """Quantidade LIMITADA (1 a 5) de contrapartes pedida por lado: {"cred": n|None, "deb": n|None}.
    "uma contraparte só"/"apenas duas contrapartes" (sem lado) valem para os dois lados."""
    t = _sem_acento(texto)
    cred, deb = _limite_lado(t, _RE_LIM_CRED), _limite_lado(t, _RE_LIM_DEB)
    geral = None
    m = _RE_N_CONTRAPARTES_SO.search(t)
    if m:
        geral = _NUMEROS[m.group(1)]
    elif _RE_UMA_CONTRAPARTE_QUALIFICADA.search(t):
        geral = 1
    elif _RE_UMA_CONTRAPARTE.search(t) and "contrapartes" not in t:
        geral = 1  # "uma contraparte" sem qualificador só vale se o texto não fala de contrapartes no plural
    if cred is not None or deb is not None:
        return {"cred": cred, "deb": deb}  # número dito para um lado não vale para o outro
    return {"cred": geral, "deb": geral}


def contrapartes_pedidas(texto: str) -> Optional[int]:
    """Número de contrapartes pedido quando é o mesmo nos dois lados (None se não houver limite ou se diferir)."""
    lim = limite_contrapartes(texto)
    return lim["cred"] if lim["cred"] is not None and lim["cred"] == lim["deb"] else None


def permite_preencher_resto(texto: str) -> bool:
    """Pedido EXPLÍCITO para preencher as demais contrapartes/campos ("pode preencher o restante",
    "invente", "aleatório"...). Negações ("não preencha o resto") não contam."""
    t = _RE_NEGADO.sub(" ", _sem_acento(texto))
    return bool(_RE_PERMISSAO.search(t)) or autoriza_invencao(texto)


def _perfil_nas_contrapartes(texto: str) -> bool:
    """Há perfil (renda baixa/alta ou localidade) descrito numa frase que fala das contrapartes."""
    for trecho in re.split(r"[.;\n]", texto or ""):
        if "contraparte" in _sem_acento(trecho) and (perfil_renda_contrapartes(trecho) or localidade_contrapartes(trecho)):
            return True
    return False


def politica_contrapartes(texto: str) -> Dict[str, Any]:
    """Decide, por lado, se o Sentinela pode criar/completar contrapartes sozinho.
    - "restrito": comandos como "preencha só o que informei" ou "pontuais" (sem pedido explícito de preencher);
    - "limite": quantidade limitada pedida por lado (1 a 5), que também restringe, salvo pedido explícito;
    - "livre": por lado, quando há fragmentação, fracionamento, "muitas/diversas contrapartes", perfil das
      contrapartes ou pedido explícito, e o lado não está restrito."""
    t = _sem_acento(texto)
    permissao = permite_preencher_resto(texto)
    limite = limite_contrapartes(texto)
    restrito_geral = bool(_RE_SO_O_PEDIDO.search(t) or _RE_PONTUAL.search(t)) and not permissao
    sinais_gerais = (menciona_fragmentacao(texto) or menciona_fracionamento(texto) or bool(_RE_MUITAS.search(t))
                     or _perfil_nas_contrapartes(texto) or permissao)
    muitas_lado = {"cred": False, "deb": False}
    for m in _RE_MUITAS_N.finditer(t):
        lado = m.group(1)
        for k in (("cred",) if lado in ("credito", "entrada") else ("deb",) if lado else ("cred", "deb")):
            muitas_lado[k] = True
    livre = {}
    for k in ("cred", "deb"):
        limitado = limite[k] is not None and not permissao
        livre[k] = (not restrito_geral) and (not limitado) and (sinais_gerais or muitas_lado[k])
    return {"restrito": restrito_geral or any(limite[k] is not None and not permissao for k in limite),
            "restrito_geral": restrito_geral, "limite": limite, "livre": livre, "permissao": permissao}


def restringe_ao_pedido(texto: str) -> bool:
    """True se o analista pediu para inserir SÓ o que informou (limite de contrapartes ou "preencha só...")."""
    return bool(politica_contrapartes(texto)["restrito"])


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


_RE_FRAGMENTACAO = re.compile(r"fragment")
_RE_FRACIONAMENTO = re.compile(r"fraciona")
_RE_ARRED = re.compile(r"arredond")
_RE_ARRED_VAGO = re.compile(r"divers|vari[ao]s|mult[ao]s|muit[ao]s|alto\s+(?:numero|volume)|grande\s+(?:numero|volume)"
                            r"|diversidade|recorrent|reiterad|frequent|sucessiv|inumer|inumeras|sistematic")


def menciona_fragmentacao(texto: str) -> bool:
    """Fragmentação = alto número de contrapartes, sem concentração em nenhuma delas."""
    return bool(_RE_FRAGMENTACAO.search(_sem_acento(texto)))


def menciona_fracionamento(texto: str) -> bool:
    """Alto fracionamento entre as contrapartes = cada contraparte com um alto número de transações."""
    return bool(_RE_FRACIONAMENTO.search(_sem_acento(texto)))


def menciona_arredondamento_diverso(texto: str) -> bool:
    """'Diversas transações arredondadas' e termos parecidos: a IA cria várias linhas de arredondamento."""
    t = _sem_acento(texto)
    return bool(_RE_ARRED.search(t) and _RE_ARRED_VAGO.search(t))


_RE_MESMA_LOC = re.compile(r"mesma[s]?\s+(?:localidade|cidade|regiao|praca)|mesmo\s+(?:estado|municipio)"
                           r"|mesmas\s+localidades|mesma\s+cidade/estado|moram\s+na\s+mesma|residem\s+na\s+mesma")
_RE_DIF_LOC = re.compile(r"(?:localidades|cidades|estados|regioes|municipios)\s+(?:diferentes|distintos[as]?|distintas)"
                         r"|localidade\s+diferente|cidade\s+diferente|estado\s+diferente|outras?\s+(?:cidades|localidades)"
                         r"|sem\s+(?:vinculo|relacao|ligacao)\s+aparente|sem\s+vinculo|distantes?\s+do\s+titular"
                         r"|diferentes?\s+do\s+titular|diferentes?\s+do\s+cliente")


def localidade_contrapartes(texto: str) -> str:
    """'MESMA' (contrapartes na cidade/estado do titular), 'DIFERENTE' (outras cidades/estados) ou ''."""
    t = _sem_acento(texto)
    if _RE_DIF_LOC.search(t):
        return "DIFERENTE"
    if _RE_MESMA_LOC.search(t):
        return "MESMA"
    return ""


_RE_RENDA_BAIXA = re.compile(r"sem\s+(?:renda|capacidade\s+financeira)\s+(?:alta|elevada)|sem\s+capacidade"
                             r"|renda\s+(?:baixa|modesta|reduzida|pequena)|baixa\s+renda|baixo\s+poder"
                             r"|capacidade\s+financeira\s+(?:baixa|reduzida|limitada)|renda\s+inferior")
_RE_RENDA_ALTA = re.compile(r"renda\s+(?:alta|elevada)|alta\s+renda|alto\s+poder|capacidade\s+financeira\s+(?:alta|elevada)")


def perfil_renda_contrapartes(texto: str) -> str:
    """'BAIXA', 'ALTA' ou '' conforme o perfil de renda citado no texto (negações como "sem renda
    elevada" contam como BAIXA)."""
    t = _sem_acento(texto)
    if _RE_RENDA_BAIXA.search(t):
        return "BAIXA"
    if _RE_RENDA_ALTA.search(t):
        return "ALTA"
    return ""


_NOMES = ["Marcos", "Fernanda", "Rafael", "Camila", "Anderson", "Juliana", "Thiago", "Patrícia", "Lucas", "Aline",
          "Rodrigo", "Vanessa", "Bruno", "Daniela", "Felipe", "Luciana", "Gustavo", "Renata", "Diego", "Priscila"]
_SOBRENOMES = ["Andrade", "Lopes", "Ribeiro", "Souza", "Teixeira", "Pires", "Moura", "Carvalho", "Nunes", "Rocha",
               "Almeida", "Barbosa", "Cardoso", "Dias", "Freitas", "Gomes", "Martins", "Oliveira", "Pereira", "Silva"]
_CIDADES = ["São Paulo/SP", "Belo Horizonte/MG", "Recife/PE", "Salvador/BA", "Curitiba/PR", "Porto Alegre/RS",
            "Fortaleza/CE", "Goiânia/GO", "Manaus/AM", "Campinas/SP", "Betim/MG", "Niterói/RJ", "Londrina/PR",
            "Joinville/SC", "Vitória/ES", "Natal/RN"]
_CARGOS = {
    "BAIXA": ["Auxiliar de limpeza", "Vendedor", "Atendente de lanchonete", "Motoboy", "Porteiro", "Diarista",
              "Repositor de mercadorias", "Ajudante geral", "Cozinheira", "Entregador"],
    "": ["Analista administrativo", "Técnico em informática", "Professor", "Vendedor externo", "Contador",
         "Enfermeiro", "Motorista de aplicativo", "Assistente financeiro"],
    "ALTA": ["Médico", "Advogado", "Engenheiro civil", "Empresário", "Diretor comercial", "Dentista",
             "Arquiteto", "Gerente de contas corporativas"],
}
_RAMOS = ["Comércio varejista", "Transporte de cargas", "Serviços de limpeza", "Alimentação", "Construção civil",
          "Tecnologia da informação", "Consultoria empresarial"]
_SUFIXOS_EMPRESA = ["Comércio Ltda", "Serviços Ltda", "Participações Ltda", "Distribuidora Ltda", "& Cia Ltda"]


def _renda_aleatoria(perfil: str, rng: random.Random, usadas: set) -> str:
    for _ in range(50):
        if perfil == "BAIXA":
            v = rng.randint(13, 32) * 100
        elif perfil == "ALTA":
            v = rng.randint(35, 150) * 1000
        else:
            v = rng.randint(35, 95) * 100
        if v not in usadas:
            break
    usadas.add(v)
    return formatar_brl(float(v))


def ajustar_contrapartes_pedidas(caso: Caso, texto: str, rng: Optional[random.Random] = None) -> List[str]:
    """Quantidade LIMITADA pedida (1 a 5, por lado): cada lado com limite fica com exatamente N contrapartes,
    preenchidas só com o que o analista informou (com N = 1 a contraparte leva o total do lado). Com o lado
    restrito, só as especificações explícitas do texto (renda baixa/alta, localidade) são aplicadas."""
    rng = rng or random.Random()
    pol = politica_contrapartes(texto)
    avisos: List[str] = []
    perfil = perfil_renda_contrapartes(texto)
    loc = localidade_contrapartes(texto)
    cidade_titular = (caso.cidade_estado or "").strip() if not caso.eh_pj() else ""
    for lado, rotulo, attr_lista, attr_total, attr_cont in (
            ("cred", "crédito", "contrapartes_credito", "mov_total_credito", "mov_total_contrapartes_credito"),
            ("deb", "débito", "contrapartes_debito", "mov_total_debito", "mov_total_contrapartes_debito")):
        n = pol["limite"][lado]
        lista = getattr(caso, attr_lista)
        total = parse_valor_br(getattr(caso, attr_total))
        if not n or (total <= 0 and not lista):
            continue
        if len(lista) > n:
            del lista[n:]
            avisos.append(f"O texto pediu {n} contraparte(s) de {rotulo}; as demais foram removidas.")
        while len(lista) < n and total > 0:
            lista.append(ContraparteMovimentacao(tipo="Pessoa Física"))
        setattr(caso, attr_cont, str(len(lista)))
        if n == 1 and lista and total > 0:
            c = lista[0]
            if not (c.porcentagem or "").strip():
                c.porcentagem = "100%"
            if not (c.valor or "").strip():
                c.valor = formatar_brl(total)
        if pol["permissao"]:
            continue  # pediu para preencher o resto: completar_contrapartes cuida do preenchimento
        rendas: set = set()
        for c in lista:  # só o que o texto especificou de forma explícita
            if c.tipo != "Pessoa Jurídica" and perfil and not (c.renda_presumida or "").strip():
                c.renda_presumida = _renda_aleatoria(perfil, rng, rendas)
            if not (c.cidade_estado or "").strip():
                if loc == "MESMA" and cidade_titular:
                    c.cidade_estado = cidade_titular
                elif loc == "DIFERENTE":
                    c.cidade_estado = rng.choice([x for x in _CIDADES if x.lower() != cidade_titular.lower()])
    return avisos


def completar_contrapartes(caso: Caso, texto: str = "", rng: Optional[random.Random] = None) -> List[str]:
    """Rede de segurança da regra 25: quando o texto fala de contrapartes e há total movimentado no lado,
    mas a IA não as devolveu, cria as principais; e preenche os campos que ficaram em branco
    (nome, idade, cidade/estado, renda presumida, registro profissional, valor, porcentagem e número de
    transações). Devolve avisos em português."""
    rng = rng or random.Random()
    avisos: List[str] = []
    pol = politica_contrapartes(texto)
    if not (pol["livre"]["cred"] or pol["livre"]["deb"]):
        return avisos  # só o pedido: nada de criar nem completar contrapartes sozinho
    t = _sem_acento(texto)
    perfil = perfil_renda_contrapartes(texto)
    fragmentacao, fracionamento = menciona_fragmentacao(texto), menciona_fracionamento(texto)
    loc = localidade_contrapartes(texto)
    cidade_titular = (caso.cidade_estado or "").strip() if not caso.eh_pj() else ""
    pool_cidades = [c for c in _CIDADES if loc != "DIFERENTE" or c.lower() != cidade_titular.lower()]

    for lado, rotulo, attr_lista, attr_total, attr_cont in (
            ("cred", "crédito", "contrapartes_credito", "mov_total_credito", "mov_total_contrapartes_credito"),
            ("deb", "débito", "contrapartes_debito", "mov_total_debito", "mov_total_contrapartes_debito")):
        if not pol["livre"][lado]:
            continue
        lista = getattr(caso, attr_lista)
        total = parse_valor_br(getattr(caso, attr_total))
        if total <= 0:
            continue
        informado = re.search(r"\d+", getattr(caso, attr_cont) or "")
        if not lista and ("contraparte" in t or informado or fragmentacao or fracionamento):
            n = min(int(informado.group()), 5) if informado else 4
            n = max(n, 1)
            if fragmentacao:
                pcts = rng.sample(range(2, 9), min(n, 7))
            else:
                pcts = [30, 22, 15, 10, 6][:n]  # plano B, já distintos e com soma baixa
                for _ in range(100):  # sorteia porcentagens DISTINTAS que somem até 90%
                    candidatas = sorted(rng.sample(range(5, 31), n), reverse=True)
                    if sum(candidatas) <= 90:
                        pcts = candidatas
                        break
            for pct in pcts[:n]:
                lista.append(ContraparteMovimentacao(tipo="Pessoa Física", porcentagem=f"{pct}%"))
            avisos.append(f"O resumo não detalhava as contrapartes de {rotulo}; o Sentinela criou {len(lista)} "
                          "contrapartes principais com dados aleatórios. Revise nomes, valores e quantidades.")
        rendas: set = set()
        primeiros_nomes = {(c.nome or "").split(" ")[0] for c in lista if (c.nome or "").strip()}
        for c in lista:
            pj = c.tipo == "Pessoa Jurídica"
            if not (c.nome or "").strip():
                if pj:
                    c.nome = f"{rng.choice(_SOBRENOMES)} {rng.choice(_RAMOS).split()[0]} {rng.choice(_SUFIXOS_EMPRESA)}"
                else:
                    livres = [n for n in _NOMES if n not in primeiros_nomes] or _NOMES  # sem repetir o 1º nome
                    primeiro = rng.choice(livres)
                    primeiros_nomes.add(primeiro)
                    c.nome = f"{primeiro} {rng.choice(_SOBRENOMES)} {rng.choice(_SOBRENOMES)}"
            if not (c.cidade_estado or "").strip():
                c.cidade_estado = cidade_titular if (loc == "MESMA" and cidade_titular) else rng.choice(pool_cidades)
            if not (c.num_transacoes or "").strip():
                c.num_transacoes = str(rng.randint(30, 150) if fracionamento else rng.randint(3, 40))
            if not (c.porcentagem or "").strip() and not (c.valor or "").strip():
                c.porcentagem = f"{rng.randint(2, 20)}%"
            if pj:
                if not (c.data_abertura or "").strip():
                    c.data_abertura = f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/{rng.randint(2005, 2023)}"
                if not (c.ramo_atividade or "").strip():
                    c.ramo_atividade = rng.choice(_RAMOS)
                if not (c.porte or "").strip():
                    c.porte = "Microempresa (ME)"
                if not (c.faturamento_presumido or "").strip():
                    c.faturamento_presumido = formatar_brl(float(rng.randint(20, 100) * 1000))
            else:
                if not (c.idade or "").strip():
                    c.idade = str(rng.randint(19, 62))
                if not (c.renda_presumida or "").strip():
                    c.renda_presumida = _renda_aleatoria(perfil, rng, rendas)
                if not (c.registro_profissional or "").strip():
                    cargo = rng.choice(_CARGOS[perfil if perfil in _CARGOS else ""])
                    c.registro_profissional = cargo if perfil == "ALTA" else f"{cargo}, sem registro profissional"
    return avisos


_RE_SEM_EVASAO = re.compile(r"\bsem\s+(?:rapid[ao]s?\s+)?(?:evasao|repasses?\s+rapidos?)"
                            r"|\bnao\s+(?:houve|ha|teve|tem)\s+(?:rapid\w+\s+)?(?:evasao|repasses?)")
_RE_COM_EVASAO = re.compile(r"rapid[ao]s?\s+evasao|evasao\s+rapida|repasses?\s+rapidos?|\bevadi\w+|"
                            r"(?:enviad\w+|transferid\w+|repassad\w+|sacad\w+|movimentad\w+)\s+"
                            r"(?:logo|rapidamente|imediatamente|em\s+seguida)|logo\s+(?:apos|depois)|"
                            r"\bimediatamente\b|\brapidamente\b|\bno\s+mesmo\s+dia\b|\bem\s+seguida\b")
_RE_SO_DEBITOS = re.compile(r"\b(?:so|somente|apenas)\s+(?:os\s+)?debitos?\b|\bsem\s+(?:os\s+)?(?:creditos?|recebimentos?)\b"
                            r"|\bnao\s+(?:houve|ha|teve|tem)\s+(?:creditos?|recebimentos?)\b"
                            r"|\bja\s+estava(?:m)?\s+na\s+conta\b")
_RE_SO_CREDITOS = re.compile(r"\b(?:so|somente|apenas)\s+(?:os\s+)?creditos?\b|\bsem\s+(?:os\s+)?debitos?\b"
                             r"|\bnao\s+(?:houve|ha|teve|tem)\s+debitos?\b"
                             r"|\breceb\w+[^.;\n]*\bnao\s+(?:foram\s+|houve\s+|ha\s+)?(?:evadid\w+|evadiu|enviad\w+|enviou|transferid\w+|transferiu|repassad\w+|repassou)")


def evasao_cripto_do_texto(texto: str) -> str:
    """Modo da timeline de criptomoedas pela instrução do analista (reforço em código: a IA também devolve
    "evasaoCripto"): 'Só Débitos (Sem Créditos)', 'Só Créditos (Sem Débitos)', 'Sem Rápida Evasão',
    'Rápida Evasão' ou ''. Os modos de um lado só são testados antes; a negação de evasão vem depois."""
    t = _sem_acento(texto)
    if _RE_SO_DEBITOS.search(t):
        return CRIPTO_SO_DEBITOS
    if _RE_SO_CREDITOS.search(t):
        return CRIPTO_SO_CREDITOS
    if _RE_SEM_EVASAO.search(t):
        return "Sem Rápida Evasão"
    return "Rápida Evasão" if _RE_COM_EVASAO.search(t) else ""


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
    pol = politica_contrapartes(texto)
    sn = lambda v: "SIM" if v else "NÃO"  # noqa: E731
    return (
        f"INVENÇÃO AUTORIZADA: {sn(invencao)}\n"
        f"FRAGMENTAÇÃO: {sn(menciona_fragmentacao(texto))}\n"
        f"FRACIONAMENTO ENTRE CONTRAPARTES: {sn(menciona_fracionamento(texto))}\n"
        f"ARREDONDAMENTO DIVERSO: {sn(menciona_arredondamento_diverso(texto))}\n"
        f"LOCALIDADE DAS CONTRAPARTES: {localidade_contrapartes(texto) or 'NÃO INFORMADA'}\n"
        f"APENAS O PEDIDO: {sn(pol['restrito'])}\n"
        + (("NÚMERO DE CONTRAPARTES PEDIDO: " + ", ".join(
            f"{nome} {pol['limite'][k]}" for k, nome in (("cred", "CRÉDITO"), ("deb", "DÉBITO"))
            if pol["limite"][k]) + "\n") if any(pol["limite"].values()) else "")
        + f"PREENCHER CONTRAPARTES AUTOMATICAMENTE: CRÉDITO {sn(pol['livre']['cred'])}, DÉBITO {sn(pol['livre']['deb'])}\n"
        + "\n"
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


def _modo_cripto(v: Any) -> str:
    """Valor da timeline de criptomoedas devolvido pela IA: os dois padrões de evasão ou um dos lados só."""
    s = _sem_acento(_txt(v))
    if not s:
        return ""
    if re.search(r"so\s+debit|somente\s+debit|apenas\s+debit|sem\s+credit", s):
        return CRIPTO_SO_DEBITOS
    if re.search(r"so\s+credit|somente\s+credit|apenas\s+credit|sem\s+debit", s):
        return CRIPTO_SO_CREDITOS
    return _evasao(v)


def _modo_timeline(v: Any) -> str:
    """Valor de thundera.evasao (timeline bancária): os modos de cripto mais a evasão parcial."""
    s = _sem_acento(_txt(v))
    if re.search(r"parcial|pequena\s+parcela|parcela\s+pequena|pequeno\s+valor", s):
        return EVASAO_PARCIAL
    return _modo_cripto(v)


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
    _set(caso, "comp_evasao", _modo_timeline(thun.get("evasao")))
    if caso.tipo_caso == TIPO_CRIPTO:
        _set(caso, "comp_evasao_cripto", _modo_cripto(thun.get("evasaoCripto")))
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
    fragmentacao = menciona_fragmentacao(texto)
    fracionamento = menciona_fracionamento(texto)

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
        # 3b) fragmentação e fracionamento (só avisa)
        if fragmentacao and lista:
            m = re.search(r"\d+", getattr(caso, attr_cont) or "")
            n = int(m.group()) if m else 0
            if n < 30:
                avisos.append(f"O texto fala em fragmentação, mas o total de contrapartes de {rotulo} é {n or '—'}. "
                              "Fragmentação pede um número alto de contrapartes. Confira.")
            pcts_desc = [c.porcentagem.strip() for c in lista if (c.porcentagem or "").strip()]
            if len(pcts_desc) >= 2 and len(set(pcts_desc)) == 1:
                avisos.append(f"As contrapartes de {rotulo} têm todas a mesma porcentagem ({pcts_desc[0]}). "
                              "Varie os percentuais entre elas.")
            if any(parse_valor_br(c.porcentagem) >= 20.0 for c in lista):
                avisos.append(f"O texto fala em fragmentação, mas há contraparte de {rotulo} com 20% ou mais do "
                              "total (concentração). Confira os percentuais.")
        if fracionamento:
            baixas = [c for c in lista if _tem_digito(c.num_transacoes) and int(re.search(r"\d+", c.num_transacoes).group()) < 20]
            if baixas:
                avisos.append(f"O texto fala em alto fracionamento, mas {len(baixas)} contraparte(s) de {rotulo} "
                              "têm menos de 20 transações. Confira o número de transações.")
        # 4) regra de concentração (só avisa)
        if not invencao and not concentracao:
            for c in lista:
                if parse_valor_br(c.porcentagem) > 50.0:
                    avisos.append(
                        f"A contraparte de {rotulo} {c.nome or '(sem nome)'} tem {c.porcentagem} do total, mas o "
                        "texto não menciona concentração. Confira o percentual.")
    # localidade das contrapartes
    loc = localidade_contrapartes(texto)
    cidade_titular = (caso.cidade_estado or "").strip()
    if loc == "MESMA" and cidade_titular and not caso.eh_pj():
        for lista in (caso.contrapartes_credito, caso.contrapartes_debito):
            for c in lista:
                c.cidade_estado = cidade_titular
    elif loc == "DIFERENTE" and cidade_titular and not caso.eh_pj():
        for rotulo, lista in (("crédito", caso.contrapartes_credito), ("débito", caso.contrapartes_debito)):
            iguais = [c for c in lista if (c.cidade_estado or "").strip().lower() == cidade_titular.lower()]
            if iguais:
                avisos.append(f"O texto pede contrapartes de localidades diferentes do titular, mas {len(iguais)} "
                              f"contraparte(s) de {rotulo} estão em {cidade_titular}. Confira.")
    # rendas iguais entre contrapartes PF / sócios
    for rotulo, lista in (("crédito", caso.contrapartes_credito), ("débito", caso.contrapartes_debito)):
        rendas = [c.renda_presumida.strip() for c in lista if c.tipo != "Pessoa Jurídica" and (c.renda_presumida or "").strip()]
        if len(rendas) >= 3 and len(set(rendas)) == 1:
            avisos.append(f"As contrapartes de {rotulo} têm todas a mesma renda presumida ({rendas[0]}). "
                          "Varie os valores entre elas.")
    # endereço do sócio não informado = endereço da empresa
    if caso.eh_pj() and (caso.endereco or "").strip() and not restringe_ao_pedido(texto):
        for so in caso.socios:
            if not (so.endereco or "").strip():
                so.endereco = caso.endereco
    # arredondamento: quantidade x valor não pode passar do total do lado
    for rotulo_lado, cd, attr_total in (("créditos", "Créditos", "mov_total_credito"),
                                        ("débitos", "Débitos", "mov_total_debito")):
        total = parse_valor_br(getattr(caso, attr_total))
        soma = sum(parse_valor_br(it.quantidade) * parse_valor_br(it.valor)
                   for it in caso.arredondamento_itens if it.cred_deb == cd)
        if total > 0 and soma > total:
            avisos.append(f"As transações arredondadas de {rotulo_lado} somam {formatar_brl(soma)}, acima do total "
                          f"de {rotulo_lado} ({formatar_brl(total)}). Confira quantidades e valores.")
    return avisos


def completar_obrigatorios(caso: Caso, hoje: Optional[date] = None) -> Caso:
    """Fecha o que o formulário precisa para abrir de forma consistente: tipo de região de risco e de PEP
    quando há "Sim" sem tipo, período padrão e contagem de contrapartes descritas. NÃO coloca marcadores
    ("Não informado", R$0,00): o que não foi informado fica em branco e o dossiê não mostra esses campos.
    Não toca no nome do alerta, na data do alerta, na sentença nem no gênero."""
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
    if not (caso.mov_total_contrapartes_credito or "").strip() and caso.contrapartes_credito:
        caso.mov_total_contrapartes_credito = str(len(caso.contrapartes_credito))
    if not (caso.mov_total_contrapartes_debito or "").strip() and caso.contrapartes_debito:
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


def _ajustar_evasao_cripto(caso: Caso) -> None:
    """Timeline de cripto: só casos Cripto com montante em Outras Movimentações (Criptomoedas). Se a IA não
    marcou a evasão, lê a instrução da própria descrição; sem montante, não há timeline de cripto."""
    if caso.tipo_caso != TIPO_CRIPTO:
        caso.comp_evasao_cripto = ""
        return
    if montante_cripto(caso) <= 0:
        caso.comp_evasao_cripto = ""
        return
    if not caso.comp_evasao_cripto:
        instrucao = " ".join(m.info for m in caso.outras_movimentacoes if m.tipo == "Criptomoedas")
        caso.comp_evasao_cripto = evasao_cripto_do_texto(instrucao)


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
    _ajustar_evasao_cripto(caso)
    texto_total = f"{resumo}\n{outras_movimentacoes}"
    avisos_cp = ajustar_contrapartes_pedidas(caso, texto_total) + completar_contrapartes(caso, texto_total)
    avisos = avisos_cp + coerencia_extracao(caso, texto_total)
    if mudanca:
        aplicar_mudanca_respondida(caso, mudanca, avisos)
    return caso, avisos


def preencher_caso_via_ia(*args: Any, hoje: Optional[date] = None, **kw: Any) -> Tuple[Caso, List[str]]:
    """Extrai e completa os obrigatórios numa só chamada. Devolve (caso, avisos)."""
    caso, avisos = extrair_caso_via_ia(*args, hoje=hoje, **kw)
    completar_obrigatorios(caso, hoje)
    return caso, avisos
