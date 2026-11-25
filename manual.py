"""Manual do usuário do Sentinela: como funciona, comandos rápidos e tutoriais animados (HTML estático)."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

CSS_MANUAL = """
.sx-man{ text-align:left; font-family:var(--sans); color:var(--ink); font-size:14.5px; line-height:1.55; }
.sx-man h3{ font-family:var(--display); font-size:17px; color:var(--purple-deep); margin:26px 0 8px;
  padding-bottom:4px; border-bottom:2px dashed var(--purple-soft); }
.sx-man p{ margin:6px 0; }
.sx-man ol, .sx-man ul{ margin:6px 0 6px 20px; padding:0; }
.sx-man li{ margin:4px 0; }
.sx-man code{ font-family:var(--mono); font-size:12.5px; background:rgba(62,42,99,.10); padding:1px 6px; border-radius:4px; }
.sx-man .sx-man-aviso{ margin:12px 0; padding:12px 14px; border:2px solid var(--gold); border-radius:10px;
  background:rgba(201,167,107,.16); }
.sx-man .sx-man-aviso b.t{ display:block; font-family:var(--mono); font-size:11.5px; letter-spacing:.14em;
  text-transform:uppercase; color:var(--purple-deep); margin-bottom:4px; }
.sx-man table{ width:100%; border-collapse:collapse; margin:8px 0; font-size:13.5px; }
.sx-man th, .sx-man td{ border:1px solid var(--purple-soft); padding:6px 8px; text-align:left; vertical-align:top; }
.sx-man th{ background:rgba(62,42,99,.10); font-family:var(--mono); font-size:11.5px; letter-spacing:.08em; text-transform:uppercase; }
.sx-man pre{ font-family:var(--mono); font-size:12.5px; background:rgba(25,21,31,.06); border-radius:8px;
  padding:10px 12px; margin:8px 0; white-space:pre-wrap; }
"""

MANUAL_HTML = """
<div class="sx-man">

<p>O Sentinela organiza o questionário de um caso de PLD (alerta, KYC, movimentações e comportamentos) em um
<b>dossiê individual em PDF</b>. Você preenche o formulário à mão ou <b>descreve o caso em texto</b> e deixa o
Sentinela preencher. Sempre <b>revise</b> o formulário antes de gerar o dossiê.</p>

<h3>1. Como funciona: as telas</h3>
<table>
<tr><th>Tela</th><th>O que faz</th></tr>
<tr><td><b>Home</b></td><td><b>Iniciar novo caso</b>, <b>Banco de dossiês</b>, este manual e o formulário de feedback.</td></tr>
<tr><td><b>Tipo de caso</b> (etapa 1)</td><td>PF, PJ, Cripto, NuInvest ou Under 18. O tipo muda campos: PJ pede empresa e sócios; Under 18, o responsável legal.</td></tr>
<tr><td><b>Modo</b> (etapa 2)</td><td><b>Preencher com instruções</b> (automático) ou <b>Preencher manualmente</b>.</td></tr>
<tr><td><b>Preenchimento por instruções</b></td><td>Você digita <b>Nome do alerta</b>, <b>Data</b> e <b>Sentença</b> (o automático nunca os altera) e descreve o caso em <b>três caixas</b>: KYC, Movimentações e Comportamentos. Se faltar detalhe de KYC ou dados da mudança de comportamento, o Sentinela pergunta; depois abre o formulário preenchido.</td></tr>
<tr><td><b>Formulário</b></td><td><b>Bloco 1</b> Alerta/Sentença · <b>Bloco 2</b> KYC (e <b>2.1</b> sócios, só PJ) · <b>Bloco 3</b> Resumo de movimentações (totais, contrapartes, outras movimentações) · <b>Bloco 4</b> Thundera AML 360 (arredondamento, Pix, timeline, mudança de comportamento). Campos com * são obrigatórios. Termina em <b>Gerar dossiê do caso</b>.</td></tr>
<tr><td><b>Dossiê</b></td><td>Três abas: <b>Informações do Caso</b> (só o que foi preenchido; não classifica risco), <b>Resolução do Caso</b> (parecer, diligência e, no Cripto, Anexos) e <b>Avaliação de Qualidade</b>. Baixe o PDF de cada aba ou o <b>PDF completo</b>.</td></tr>
<tr><td><b>Banco de dossiês</b></td><td>Busque por número do caso ou use <b>Consultar banco de dados completo</b> para listar todos os dossiês salvos e abri-los.</td></tr>
</table>
<p>Campo sem informação fica <b>em branco</b> e <b>não aparece no dossiê</b>. Nos casos NuInvest, Crypto e outras
análises, o que não tem campo no KYC padrão vai em <b>Outras informações relevantes</b> (uma informação por linha,
<code>Rótulo: valor</code>).</p>

<h3>2. Comportamentos mapeados e comandos rápidos</h3>
<p>Escreva na caixa <b>Informações dos Comportamentos</b>. Termo e efeito:</p>
<table>
<tr><th>Comando rápido (exemplo)</th><th>O que o Sentinela preenche</th></tr>
<tr><td><code>Houve fragmentação nos créditos.</code></td><td>Total alto de contrapartes (60 a 200 ou o número informado), sem concentração: percentuais baixos e diferentes.</td></tr>
<tr><td><code>Alto fracionamento entre as contrapartes.</code></td><td>Cada contraparte descrita com muitas transações (cerca de 30 a 150).</td></tr>
<tr><td><code>Fragmentação e fracionamento.</code></td><td>Os dois efeitos juntos.</td></tr>
<tr><td><code>Diversas transações arredondadas em R$ 1.000,00 e R$ 2.000,00.</code></td><td>Várias linhas de Arredondamento, por valor e por lado (créditos e débitos). Com números seus, usa os seus.</td></tr>
<tr><td><code>Pix com mensagens "pagamento mercadoria" e "ajuda".</code></td><td>Uma linha de Pix por grupo de mensagens, com quantidade e exemplo.</td></tr>
<tr><td><code>Rápida evasão dos valores recebidos.</code> / <code>Sem rápida evasão.</code></td><td>Timeline de transferências em Rápida Evasão ou Sem Rápida Evasão.</td></tr>
<tr><td><code>Só créditos, sem débitos.</code> / <code>Só débitos, sem recebimentos.</code></td><td>Timeline de um lado só (o gráfico mostra só o lado que existe).</td></tr>
<tr><td><code>Recebeu e evadiu só uma pequena parcela nos débitos.</code></td><td>Evasão Parcial (Pequena Parcela nos Débitos).</td></tr>
<tr><td><code>Houve mudança de comportamento.</code></td><td>O Sentinela pede a <b>data de abertura da conta/último reporte</b> (anterior ao alerta) e, opcionalmente, o valor do mês da mudança, e monta a narrativa dos 6 meses.</td></tr>
<tr><td><code>Alta concentração em Carlos Lima.</code></td><td>A contraparte principal fica acima de 50%. Sem a palavra, nenhuma passa de 50%.</td></tr>
<tr><td><code>Recebeu R$ 200.000,00 em bitcoin, enviado em seguida a uma exchange.</code> (Cripto)</td><td>Timeline de criptomoedas com o montante e o modo de evasão (a linha de Criptomoedas vem da caixa de Movimentações).</td></tr>
</table>

<h3>3. Informações de KYC: comandos rápidos</h3>
<p>Escreva na caixa <b>Informações do KYC</b>, <b>uma informação por linha</b>. Cada dado vai para o seu campo:</p>
<pre>Nome: Carlos Eduardo Mendes
Idade: 42 anos
Cidade/Estado: Foz do Iguaçu/PR
Profissão informada: Comerciante
Registro profissional: sem registro profissional
Renda presumida: R$ 3.500,00</pre>
<table>
<tr><th>Se você escrever</th><th>O Sentinela faz</th></tr>
<tr><td><code>Registro societário: sócio de empresa do ramo de Serviços Combinados de Escritório</code></td><td>Registro societário = Sim, com o ramo. Faltando razão social, data de abertura ou situação, ele pergunta (ou preenche aleatoriamente, se você aceitar).</td></tr>
<tr><td><code>Mora em região de fronteira</code> (ou garimpo, extração mineral ou de madeira, Quadrilátero Ferrífero)</td><td>Região de risco = Sim e o tipo da região.</td></tr>
<tr><td><code>PEP relacionado: irmão de vereador, carência até 2027</code></td><td>PEP = Sim, tipo e descrição (carência).</td></tr>
<tr><td><code>Mídia negativa: contrabando, G1, 10/03/2025</code></td><td>Mídia negativa = Sim, com o texto.</td></tr>
<tr><td><code>Reporte ao COAF em 2024 por movimentação atípica</code></td><td>Histórico de PLD = Sim, com o texto.</td></tr>
<tr><td><code>Conta cancelada por fraude em 2023</code></td><td>Histórico de fraude = Sim, com o texto.</td></tr>
<tr><td><code>Compartilha dispositivo com outra conta</code></td><td>Qualquer outra informação vai para <b>Outras informações relevantes</b>.</td></tr>
</table>
<ul>
<li><b>Não mencionou, fica "Não".</b> Região de risco, PEP, mídia negativa, histórico de PLD e de fraude só ficam "Sim" quando você os cita (menção negada, como "não é PEP", não conta).</li>
<li><b>Citou sem detalhe?</b> Escreva a informação na mesma linha, ou o Sentinela abre um campo pequeno para você completar.</li>
<li><b>Dados genéricos:</b> escreva "preencha com dados aleatórios" e cada informação é criada no seu campo.</li>
<li><b>PJ:</b> inclua Nome da Empresa, Data de Abertura, Ramo, Porte, Faturamento Presumido, Endereço e, por sócio, Nome, Idade, Endereço, Renda e sinais de risco. <b>Under 18:</b> dados do responsável legal.</li>
</ul>

<h3>4. Movimentações: comandos rápidos</h3>
<p>Escreva na caixa <b>Informações das Movimentações</b>:</p>
<pre>Período de 01/01/2026 até 30/06/2026. Total de créditos R$ 450.000,00 e total de débitos R$ 430.000,00.
Diversas contrapartes de crédito, pessoas físicas de renda baixa, em cidades diferentes, nomes aleatórios. Uma delas é PEP.
2 contrapartes de débito, empresas de ramos diferentes, nomes aleatórios.
Saques de R$ 15.000,00, boletos de R$ 8.500,00, gastos no cartão de crédito de R$ 12.000,00 e empréstimo de R$ 20.000,00.</pre>
<table>
<tr><th>Comando rápido</th><th>Efeito</th></tr>
<tr><td><code>Período de 01/06/2026 até 01/08/2026</code>, <code>créditos de R$ ...</code>, <code>débitos de R$ ...</code></td><td>Período e totais.</td></tr>
<tr><td><code>João Silva (PF, 35 anos, São Paulo/SP), 40%, R$ 200.000,00, 23 transações</code></td><td>Contraparte descrita, com todos os campos informados.</td></tr>
<tr><td><code>120 contrapartes de crédito</code></td><td>Total como número; descreva só as 3 a 5 principais.</td></tr>
<tr><td><code>diversas / muitas contrapartes</code>, <code>pode preencher o restante</code></td><td>O Sentinela cria 3 a 5 contrapartes por lado, com nomes, idades e cidades diferentes.</td></tr>
<tr><td><code>uma contraparte de crédito e uma de débito</code>, <code>preencha apenas o que informei</code></td><td>Só o pedido. O que você não informou fica em branco.</td></tr>
<tr><td><code>renda baixa</code> / <code>renda alta</code></td><td>Renda de R$ 1.300 a R$ 3.200 (baixa) ou R$ 35 mil a R$ 150 mil (alta), diferente em cada contraparte.</td></tr>
<tr><td><code>mesma localidade</code> / <code>cidades diferentes do titular</code></td><td>Mesma cidade/estado do titular, ou cidades diferentes entre si.</td></tr>
<tr><td><code>aleatório</code>, <code>invente os nomes</code></td><td>Autoriza criar nomes, idades e cidades.</td></tr>
<tr><td><code>empresas de ramos diferentes</code>, <code>faturamento baixo/elevado</code>, <code>Médio Porte</code></td><td>Contrapartes PJ com ramo, porte e faturamento anual coerentes.</td></tr>
<tr><td><code>uma delas é PEP / sócia de empresa / tem mídia negativa</code></td><td>Sinal = Sim na contraparte e pergunta do detalhe. <b>Sem menção, tudo "Não"</b>; registro profissional e societário nunca são inventados.</td></tr>
<tr><td><code>3 contrapartes são PEP</code></td><td>Uma contraparte para cada, com PEP marcado.</td></tr>
</table>
<p><b>Outras movimentações</b> (o que não for transferência bancária comum). Cite o tipo e o valor, e o Sentinela cria a linha certa:</p>
<table>
<tr><th>Termos</th><th>Tipo no formulário</th></tr>
<tr><td>saque, sacou, caixa eletrônico</td><td>Saques</td></tr>
<tr><td>boleto</td><td>Boletos</td></tr>
<tr><td>cartão de crédito, fatura</td><td>Gastos Cartão de Crédito</td></tr>
<tr><td>cartão de débito, compras no débito</td><td>Gastos Cartão de Débito</td></tr>
<tr><td>empréstimo, consignado, financiamento</td><td>Empréstimos</td></tr>
<tr><td>cripto, bitcoin, BTC, USDT</td><td>Criptomoedas</td></tr>
<tr><td>investimento, CDB, Tesouro, renda fixa, ações</td><td>Investimentos</td></tr>
</table>

<h3>5. Gerar e consultar o dossiê</h3>
<ol>
<li>No fim do formulário, clique em <b>Gerar dossiê do caso</b>. Se faltar campo obrigatório, o Sentinela lista quais.</li>
<li>O dossiê é salvo no <b>Banco de dossiês</b> e (quando ativada) gravado na base de casos. Baixe o PDF ou abra o dossiê.</li>
<li>Preencha <b>Resolução do Caso</b> e <b>Avaliação de Qualidade</b> na própria tela do dossiê e use <b>Salvar</b>.</li>
<li>Para voltar a um caso, use o <b>Banco de dossiês</b>.</li>
</ol>

</div>
"""

# Tutoriais animados (GIF) passo a passo: (título, arquivo dentro de VIDEOS_DIR). Só aparecem os arquivos que existirem.
VIDEOS_DIR = Path(__file__).parent / "videos"
VIDEOS = (
    ("1. Iniciar um caso e escolher o modo", "01_iniciar_caso.gif"),
    ("2. Preencher o KYC", "02_kyc.gif"),
    ("3. Preencher as Movimentações", "03_movimentacoes.gif"),
    ("4. Preencher os Comportamentos", "04_comportamentos.gif"),
    ("5. Revisar, gerar e consultar o dossiê", "05_gerar_dossie.gif"),
)


def tela_manual() -> None:
    from estilo import titulo_cartao
    titulo_cartao("Manual do usuário", "SENTINELA", pequeno=True,
                  descricao_normal="Como criar um dossiê, passo a passo.")
    st.html("<style>" + CSS_MANUAL + "</style>" + MANUAL_HTML)
    existentes = [(t, VIDEOS_DIR / a) for t, a in VIDEOS if (VIDEOS_DIR / a).is_file()]
    if existentes:
        st.html("<style>" + CSS_MANUAL + "</style><div class='sx-man'><h3>6. Tutoriais passo a passo (animados)</h3></div>")
        for titulo, arq in existentes:
            st.caption(titulo)
            st.image(str(arq))
