# Sentinela PLD — Databricks App

Port em Python (Streamlit) do Sentinela PLD, originalmente um artefato
HTML/JS. Gera dossiês de análise PLD/AML padronizados, com preenchimento
automático via IA, geração de PDF no servidor e um Banco de Dossiês
persistente e compartilhado pelo time.

---

## 1. Conteúdo do pacote

| Arquivo | O que é | Precisa editar? |
|---|---|---|
| `app.py` | Fluxo das telas (Streamlit): home, tipo de caso, modo, preenchimento por IA, formulário, dossiê com 3 abas e Banco. | Não |
| `core.py` | Modelo de dados, nota de qualidade, risco geral, narrativa de mudança de comportamento, gráfico e Banco de Dossiês. | Não |
| `ia.py` | Preenchimento automático por IA: prompts, regras, normalização e coerência dos dados. | Não |
| `pdf_dossie.py` | PDF do dossiê (Informações + Resolução + Avaliação). | Não |
| `dossie_html.py` | Aba "Informações do Caso" em HTML (pílulas, contrapartes, gráfico). | Não |
| `opcoes.py` | Razões, jurisprudências, diligências e as rubricas AML Nupag / AML NuInvest. | Só se as regras mudarem |
| `estilo.py` | Todo o visual: paleta, fontes, cartões, botões, abas e arte de fundo. | Só para mudar o design |
| `.streamlit/config.toml` | Tema base (cores) do Streamlit. | Não |
| `requirements.txt` | Dependências Python. | Não |
| `app.yaml` | Manifesto do Databricks App. | **Sim** (ver passo 5) |
| `tests/` | Testes automatizados (ver passo 10). | Não |

Todos os arquivos `.py`, o `app.yaml` e a pasta `.streamlit/` ficam na **raiz** do app.

---

## 2. Pré-requisitos

- Workspace Databricks com **Databricks Apps** habilitado.
- Permissão para criar um **Volume** no Unity Catalog (armazenamento).
- Permissão para criar **Secrets** (só se for usar o preenchimento por IA).
- Databricks CLI instalado, se for subir por linha de comando:
  `pip install databricks-cli` e depois `databricks configure`.

---

## 3. Criar o armazenamento (Unity Catalog Volume)

O Banco de Dossiês grava os casos (JSON) e os PDFs em disco. Para que eles
**persistam** entre reinícios do app e sejam compartilhados pelo time, use
um Volume do Unity Catalog. Em um notebook ou no SQL Editor:

```sql
CREATE SCHEMA IF NOT EXISTS main.sentinela;
CREATE VOLUME IF NOT EXISTS main.sentinela.dossies;
```

Isso cria o caminho `/Volumes/main/sentinela/dossies`. Ajuste
`main.sentinela` para o catálogo/schema que seu time usa.

> Sem um Volume, o app ainda funciona, mas grava em disco efêmero — os
> dossiês somem quando o app reinicia. Não use assim em produção.

Dê ao app permissão de leitura e escrita no Volume:

```sql
GRANT READ VOLUME, WRITE VOLUME ON VOLUME main.sentinela.dossies TO `<service-principal-do-app>`;
```

O service principal do app aparece na aba **Authorization** do app depois de
criá-lo (passo 5).

---

## 4. Configurar o acesso à IA (opcional)

Necessário **apenas** para o botão "Preencher com Instruções (Automático)".
Todo o resto do app funciona sem isso.

O app suporta dois cenários. Escolha o que se aplica à sua empresa.

### Cenário A — Proxy LiteLLM corporativo (provável no Nubank)

Se o seu time já fornece um proxy LiteLLM, use a key dele e aponte a base URL:

```bash
export ANTHROPIC_API_KEY=<sua key do LiteLLM>
export ANTHROPIC_BASE_URL=https://<endereco-do-litellm-da-empresa>
export SENTINELA_LLM_MODELO=anthropic/claude-sonnet-4-6
```

Pontos importantes:

- Uma key do LiteLLM **não funciona** em `api.anthropic.com` — é isso que
  causa o erro `401 Unauthorized`. É obrigatório definir `ANTHROPIC_BASE_URL`.
- Por padrão, com uma base URL que não seja a da Anthropic, o app usa a rota
  compatível com OpenAI (`/v1/chat/completions`), que é a que todo LiteLLM
  expõe. Se o seu proxy usar a rota de passthrough da Anthropic, defina
  `SENTINELA_LLM_FORMATO=anthropic` para usar `/v1/messages`.
- O **nome do modelo** no proxy pode ser diferente do nome oficial. Peça ao
  time a lista de modelos disponíveis e ajuste `SENTINELA_LLM_MODELO`.

### Cenário B — API da Anthropic direta

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

A key oficial começa com `sk-ant-`, é gerada em
`console.anthropic.com/settings/keys` e exige billing/créditos na conta.
Não defina `ANTHROPIC_BASE_URL` nesse caso.

### Guardando a credencial no Databricks

Nunca coloque a key no código nem no `app.yaml`:

```bash
databricks secrets create-scope sentinela
databricks secrets put-secret sentinela anthropic-api-key
```

### Referência das variáveis

| Variável | Para que serve | Padrão |
|---|---|---|
| `ANTHROPIC_API_KEY` | Credencial (Anthropic ou LiteLLM). | — |
| `ANTHROPIC_BASE_URL` | Endereço do serviço. Defina para usar um proxy. | `https://api.anthropic.com` |
| `SENTINELA_LLM_FORMATO` | `openai` ou `anthropic`. | `anthropic` se a base for a oficial, senão `openai` |
| `SENTINELA_LLM_MODELO` | Nome do modelo. | `claude-sonnet-4-6` |

## 5. Editar o `app.yaml`

```yaml
command:
  - "streamlit"
  - "run"
  - "app.py"

env:
  - name: "SENTINELA_DATA_DIR"
    value: "/Volumes/main/sentinela/dossies"
  - name: "ANTHROPIC_API_KEY"
    valueFrom: "anthropic-api-key"
  - name: "ANTHROPIC_BASE_URL"
    value: "https://litellm.data.nubank.world"
  - name: "SENTINELA_LLM_MODELO"
    value: "claude-sonnet-4-6"
```

Ajuste:
- `SENTINELA_DATA_DIR` → o caminho do Volume criado no passo 3.
- `valueFrom` → o nome da secret criada no passo 4.
- `ANTHROPIC_BASE_URL` → o endereço do seu proxy LiteLLM. **Remova essa linha**
  se for usar a API da Anthropic direta.
- Remova os três blocos de IA se não for usar o preenchimento automático.

---

## 6. Publicar

**Pela interface:** Compute → Apps → Create App → template **Custom** →
faça upload dos arquivos da raiz (incluindo a pasta `.streamlit/`) → Deploy.

**Pela CLI:**

```bash
databricks apps create sentinela-pld
databricks sync . /Workspace/Users/<seu-email>/sentinela-pld
databricks apps deploy sentinela-pld \
  --source-code-path /Workspace/Users/<seu-email>/sentinela-pld
```

O Databricks instala o `requirements.txt` e inicia o Streamlit sozinho.

---

## 7. Testar localmente antes de subir (recomendado)

Use **Python 3.11** — é a versão do runtime do Databricks Apps, e versões
muito novas (3.13/3.14) ainda não têm pacotes pré-compilados para algumas
dependências, o que faz o `pip install` tentar compilar e falhar.

```bash
# macOS
brew install python@3.11
/opt/homebrew/bin/python3.11 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

export SENTINELA_DATA_DIR=./data
export ANTHROPIC_API_KEY=sk-ant-...   # opcional

streamlit run app.py
```

Abre em `http://localhost:8501`. Para sair do venv: `deactivate`.

---

## 8. Como usar o app

1. **Iniciar novo caso** → escolha o tipo (PF, PJ, Cripto, NuInvest, Under 18).
2. Escolha **Preencher com instruções (automático)** ou **Preencher manualmente**.
   No automático você digita **Nome do alerta, Data do alerta e Sentença** (a IA nunca
   preenche esses três), cola o resumo do caso e, se quiser, as movimentações não
   bancárias (saques, boletos, cartões etc., que só entram pelo campo próprio).
3. Revise os 4 blocos: Alerta/Sentença, KYC, Resumo de Movimentações, Thundera/AML 360.
   O formulário lista os campos obrigatórios que faltarem.
4. **Gerar dossiê do caso** → grava no Banco (JSON + PDF) e mostra a prévia.
5. **Dossiê** (3 abas): *Informações do Caso* (somente leitura), *Resolução do Caso*
   (parecer, alíneas, jurisprudências, razões de clear/cancelamento e diligência; cada
   seção tem o próprio Salvar e "Salvar informações do caso" trava a aba) e *Avaliação de
   Qualidade* (rubrica pelo tipo do caso; nota por categoria).
6. **Banco de Dossiês**: busca por trecho do número (sem diferenciar maiúsculas) ou
   consulta completa; clique para abrir. Resolução e Avaliação **ficam gravadas** no caso.
7. PDFs: *PDF completo (3 abas)* no topo do dossiê; *Baixar versão atualizada em PDF* na
   Resolução (Informações + Resolução, liberado após salvar o caso) e na Avaliação (só a aba).

---

## 9. Diferenças em relação ao artefato original

**Corrigido nesta versão** (divergências listadas no manual, seção 13):

| Antes | Agora |
|---|---|
| Nota descontava por critério marcado | Desconta **por categoria** (uma vez), Regulatory zera, Business Intelligence não desconta |
| Rubrica escolhida à mão | Definida pelo tipo do caso (NuInvest → AML NuInvest; demais → AML Nupag) |
| Instruções da IA simplificadas | Regras completas: invenção autorizada, profissão informada x registro profissional, 3 a 5 contrapartes principais, percentuais/valores coerentes, termos vagos viram números, outras movimentações só pelo campo próprio |
| Diligência com 3 opções | 4 opções (Clear, Reportar, Reportar e Cancelar, Cancelar), selo colorido |
| Risco olhava só PEP, região e sócios | Considera também históricos, mídia negativa, contrapartes, Thundera e compatibilidade com a renda/faturamento; os fatores aparecem no dossiê |
| Narrativa usava o mês de pico informado | Pico no 1º mês do período; 5 meses anteriores com os valores-base do original |
| Resolução e Avaliação não eram incluídas no PDF do dossiê | PDF completo traz as 3 abas e é regerado a cada salvamento |

**PDF:** gerado no servidor (reportlab), com gráfico, selo e rodapé; escopos *completo*,
*resolução* e *avaliação*.

**Armazenamento:** arquivos JSON + PDF no Volume do Unity Catalog. Gravações simultâneas
do índice não se perdem (trava de arquivo, escrita atômica) e um índice corrompido é
reconstruído a partir dos `caso_*.json`. A classe `ArmazenamentoLocal` pode ser trocada por
uma tabela Delta mantendo a mesma interface pública.

**Design:** fiel às capturas do manual (paleta, Montserrat / Source Serif 4 / IBM Plex,
cartões com sombra deslocada, carimbo, botões com efeito de pressionar, selects roxos,
abas sublinhadas, robôs ao fundo). Os robôs e o cabo da home são imagens SVG dentro do CSS,
porque o `st.html` remove `<svg>`.

**Diferenças deliberadas** em relação ao artefato:
- O preenchimento por IA leva ao formulário para **revisão** antes de gerar (o artefato gerava
  o dossiê direto, sem pausa).
- Seções salvas da Resolução têm o link **Editar**, e o caso travado tem **Reabrir para
  edição** (no artefato o bloqueio durava só a sessão; aqui os dados persistem).
- Arredondamento e Pix aceitam várias linhas vindas da IA (antes, uma de cada).
- No Bloco 3, os seis selects do mini-KYC das contrapartes ficam em duas linhas de três.

---

## 10. Testes

```bash
./venv/bin/python -m unittest discover -s tests -t . -v        # 100+ testes, sem rede
```

| Arquivo | O que cobre |
|---|---|
| `tests/test_core.py` | Nota por categoria, risco, narrativa, gráfico, validação, e o **Banco de Dossiês** (criar → gravar → buscar → abrir; ordem; concorrência; índice corrompido; número malformado) |
| `tests/test_ia.py` | Prompts e regras da IA contra um servidor HTTP fake (formatos openai e anthropic, 401/404, resposta cortada, retentativa, normalização, coerência, campos neutros) |
| `tests/test_pdf.py` | PDF por escopo (completo, resolução, avaliação), escape de texto, casos vazios/PJ/Under 18 |
| `tests/test_app.py` | Telas via `AppTest`: navegação, os 5 tipos, validação, sócios, gênero ambíguo, Resolução, Avaliação, IA, Banco |
| `tests/e2e_playwright.py` | Navegador real (opcional; precisa de `playwright` e `pypdf` num venv à parte): cria o caso, grava, busca, abre, salva Resolução/Avaliação, recarrega e confere o PDF |

Os testes de PDF só conferem o texto se `pypdf` estiver instalado.

---

## 11. Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| CSS aparece como texto na tela | Uso de `st.markdown` para HTML | Já corrigido: todo HTML passa por `st.html()`. Se reintroduzir, use `st.html()`. |
| Dossiês somem ao reiniciar | `SENTINELA_DATA_DIR` não aponta para um Volume | Corrija no `app.yaml` (passo 5). |
| "ANTHROPIC_API_KEY não configurada" | Secret ausente ou não vinculada | Passos 4 e 5. |
| `401 Unauthorized` em api.anthropic.com | Key de proxy (LiteLLM) usada contra a API oficial | Defina `ANTHROPIC_BASE_URL` com o endereço do proxy (passo 4, cenário A). |
| `404` no endpoint da IA | Formato de rota errado para o seu proxy | Alterne `SENTINELA_LLM_FORMATO` entre `openai` e `anthropic`. |
| Erro de modelo inexistente | O proxy usa outro nome de modelo | Ajuste `SENTINELA_LLM_MODELO` com um nome que o proxy aceite. |
| `pip install` falha compilando matplotlib | Python muito novo (3.13/3.14) | Use Python 3.11 (passo 7). |
| `ModuleNotFoundError: core` | Arquivos renomeados (ex: `core (1).py`) | Os nomes devem ser exatamente `app.py`, `core.py`, `opcoes.py`, `estilo.py`. |
| Permission denied ao gravar | Service principal sem acesso ao Volume | Rode o `GRANT` do passo 3. |
| Estilo quebrado após atualizar Streamlit | Seletores internos (`data-testid`) mudaram | Mantenha `streamlit==1.38.0` ou ajuste os seletores em `estilo.py`. |
