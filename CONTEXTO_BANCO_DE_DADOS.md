# Sentinela PLD — contexto da implementação do banco de dados

Documento para outro agente do Claude entender rapidamente o estado atual da base de casos. Estado do código em
`main`, commit `5930db0` ("Base de casos em Unity Catalog…"). Detalhes para usuários: `README.md` seção 3.1.

## 1. O que é e por quê

O Sentinela é um app **Streamlit** (rodando como Databricks App) que gera **dossiês de casos de PLD/AML**
(tipos: Pessoa Física, PJ, Cripto, NuInvest, Under 18). Antes, os dossiês ficavam só em arquivos (JSON + PDF) no
"Banco de Dossiês" (`SENTINELA_DATA_DIR`, um Volume do Unity Catalog; localmente `./data`).

A base de casos foi adicionada para que as pessoas **consultem os casos por tipo** e os levem a calibrações com seus
times. Os arquivos continuam sendo a fonte primária; a base é uma cópia consultável.

## 2. Regras de negócio que NÃO podem ser quebradas

1. **Só o dossiê gerado é gravado** ("Informações do Caso": alerta, KYC, movimentações, comportamentos AML 360).
2. **Resolução do Caso e Avaliação de Qualidade NUNCA vão para a base.** Continuam sendo preenchidas no app, na
   calibração. Salvar Resolução/Avaliação depois **não** grava nada.
   - Campos excluídos: `esquema_sql.EXCLUIDOS_CASOS` e `esquema_sql.NAO_GRAVADOS_LISTAS`.
   - `gravacao_sql.dossie_sem_resolucao()` zera esses campos antes de gravar (inclusive no `caso_json`).
3. **Texto do usuário nunca entra no SQL**: vai como **parâmetro** (um JSON com as linhas de cada tabela, lido no
   SQL por `from_json`). Não montar SQL com texto livre.
4. **Falha na gravação nunca derruba o app**: o dossiê segue salvo nos arquivos, o analista vê um aviso e o botão
   "Tentar gravar na base novamente".
5. A gravação é **opcional**: só roda com `SENTINELA_SQL_WAREHOUSE_ID` definida. Sem ela, nada vai ao Databricks.

## 3. Arquivos

| Arquivo | Papel |
|---|---|
| `esquema_sql.py` | Gera o DDL (tabelas Delta + views) **a partir das dataclasses de `core.py`**. CLI: imprime o DDL ou aplica (`--aplicar --warehouse <id> [--perfil <p>]`). Usa `CREATE TABLE IF NOT EXISTS` e `CREATE OR REPLACE VIEW` (não apaga dados). |
| `gravacao_sql.py` | Converte o `Caso` em linhas, gera INSERT/DELETE parametrizados, grava via Databricks SDK, e migra casos antigos. |
| `app.py` | Integra: em `_gerar_dossie` marca `ss.sql_pendente`; em `tela_formulario` chama `_gravar_na_base` (spinner) e mostra ok/erro + botão de nova tentativa (`_regravar_sql`, com `sql_limpar=True`). |
| `app.yaml` | Variáveis de ambiente (bloco da base está **comentado**, a ativar). |
| `tests/test_esquema_sql.py`, `tests/test_gravacao_sql.py`, `tests/test_app.py` | Testes do esquema, da gravação (com executor falso) e da integração no app. |

## 4. Modelo de dados (`usr.sentinela_aml`, catálogo/schema configuráveis)

Uma linha por caso em `casos`; listas ficam em tabelas filhas ligadas por `numero_caso`, todas repetindo
`tipo_caso` para filtrar sem JOIN.

| Tabela | Conteúdo | Chave |
|---|---|---|
| `casos` | campos escalares do Caso + colunas derivadas tipadas + `caso_json` + `gravado_em` | `numero_caso` |
| `contrapartes` | contrapartes de crédito/débito (Bloco 3) com mini-KYC (`lado`) | `numero_caso, lado, ordem` |
| `socios` | sócios (PJ) | `numero_caso, ordem` |
| `outras_movimentacoes` | saques, boletos, cripto… com montante extraído | `numero_caso, ordem` |
| `arredondamentos` | transações em perfil de arredondamento (Bloco 4) | `numero_caso, ordem` |
| `mensagens_pix` | mensagens Pix (Bloco 4) | `numero_caso, ordem` |
| `timeline_diaria` | série diária dos gráficos (bancária e cripto) | `numero_caso, timeline, data` |

**Views por tipo** (só as colunas relevantes ao tipo): `casos_pf`, `casos_pj`, `casos_cripto` (PF + grupo cripto),
`casos_nuinvest`, `casos_under18` (PF + grupo representante). Definidas em `esquema_sql.VIEWS` e nos grupos
`GRUPO_PF/PJ/UNDER18/CRIPTO`.

**Convenções de colunas**
- Texto original do formulário mantém o nome do campo do Caso (ex.: `mov_total_credito` = "R$500.000,00").
- Versões tipadas: sufixo `_valor` (DOUBLE) ou `_dt` (DATE) — ver `DERIVADAS_CASOS`.
- `criado_em` / `atualizado_em` são TIMESTAMP; `schema_version` é INT.
- Campo sem informação → `NULL` (`""` vira NULL).
- `caso_json` guarda o dossiê completo (sem Resolução/Avaliação) para reconstruir o caso.
- `COBERTURA_LISTAS` mapeia cada lista do Caso à tabela onde ela é gravada.

## 5. Fluxo de gravação (`gravacao_sql.py`)

1. `_gerar_dossie` (app) salva arquivos e, se `configurado()`, marca o caso como pendente.
2. `gravar_se_configurado(caso, limpar)` → devolve `(status, msg)` com status `desativado | ok | erro`; **nunca
   levanta exceção**.
3. `gravar_caso`: (opcional `limpar=True`: DELETE por `numero_caso` em todas as tabelas, ordem inversa) → INSERT em
   `casos` primeiro → INSERT das filhas em paralelo (até 6 threads). Erros das filhas são agregados em `ErroGravacao`.
4. `executor_databricks` usa `WorkspaceClient().statement_execution.execute_statement` (wait 50s, cancela no
   timeout). No Databricks Apps a autenticação é automática; fora dele use `SENTINELA_SQL_PERFIL`.
- Número de caso é único: a primeira gravação só faz INSERT. `limpar=True` só é usado em nova tentativa/migração.
- Atenção: **não há transação** entre tabelas — falha parcial é possível; a recuperação é o retry com `limpar=True`.

**Migração de casos já salvos:** `python gravacao_sql.py <pasta> --warehouse <id> [--perfil <p>]` (função
`migrar_pasta`). Idempotente (apaga e regrava cada caso). `normalizar_caso_antigo` converte o marcador legado
"Não informado" em vazio.

## 6. Configuração

| Variável | Padrão | Observação |
|---|---|---|
| `SENTINELA_SQL_WAREHOUSE_ID` | — | **Liga a gravação.** Sem ela, desativado. |
| `SENTINELA_SQL_CATALOGO` | `usr` | |
| `SENTINELA_SQL_SCHEMA` | `sentinela_aml` | |
| `SENTINELA_SQL_PERFIL` | — | Perfil do Databricks CLI (uso fora do Databricks Apps). |

Dependência: `databricks-sdk` (em `requirements.txt`).

Permissões necessárias (rodar como dono do schema): service principal do app com `USE CATALOG` em `usr`,
`USE SCHEMA, SELECT, MODIFY` em `usr.sentinela_aml` e "Can use" no SQL warehouse; quem só consulta, `USE SCHEMA, SELECT`.

## 7. Testes e como manter consistente

- O esquema é **derivado do modelo**: ao adicionar um campo em `core.Caso`, `tests/test_esquema_sql.py` falha até o
  campo ter coluna/tabela **ou** ser declarado em `EXCLUIDOS_CASOS`/`NAO_GRAVADOS_LISTAS`. Se for lista, registrar em
  `COBERTURA_LISTAS`. Se for relevante a um tipo, incluir no grupo da view.
- Testes também falham se algo de Resolução/Avaliação chegar às tabelas.
- Rodar: `./venv/bin/python -m pytest tests/` (`tests/e2e_playwright.py` é e2e à parte).
- Como `CREATE TABLE IF NOT EXISTS` não altera tabelas existentes, **coluna nova em tabela já criada exige `ALTER
  TABLE`** (ainda não há mecanismo de migração de esquema).

## 8. Estado atual e lacunas conhecidas

- Código, testes e docs (README 3.1, manual, `app.yaml`) estão commitados. Os testes usam executor falso; **não há
  registro neste repo de que o DDL já tenha sido aplicado no workspace nem de que `SENTINELA_SQL_WAREHOUSE_ID` esteja
  ativa em produção** (bloco do `app.yaml` está comentado) — confirmar com o usuário antes de assumir.
- Sem evolução de esquema (ALTER) automática; sem transação multi-tabela.
- Atualizações posteriores do dossiê (se existirem) não são regravadas; só a geração grava.
- `data/` local contém casos de exemplo (`caso_2026-426865.json`, `indice_dossies.json`, `pdfs/`) úteis para testar a migração.
