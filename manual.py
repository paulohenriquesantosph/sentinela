"""Manual do usuário do Sentinela: passo a passo para criar um dossiê (HTML estático)."""
from __future__ import annotations

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
.sx-man pre{ font-family:var(--mono); font-size:12.5px; background:rgba(25,21,31,.06); border-radius:8px;
  padding:10px 12px; margin:8px 0; white-space:pre-wrap; }
"""

MANUAL_HTML = """
<div class="sx-man">

<p>Este manual mostra, passo a passo, como criar um dossiê no Sentinela — da home até o PDF final.</p>

<h3>1. Iniciar um novo caso</h3>
<ol>
  <li>Na home, clique em <b>Iniciar novo caso</b>.</li>
  <li><b>Etapa 1 de 2:</b> escolha o tipo de caso: <b>Pessoa Física (PF)</b>, <b>Pessoa Jurídica (PJ)</b>,
      <b>Cripto</b>, <b>NuInvest</b> ou <b>Under 18</b>. O tipo muda alguns campos do formulário
      (por exemplo, PJ pede dados da empresa e dos sócios; Under 18 pede o responsável legal).</li>
  <li><b>Etapa 2 de 2:</b> escolha como preencher:
    <ul>
      <li><b>Preencher com instruções (automático):</b> você informa nome do alerta, data, sentença e cola um
          resumo do caso; o Sentinela tenta preencher o formulário sozinho (veja a seção 2).</li>
      <li><b>Preencher manualmente:</b> abre o formulário em branco.</li>
    </ul></li>
</ol>

<div class="sx-man-aviso"><b class="t">Importante</b>
Se usar o preenchimento automático, <b>revise tudo</b> no formulário antes de gerar o dossiê. Os campos
preenchidos pela IA podem estar incompletos ou incorretos.</div>

<h3>2. Preenchimento por instruções (automático)</h3>
<p>Nesta tela você descreve o caso em texto livre e o Sentinela preenche o formulário. Depois, ele abre o
formulário já preenchido para você revisar. Os campos da tela são:</p>
<ul>
  <li><b>Nome do alerta*</b>, <b>Data do alerta*</b> e <b>Sentença*</b>: <b>sempre digitados por você</b>.
      O automático nunca os preenche nem os altera.</li>
  <li><b>Resumo do caso*</b>: o texto principal. Cole ou escreva tudo o que se sabe sobre o cliente (KYC),
      as movimentações, as contrapartes e o comportamento. Quanto mais específico, melhor.</li>
  <li><b>Outras movimentações</b> (opcional): só para movimentações que <b>não</b> sejam transferências
      bancárias comuns: saques, boletos, gastos no cartão de crédito ou débito, empréstimos, criptomoedas,
      investimentos. Este campo é a <b>única fonte</b> da seção “Outras movimentações”: o que estiver só no
      Resumo não vai para ela.</li>
</ul>

<p><b>O que o Sentinela preenche a partir do Resumo</b> (só entra o que o texto afirma):</p>
<ul>
  <li><b>KYC do cliente (PF, Cripto, NuInvest, Under 18):</b> nome, idade, cidade/estado, última atualização
      cadastral, <b>profissão informada</b>, <b>renda presumida</b> (ex.: “renda de R$ 3.500”), registro
      profissional e registro societário (razão social, data de abertura, situação cadastral e ramo).
      O gênero é inferido pelo primeiro nome; se o nome for ambíguo, o formulário pergunta.</li>
  <li><b>KYC da empresa (PJ):</b> inclua no Resumo o <b>Nome da Empresa, Data de Abertura, Ramo de
      Atividade, Porte, Faturamento Presumido, Endereço, Fachada e Presença Online</b>. Fachada e Presença
      Online vão para o formulário apenas como <b>Sim</b> ou <b>Não</b> (não há campo de detalhe). Os
      <b>sócios</b> só entram se você citar (nome, idade, endereço, renda, patrimônio e os Sim/Não de risco),
      exceto quando você disser que mais de um sócio tem o mesmo sinal (ex.: “2 sócios são PEP”): aí o
      Sentinela cria um sócio para cada um.</li>
  <li><b>Under 18:</b> dados do responsável legal, se o texto falar dele.</li>
  <li><b>Riscos (Sim/Não e detalhe):</b> região de risco (fronteira, extração mineral/madeira ou outra), PEP
      (titular ou relacionado, com descrição e carência), mídia negativa, histórico de PLD e de fraudes.
      Veja o quadro “Perguntas do KYC” abaixo.</li>
  <li><b>Outras informações relevantes:</b> qualquer informação adicional de KYC que o resumo trouxer e que
      não tenha campo próprio (compartilhamento de dispositivo, redes sociais, processos, dados de
      NuInvest/Crypto e outras informações não convencionais). O Sentinela coloca <b>uma informação por
      linha</b>. Veja a seção 4.</li>
  <li><b>Resumo de movimentações:</b> período (<code>DD/MM/AAAA até DD/MM/AAAA</code>), <b>total de créditos</b>
      e <b>total de débitos</b>, e <b>número total de contrapartes</b> de cada lado.</li>
  <li><b>Contrapartes:</b> para cada uma, o tipo (PF ou PJ), a <b>porcentagem</b>, o <b>valor</b>, o
      <b>número de transações</b> e seus dados (nome, idade ou data de abertura, cidade/estado, renda ou
      faturamento presumido, profissão ou ramo, porte) com o mini-KYC (Sim/Não de registro societário,
      região de risco, PEP, PLD, fraude e mídia negativa). Quando faltar informação no mini-KYC, fica “Não”.</li>
  <li><b>Thundera / AML 360:</b>
    <ul>
      <li><b>Arredondamento:</b> uma linha por valor de referência (R$ 1.000, R$ 2.000, R$ 5.000...), com a
          quantidade de transações, separando créditos e débitos.</li>
      <li><b>Mensagens Pix:</b> uma linha por grupo de mensagens, com a quantidade e um exemplo da mensagem.</li>
      <li><b>Timeline de transferências:</b> “Rápida Evasão” ou “Sem Rápida Evasão”, se o texto disser.</li>
      <li><b>Mudança de comportamento:</b> veja o quadro “Mudança de comportamento” abaixo.</li>
      <li><b>Data de abertura da conta / último reporte.</b></li>
    </ul></li>
  <li><b>Outras movimentações:</b> a partir do campo próprio, classificadas como Saques, Boletos, Gastos
      Cartão de Crédito/Débito, Empréstimos, Criptomoedas, Investimentos ou Outros.</li>
</ul>

<p><b>Como escrever o Resumo para o automático acertar</b></p>
<ul>
  <li><b>Valores:</b> use números claros: “crédito total de R$ 500.000,00”, “renda de R$ 2.800”.</li>
  <li><b>Porcentagens e transações por contraparte:</b> “João Silva (PF, 35 anos, São Paulo/SP) concentrou
      40% dos créditos, R$ 200.000,00, em 23 transações”.</li>
  <li><b>Muitas contrapartes:</b> informe o total (“120 contrapartes de crédito”) e descreva só as 3 a 5
      principais. O restante o dossiê calcula como “demais contrapartes”.</li>
  <li><b>Profissão:</b> escreva “cliente declarou ser <i>X</i>” para a <b>profissão informada</b>. O que o
      analista constatou (ex.: “consta como motorista de aplicativo”) vai para o <b>registro
      profissional</b>. Em caso de dúvida, o Sentinela coloca no registro profissional.</li>
  <li><b>Período:</b> “de 01/06/2026 até 01/08/2026”. Sem período, o Sentinela usa um período padrão.</li>
  <li><b>Concentração:</b> se não houver menção a concentração, nenhuma contraparte passa de 50% do total.
      Se houver (“alta concentração em X”), a principal fica acima de 50%.</li>
  <li><b>Termos vagos:</b> “diversas”, “várias” e “muitas” viram um número plausível (ex.: 12), nunca a
      palavra. Prefira dar o número real.</li>
  <li><b>Contrapartes aleatórias:</b> se quiser que o Sentinela crie o que faltar, escreva “aleatório”,
      “invente” ou “à sua escolha”, junto com o perfil desejado. Ele cria nomes, idades, cidades, rendas e
      cargos <b>respeitando a sua instrução</b>. Exemplo: “diversas pessoas físicas, sem capacidade
      financeira elevada” gera contrapartes com <b>renda presumida baixa</b>, variada e coerente com o
      cargo. Se você não disser as profissões, ele cria <b>cargos aleatórios</b> compatíveis com o perfil.
      Sem essa autorização, ele não inventa nada.</li>
</ul>

<div class="sx-man-aviso"><b class="t">Perguntas do KYC</b>
Quando o Resumo indica <b>Sim</b> em um item do KYC, o Sentinela marca <b>Sim</b> no formulário e preenche
os detalhes que o texto trouxer. Se o <b>Sim</b> vier <b>sem</b> os detalhes, o Sentinela não abre o
formulário ainda: ele mostra só as perguntas que faltaram, e depois de respondidas você clica em
<b>Continuar</b>. Os itens são:
<ul>
  <li><b>Registro societário</b> (PF): razão social, data de abertura, situação cadastral e ramo de
      atividade.</li>
  <li><b>Região de risco:</b> cidade/estado (vai para o campo Cidade/Estado do KYC), o risco da região e,
      se for “Outras Regiões de Risco”, qual é a região.</li>
  <li><b>PEP:</b> tipo de PEP e descrição do PEP e carência.</li>
  <li><b>Mídia negativa:</b> qual é a mídia (link, se houver), data e fonte.</li>
  <li><b>Histórico de PLD</b> e <b>Histórico de fraude:</b> os detalhes de cada um.</li>
</ul>
Isso vale também para os <b>sócios</b> (caso PJ): região de risco (e o risco da região), PEP (tipo e
descrição/carência), mídia negativa, histórico de PLD e de fraude, sócio por sócio.
<br/><br/>E vale para as <b>contrapartes</b> do Bloco 3: se o Resumo disser que uma contraparte é sócia de
empresa (registro societário), é PEP, tem mídia negativa, histórico de PLD, histórico de fraude ou região de
risco, o Sentinela marca <b>Sim</b> nela e pergunta os detalhes, contraparte por contraparte. Se o Resumo
disser que <b>mais de uma</b> contraparte tem o mesmo sinal (por exemplo, “3 contrapartes são PEP”), o
Sentinela <b>cria uma contraparte para cada uma</b>, com o sinal marcado, e pergunta os detalhes de cada
uma.
<br/><br/>Para evitar a pergunta, já escreva esses dados no Resumo. Para mudar o Resumo depois de ver as perguntas,
use <b>Refazer com outro resumo</b>.</div>

<div class="sx-man-aviso"><b class="t">Mudança de comportamento</b>
Se o Resumo disser que houve mudança de comportamento, aparecem campos extras na tela e o preenchimento só
continua depois de você respondê-los. As movimentações são descritas em <b>6 meses</b>: o último é o
<b>mês do alerta</b> (o mês da mudança) e os outros 5 são os <b>meses anteriores</b> à data do alerta. Você
não precisa informar os meses; basta preencher:
<ul>
  <li><b>Valor do mês da mudança</b> (opcional): se você não informar, o Sentinela cria um valor elevado,
      sempre <b>abaixo do total movimentado no período do alerta</b>. Se você informar um valor maior que
      o total, o formulário mostra um aviso.</li>
  <li><b>Abertura da conta e/ou último reporte</b> (<code>DD/MM/AAAA</code>): obrigatório, e precisa ser
      <b>anterior à data do alerta</b>.</li>
</ul>
Nos 5 meses anteriores, o Sentinela usa valores baixos de referência; só o mês do alerta recebe o valor
elevado.</div>

<div class="sx-man-aviso"><b class="t">Exemplo de Resumo</b>
<pre>Cliente Maria Souza, 34 anos, Recife/PE, declarou ser professora com renda de R$ 3.200.
Consta registro como sócia de microempresa de comércio. Sem PEP, sem mídia negativa.
Período de 01/06/2026 até 01/08/2026. Créditos totais de R$ 480.000,00 de 60 contrapartes;
principal: Carlos Lima (PF), 30%, R$ 144.000,00, 18 transações. Débitos totais de R$ 470.000,00
de 15 contrapartes. 84 transações em múltiplos de R$ 1.000,00 nos créditos.
Mudança de comportamento com pico aproximado de R$ 120.000,00.</pre></div>

<div class="sx-man-aviso"><b class="t">Depois de preencher</b>
O Sentinela completa campos obrigatórios que o texto não informou com “Não informado” (ou R$ 0,00 em
valores) e mostra avisos no topo do formulário quando algo não bate (por exemplo, porcentagens que somam
mais de 100%). <b>Revise todos os campos</b> e corrija antes de clicar em Gerar dossiê.</div>

<h3>3. Preencher o formulário (manual ou revisão)</h3>
<p>Campos com <b>*</b> são obrigatórios. O formulário é dividido em blocos:</p>
<ul>
  <li><b>Bloco 1 — Alerta / Sentença:</b> fator gerador do alerta, data do alerta e descrição da sentença.</li>
  <li><b>Bloco 2 — KYC:</b> dados cadastrais do cliente (ou da empresa, no caso PJ), região de risco, PEP,
      mídia negativa, histórico de PLD e de fraudes. Ao marcar <b>Sim</b> em um item, aparece um campo para
      detalhar. No fim do bloco fica o campo <b>Outras informações relevantes</b> (veja a seção 4).</li>
  <li><b>Bloco 2.1 — Sócios (só PJ):</b> use <b>+ Adicionar sócio</b> para cada sócio e <b>Remover</b> para
      apagar o último.</li>
  <li><b>Bloco 3 — Resumo de movimentações:</b> período analisado, créditos e débitos com suas contrapartes e,
      opcionalmente, <b>Outras movimentações</b> (saques, boletos, cartão, empréstimos, cripto, investimentos).</li>
  <li><b>Bloco 4 — Thundera / AML 360:</b> arredondamento de valores, mensagens Pix, timeline de transferências,
      mudança de comportamento e data de abertura da conta/último reporte.</li>
</ul>

<h3>4. Casos NuInvest, Crypto e outras análises específicas</h3>
<div class="sx-man-aviso"><b class="t">Atenção — informações fora do KYC padrão</b>
Nos casos <b>NuInvest</b>, <b>Crypto</b> ou qualquer outra análise específica que tenha informações
diferentes das informações de KYC padrão, <b>é necessário adicionar essas informações, uma por linha,
no campo “Outras informações relevantes”</b> (Bloco 2 — KYC). O formulário não tem campos próprios para
esses dados: o que não for colocado ali não aparece no dossiê.</div>
<p>Como fazer:</p>
<ol>
  <li>Vá até o fim do Bloco 2 e clique no campo <b>Outras informações relevantes</b>.</li>
  <li>Escreva <b>uma informação por linha</b> (use Enter para pular de linha), de preferência no formato
      <code>Rótulo: valor</code>.</li>
  <li>Inclua apenas informações que não tenham campo no KYC padrão.</li>
</ol>
<p>Exemplo (NuInvest):</p>
<pre>Perfil de investidor: Arrojado
Produtos operados: Ações, opções e fundos
Patrimônio declarado na corretora: R$ 250.000,00
Operações atípicas: aportes seguidos de resgate em até 2 dias</pre>
<p>Exemplo (Crypto):</p>
<pre>Exchange / carteira: Binance
Ativos negociados: BTC, USDT
Volume movimentado no período: R$ 480.000,00
Origem dos recursos: transferências de terceiros via Pix</pre>
<p>Redes sociais, processos e compartilhamento de dispositivo também entram nesse mesmo campo.</p>

<h3>5. Gerar o dossiê</h3>
<ol>
  <li>No fim do formulário, clique em <b>Gerar dossiê do caso</b>.</li>
  <li>Se faltar algum campo obrigatório, o Sentinela lista quais são — corrija e gere de novo.</li>
  <li>Com o dossiê gerado, aparecem a confirmação de que ele foi salvo no <b>Banco de Dossiês</b>, o botão
      para abrir o dossiê e o botão <b>Baixar PDF do dossiê</b>.</li>
</ol>

<h3>6. Trabalhar com o dossiê</h3>
<p>O dossiê tem três abas:</p>
<ul>
  <li><b>Informações do Caso:</b> tudo o que foi preenchido no formulário.</li>
  <li><b>Resolução do Caso:</b> parecer final do analista, alíneas específicas e diligência, preenchidos
      depois da geração.</li>
  <li><b>Avaliação de Qualidade:</b> avaliação do caso durante a calibração.</li>
</ul>
<p>O dossiê traz <b>somente as informações do caso</b>: ele não classifica o risco do caso nem lista fatores
de risco. A classificação de risco é feita pelo analista na resolução, durante a calibração. Da mesma forma,
a Timeline de Transferências mostra apenas os valores de créditos e débitos e o gráfico, e os valores
movimentados mês a mês aparecem sem indicar se houve ou não mudança de comportamento.</p>
<p>Use <b>PDF completo (3 abas)</b> no topo do dossiê para baixar tudo em um só arquivo.</p>

<h3>7. Encontrar dossiês depois</h3>
<p>Na home, clique em <b>Banco de dossiês</b> para buscar, abrir ou reabrir casos já gerados.</p>

</div>
"""


def tela_manual() -> None:
    from estilo import titulo_cartao
    titulo_cartao("Manual do usuário", "SENTINELA", pequeno=True,
                  descricao_normal="Como criar um dossiê, passo a passo.")
    st.html("<style>" + CSS_MANUAL + "</style>" + MANUAL_HTML)
