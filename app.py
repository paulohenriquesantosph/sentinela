# -*- coding: utf-8 -*-
"""
Sentinela PLD — versão Databricks (Streamlit)
================================================
Interface completa, com o design fiel ao artefato original.

Camadas:
  - core.py   : lógica de negócio (dados, armazenamento, IA, PDF)
  - opcoes.py : listas de razões/jurisprudências e rubricas de scorecard
  - estilo.py : TODO o visual (CSS, arte de fundo, cartões)
  - app.py    : este arquivo, apenas o fluxo das telas

Ver README.md para publicar no Databricks.
"""

import streamlit as st

import estilo
from core import (
    Caso, Socio, ContraparteMovimentacao, OutraMovimentacao,
    ItemArredondamento, MensagemPix, ArmazenamentoLocal,
    gerar_pdf_dossie, gerar_numero_caso, gerar_grafico_timeline,
    extrair_dados_do_texto, aplicar_dados_extraidos, ErroExtracaoIA,
    calcular_nota_scorecard, listar_drivers_scorecard, _parse_valor_br,
    TIPOS_CASO, DILIGENCIAS, TIPOS_REGIAO_RISCO_1, TIPOS_PEP, TIPOS_CONTRAPARTE,
    TIPOS_OUTRAS_MOV,
)
from opcoes import (
    RAZOES_CLEAR, RAZOES_CANCELAMENTO, JURISPRUDENCIA_NUPAGAMENTOS,
    JURISPRUDENCIA_REPORTAR_NUINVEST, JURISPRUDENCIA_REPORTAR_CANCELAR_NUINVEST,
)

st.set_page_config(page_title="Sentinela PLD", page_icon="🛡️", layout="centered")

store = ArmazenamentoLocal()

DEFAULTS = {
    "tela": "home",
    "tipo_caso_novo": None,
    "socios_tmp": [],
    "cp_credito_tmp": [],
    "cp_debito_tmp": [],
    "outras_mov_tmp": [],
    "arred_tmp": [],
    "pix_tmp": [],
    "grafico_tmp": None,
    "extracao_feita": False,
    "caso_selecionado": None,
}
for _k, _v in DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


def ir_para(tela: str):
    st.session_state.tela = tela


def limpar_formulario():
    for k in ("socios_tmp", "cp_credito_tmp", "cp_debito_tmp",
              "outras_mov_tmp", "arred_tmp", "pix_tmp"):
        st.session_state[k] = []
    st.session_state.grafico_tmp = None
    st.session_state.extracao_feita = False


# ---------------------------------------------------------------------------
# HOME
# ---------------------------------------------------------------------------
def tela_home():
    estilo.cartao_home(
        eyebrow="Gerador de Casos - Calibração",
        titulo="SENTINELA",
        descricao=("Transforma as informações de um caso de PLD/AML em um dossiê "
                   "individual, padronizado, pronto para análise e arquivo."),
        carimbo="Uso interno &middot; Confidencial",
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Iniciar novo caso", use_container_width=True):
            limpar_formulario()
            st.session_state.caso_selecionado = None
            ir_para("escolher_tipo")
            st.rerun()
    with col2:
        if st.button("Banco de Dossiês", use_container_width=True,
                     type="secondary"):
            st.session_state.caso_selecionado = None
            ir_para("banco")
            st.rerun()


# ---------------------------------------------------------------------------
# ESCOLHA DO TIPO DE CASO
# ---------------------------------------------------------------------------
def tela_escolher_tipo():
    estilo.cartao_home(
        eyebrow="Etapa 1 de 2",
        titulo="SENTINELA",
        descricao="Escolha o tipo de caso que será gerado para esta calibração.",
        titulo_pequeno=True,
    )
    for tipo in TIPOS_CASO:
        if st.button(tipo, use_container_width=True, type="secondary"):
            st.session_state.tipo_caso_novo = tipo
            limpar_formulario()
            ir_para("modo_preenchimento")
            st.rerun()
    st.write("")
    if st.button("← Voltar", type="secondary"):
        ir_para("home")
        st.rerun()


# ---------------------------------------------------------------------------
# MODO DE PREENCHIMENTO
# ---------------------------------------------------------------------------
def tela_modo_preenchimento():
    estilo.cartao_home(
        eyebrow="Etapa 2 de 2",
        titulo="SENTINELA",
        sub=st.session_state.tipo_caso_novo or "",
        descricao="Como você quer preencher este caso?",
        titulo_pequeno=True,
    )
    if st.button("Preencher com Instruções (Automático)", use_container_width=True):
        ir_para("preenchimento_ia")
        st.rerun()
    if st.button("Preencher Manualmente", use_container_width=True, type="secondary"):
        ir_para("formulario")
        st.rerun()
    st.write("")
    if st.button("← Voltar", type="secondary"):
        ir_para("escolher_tipo")
        st.rerun()


# ---------------------------------------------------------------------------
# PREENCHIMENTO AUTOMÁTICO VIA IA
# ---------------------------------------------------------------------------
def tela_preenchimento_ia():
    estilo.cartao_home(
        eyebrow="Preenchimento com Instruções",
        titulo="DESCREVA O CASO",
        descricao=("A IA lê o resumo em texto livre e pré-preenche o formulário. "
                   "Você revisa e completa depois."),
        titulo_pequeno=True,
    )

    with st.container(border=True):
        fator_gerador = st.text_input("Nome do Alerta *", placeholder="Ex: Transfer In")
        texto = st.text_area("Resumo do caso *", height=220, placeholder=(
            "Ex: Cliente João, 34 anos, morador de São Paulo/SP. Recebeu entre "
            "01/06/2026 e 01/08/2026 cerca de R$300.000,00 fragmentados entre 12 "
            "contrapartes, sendo a principal responsável por 40% do valor. "
            "Movimentação com forte recorrência de arredondamento e rápida evasão."
        ))
        texto_outras_mov = st.text_area(
            "Outras Movimentações não bancárias (opcional)", height=90)

        if st.button("Extrair dados com IA", use_container_width=True):
            if not texto.strip():
                st.error("Cole o resumo do caso antes de extrair.")
            else:
                with st.spinner("Chamando a IA para extrair os dados…"):
                    try:
                        dados = extrair_dados_do_texto(texto, texto_outras_mov)
                        caso_tmp = Caso(numero_caso="tmp",
                                        tipo_caso=st.session_state.tipo_caso_novo)
                        caso_tmp.fator_gerador = fator_gerador
                        caso_tmp = aplicar_dados_extraidos(caso_tmp, dados)
                        st.session_state.caso_extraido = caso_tmp
                        st.session_state.extracao_feita = True
                        st.success("Dados extraídos. Revise no formulário.")
                    except ErroExtracaoIA as e:
                        st.error(str(e))

    if st.session_state.get("extracao_feita"):
        if st.button("Continuar para o formulário →", use_container_width=True):
            ir_para("formulario")
            st.rerun()

    if st.button("← Voltar", type="secondary"):
        ir_para("modo_preenchimento")
        st.rerun()


# ---------------------------------------------------------------------------
# FORMULÁRIO COMPLETO
# ---------------------------------------------------------------------------
def tela_formulario():
    tipo_caso = st.session_state.tipo_caso_novo
    eh_pj = tipo_caso == "Pessoa Jurídica (PJ)"
    eh_under18 = tipo_caso == "Under 18"
    extraido = (st.session_state.get("caso_extraido")
                if st.session_state.get("extracao_feita") else None)

    def d(attr, default=""):
        return getattr(extraido, attr, default) if extraido else default

    estilo.cartao_home(
        eyebrow="Novo caso",
        titulo="SENTINELA",
        sub=tipo_caso or "",
        titulo_pequeno=True,
    )

    # ---- BLOCO 1 ----
    estilo.cabecalho_bloco("Bloco 1", "Alerta / Sentença")
    with st.container(border=True):
        fator_gerador = st.text_input("Fator Gerador do Alerta *", value=d("fator_gerador"))
        sentenca = st.text_area("Sentença / descrição do alerta", value=d("sentenca"))

    # ---- BLOCO 2 ----
    estilo.cabecalho_bloco("Bloco 2", "KYC - Know Your Customer")
    socios: list = st.session_state.socios_tmp
    rep_nome = rep_renda = rep_reg_prof = rep_reg_soc = rep_hist_pld = rep_hist_fraude = ""
    nome_empresa = data_abertura = ramo_atividade = porte = faturamento_presumido = endereco = ""
    presenca_online = fachada_empresa = "Não"
    presenca_online_detalhe = fachada_empresa_detalhe = ""
    nome_cliente = idade = cidade_estado = ultima_atualizacao = profissao_informada = ""
    renda_presumida = registro_profissional = ""
    registro_societario = "Não"
    reg_soc_razao_social = reg_soc_data_abertura = reg_soc_situacao = reg_soc_ramo = ""

    with st.container(border=True):
        if eh_pj:
            c1, c2 = st.columns(2)
            nome_empresa = c1.text_input("Nome da Empresa *", value=d("nome_empresa"))
            data_abertura = c2.text_input("Data de Abertura *", value=d("data_abertura"))
            c3, c4 = st.columns(2)
            ramo_atividade = c3.text_input("Ramo de Atividade *", value=d("ramo_atividade"))
            porte = c4.text_input("Porte *", value=d("porte"))
            c5, c6 = st.columns(2)
            faturamento_presumido = c5.text_input("Faturamento Presumido *",
                                                  value=d("faturamento_presumido"))
            endereco = c6.text_input("Endereço *", value=d("endereco"))

            c7, c8 = st.columns(2)
            presenca_online = c7.selectbox("Presença Online *", ["Não", "Sim"])
            if presenca_online == "Sim":
                presenca_online_detalhe = c8.text_input(
                    "Detalhes da Presença Online *",
                    placeholder="Insira o Link ou Informação sobre a Presença Online.")
            c9, c10 = st.columns(2)
            fachada_empresa = c9.selectbox("Fachada da Empresa *", ["Não", "Sim"], key="fachada")
            if fachada_empresa == "Sim":
                fachada_empresa_detalhe = c10.text_input(
                    "Detalhes da Fachada da Empresa *", key="fachada_det",
                    placeholder="Insira o Link ou Informação sobre a Fachada e Data.")

        elif eh_under18:
            estilo.subtitulo("Campos adicionais — Caso Under 18")
            c1, c2 = st.columns(2)
            rep_nome = c1.text_input("Nome do Responsável Legal *")
            rep_renda = c2.text_input("Renda Presumida do Responsável Legal *")
            c3, c4 = st.columns(2)
            rep_reg_prof = c3.text_input("Registro Profissional do Responsável Legal *")
            rep_reg_soc = c4.text_input("Registro Societário do Responsável Legal *")
            c5, c6 = st.columns(2)
            rep_hist_pld = c5.text_input("Histórico de PLD do Responsável Legal *")
            rep_hist_fraude = c6.text_input("Histórico de Fraude do Responsável Legal *")

        if not eh_pj:
            c1, c2, c3 = st.columns(3)
            nome_cliente = c1.text_input("Nome do Cliente *", value=d("nome_cliente"))
            idade = c2.text_input("Idade *", value=d("idade"))
            cidade_estado = c3.text_input("Cidade/Estado *", value=d("cidade_estado"))
            c4, c5 = st.columns(2)
            ultima_atualizacao = c4.text_input("Última Atualização Cadastral *",
                                               value=d("ultima_atualizacao_cadastral"))
            profissao_informada = c5.text_input("Profissão Informada pelo Cliente",
                                                value=d("profissao_informada"))
            c6, c7 = st.columns(2)
            renda_presumida = c6.text_input("Renda Presumida do Cliente *",
                                            value=d("renda_presumida"))
            registro_profissional = c7.text_input("Registros Profissionais *",
                                                  value=d("registro_profissional"))
            registro_societario = st.selectbox("Registros Societários *", ["Não", "Sim"])
            if registro_societario == "Sim":
                estilo.subtitulo("Registro societário")
                c8, c9 = st.columns(2)
                reg_soc_razao_social = c8.text_input("Razão Social *")
                reg_soc_data_abertura = c9.text_input("Data de Abertura *", key="regsoc_data")
                c10, c11 = st.columns(2)
                reg_soc_situacao = c10.text_input("Situação Cadastral *")
                reg_soc_ramo = c11.text_input("Ramo de Atividade *", key="regsoc_ramo")

        estilo.subtitulo("Região de risco, PEP e histórico")
        c1, c2 = st.columns(2)
        regiao_risco = c1.selectbox("Região de Risco *", ["Não", "Sim"])
        tipo_regiao_risco = ""
        if regiao_risco == "Sim":
            tipo_regiao_risco = c2.selectbox("Risco da Região *", TIPOS_REGIAO_RISCO_1)

        c3, c4 = st.columns(2)
        pep = c3.selectbox("PEP *", ["Não", "Sim"])
        tipo_pep = descricao_pep = ""
        if pep == "Sim":
            tipo_pep = c4.selectbox("Tipo de PEP *", TIPOS_PEP)
            descricao_pep = st.text_input("Descrição do PEP e Carência *")

        c5, c6 = st.columns(2)
        midia_negativa = c5.selectbox("Mídia Negativa *", ["Não", "Sim"])
        midia_negativa_detalhe = ""
        if midia_negativa == "Sim":
            midia_negativa_detalhe = c6.text_input(
                "Detalhes da Mídia Negativa *",
                placeholder="Link da Mídia, ou Breve Resumo, Data e Fonte")

        c7, c8 = st.columns(2)
        historico_pld = c7.selectbox("Histórico de PLD *", ["Não", "Sim"])
        historico_pld_detalhe = ""
        if historico_pld == "Sim":
            historico_pld_detalhe = c8.text_input("Detalhes do Histórico de PLD *")

        c9, c10 = st.columns(2)
        historico_fraude = c9.selectbox("Histórico de Fraudes *", ["Não", "Sim"])
        historico_fraude_detalhe = ""
        if historico_fraude == "Sim":
            historico_fraude_detalhe = c10.text_input("Detalhes do Histórico de Fraude *")

        outras_info = st.text_area(
            "Outras Informações Relevantes", value=d("outras_info"),
            placeholder="Redes Sociais, Processos, Compartilhamentos de Dispositivo, entre outros")

    if eh_pj:
        estilo.cabecalho_bloco("Bloco 2.1", "Informações Sobre o Sócio")
        with st.container(border=True):
            with st.form("form_add_socio", clear_on_submit=True):
                s1, s2, s3 = st.columns(3)
                snome = s1.text_input("Nome")
                sidade = s2.text_input("Idade")
                sendereco = s3.text_input("Endereço")
                s4, s5 = st.columns(2)
                srenda = s4.text_input("Renda Presumida")
                spatrimonio = s5.text_input("Patrimônio")
                s6, s7 = st.columns(2)
                sregiao = s6.selectbox("Região de Risco", ["Não", "Sim"])
                spep = s7.selectbox("PEP", ["Não", "Sim"])
                if st.form_submit_button("+ Adicionar sócio"):
                    if snome:
                        socios.append(Socio(
                            nome=snome, idade=sidade, endereco=sendereco,
                            renda_presumida=srenda, patrimonio=spatrimonio,
                            regiao_risco=sregiao, pep=spep))
                        st.rerun()
            for i, s in enumerate(socios):
                cols = st.columns([5, 1])
                cols[0].write(f"**{s.nome}** · {s.idade} anos · PEP: {s.pep} · "
                              f"Região de risco: {s.regiao_risco}")
                if cols[1].button("Remover", key=f"rm_socio_{i}", type="secondary"):
                    socios.pop(i)
                    st.rerun()

    # ---- BLOCO 3 ----
    estilo.cabecalho_bloco("Bloco 3", "Resumo de Movimentações")
    with st.container(border=True):
        mov_periodo = st.text_input("Período *", value=d("mov_periodo"),
                                    placeholder="Ex: 01/06/2026 até 01/08/2026")
        c1, c2 = st.columns(2)
        mov_total_credito = c1.text_input("Total de Créditos *",
                                          value=d("mov_total_credito"),
                                          placeholder="Exemplo: R$100.000,00")
        mov_total_cp_credito = c2.text_input("Total de Contrapartes (Crédito) *",
                                             value=d("mov_total_contrapartes_credito"))
        c3, c4 = st.columns(2)
        mov_total_debito = c3.text_input("Total de Débitos *",
                                         value=d("mov_total_debito"),
                                         placeholder="Exemplo: R$100.000,00")
        mov_total_cp_debito = c4.text_input("Total de Contrapartes (Débito) *",
                                            value=d("mov_total_contrapartes_debito"))

    def bloco_contrapartes(rotulo, state_key):
        estilo.subtitulo(rotulo)
        lista = st.session_state[state_key]
        with st.container(border=True):
            with st.form(f"form_{state_key}", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                tipo = c1.selectbox("Tipo de Contraparte", TIPOS_CONTRAPARTE, key=f"t_{state_key}")
                nome = c2.text_input("Nome", key=f"n_{state_key}")
                pct = c3.text_input("% do total", key=f"p_{state_key}")
                c4, c5, c6 = st.columns(3)
                valor = c4.text_input("Valor", key=f"v_{state_key}")
                num_trans = c5.text_input("Nº de transações", key=f"nt_{state_key}")
                detalhe = c6.text_input("Registro prof. / ramo", key=f"d_{state_key}")
                if st.form_submit_button("+ Adicionar contraparte"):
                    if nome:
                        lista.append(ContraparteMovimentacao(
                            tipo=tipo, nome=nome, porcentagem=pct, valor=valor,
                            num_transacoes=num_trans, registro_profissional=detalhe))
                        st.rerun()
            for i, cp in enumerate(lista):
                cols = st.columns([5, 1])
                cols[0].write(f"{cp.tipo} · **{cp.nome}** · {cp.porcentagem} · "
                              f"{cp.valor} · {cp.num_transacoes} transações")
                if cols[1].button("Remover", key=f"rm_{state_key}_{i}", type="secondary"):
                    lista.pop(i)
                    st.rerun()

    bloco_contrapartes("Contrapartes Principais de Crédito", "cp_credito_tmp")
    bloco_contrapartes("Contrapartes Principais de Débito", "cp_debito_tmp")

    estilo.subtitulo("Outras Movimentações (opcional)")
    lista_outras = st.session_state.outras_mov_tmp
    with st.container(border=True):
        with st.form("form_outra_mov", clear_on_submit=True):
            c1, c2 = st.columns([1, 2])
            tipo_mov = c1.selectbox("Tipo", TIPOS_OUTRAS_MOV)
            info_mov = c2.text_area("Descrição", height=68)
            if st.form_submit_button("+ Adicionar Outra Movimentação"):
                lista_outras.append(OutraMovimentacao(tipo=tipo_mov, info=info_mov))
                st.rerun()
        for i, m in enumerate(lista_outras):
            cols = st.columns([5, 1])
            cols[0].write(f"**{m.tipo}:** {m.info}")
            if cols[1].button("Remover", key=f"rm_om_{i}", type="secondary"):
                lista_outras.pop(i)
                st.rerun()

    # ---- BLOCO 4 ----
    estilo.cabecalho_bloco("Bloco 4", "Thundera - AML 360")
    with st.container(border=True):
        comp_arredondamento = st.selectbox(
            "Transações em Perfil de Arredondamento nas Unidades de Milhar *", ["Não", "Sim"])
        if comp_arredondamento == "Sim":
            lista_arred = st.session_state.arred_tmp
            with st.form("form_arred", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                cd = c1.selectbox("Créditos ou Débitos", ["Créditos", "Débitos"])
                qtd = c2.text_input("Quantidade")
                val = c3.text_input("Valor")
                if st.form_submit_button("+ Adicionar quantidade/valor"):
                    lista_arred.append(ItemArredondamento(cred_deb=cd, quantidade=qtd, valor=val))
                    st.rerun()
            for i, a in enumerate(lista_arred):
                cols = st.columns([5, 1])
                cols[0].write(f"{a.cred_deb} · {a.quantidade} transações · {a.valor}")
                if cols[1].button("Remover", key=f"rm_ar_{i}", type="secondary"):
                    lista_arred.pop(i)
                    st.rerun()

        comp_pix = st.selectbox("Mensagens PIX *", ["Não", "Sim"])
        if comp_pix == "Sim":
            lista_pix = st.session_state.pix_tmp
            with st.form("form_pix", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                cd = c1.selectbox("Créditos ou Débitos", ["Créditos", "Débitos"], key="pix_cd")
                qtd = c2.text_input("Quantidade", key="pix_qtd")
                msg = c3.text_input("Mensagem PIX", key="pix_msg")
                if st.form_submit_button("+ Adicionar Quantidade e Mensagem PIX"):
                    lista_pix.append(MensagemPix(cred_deb=cd, quantidade=qtd, mensagem=msg))
                    st.rerun()
            for i, p in enumerate(lista_pix):
                cols = st.columns([5, 1])
                cols[0].write(f"{p.cred_deb} · {p.quantidade} mensagens · \"{p.mensagem}\"")
                if cols[1].button("Remover", key=f"rm_px_{i}", type="secondary"):
                    lista_pix.pop(i)
                    st.rerun()

        comp_evasao = st.selectbox("Timeline de Transferências *",
                                   ["", "Rápida Evasão", "Sem Rápida Evasão"])
        if comp_evasao:
            estilo.nota("O gráfico é montado com base no Total de Créditos, "
                        "Total de Débitos e Período preenchidos no Bloco 3.")
            if st.button("+ Gerar/Atualizar Gráfico"):
                total_c = _parse_valor_br(mov_total_credito)
                total_d = _parse_valor_br(mov_total_debito)
                if total_c or total_d:
                    st.session_state.grafico_tmp = gerar_grafico_timeline(total_c, total_d)
                else:
                    st.warning("Preencha Total de Créditos/Débitos no Bloco 3 primeiro.")
        if st.session_state.grafico_tmp:
            st.image(st.session_state.grafico_tmp)

        comp_mudanca_comportamento = st.text_area(
            "Mudança de Comportamento", value=d("comp_mudanca_comportamento"))
        comp_data_abertura_ultimo_reporte = st.text_input(
            "Data de Abertura da Conta / Data do Último Reporte *",
            value=d("comp_data_abertura_ultimo_reporte"))

    estilo.nota("Parecer Final, Alíneas e Diligência ficam disponíveis dentro do "
                "dossiê, na tela de Resolução, após a geração.")
    st.write("")

    col_a, col_b = st.columns([2, 1])
    with col_a:
        gerar = st.button("Gerar dossiê do caso", use_container_width=True)
    with col_b:
        if st.button("← Voltar", use_container_width=True, type="secondary"):
            ir_para("modo_preenchimento")
            st.rerun()

    if gerar:
        if (eh_pj and not nome_empresa) or (not eh_pj and not nome_cliente):
            st.error("Preencha ao menos o nome do cliente/empresa antes de gerar o dossiê.")
        else:
            caso = Caso(
                numero_caso=gerar_numero_caso(), tipo_caso=tipo_caso,
                fator_gerador=fator_gerador, sentenca=sentenca,
                regiao_risco=regiao_risco, tipo_regiao_risco=tipo_regiao_risco,
                pep=pep, tipo_pep=tipo_pep, descricao_pep=descricao_pep,
                midia_negativa=midia_negativa, midia_negativa_detalhe=midia_negativa_detalhe,
                historico_pld=historico_pld, historico_pld_detalhe=historico_pld_detalhe,
                historico_fraude=historico_fraude,
                historico_fraude_detalhe=historico_fraude_detalhe,
                outras_info=outras_info,
                nome_cliente=nome_cliente, idade=idade, cidade_estado=cidade_estado,
                ultima_atualizacao_cadastral=ultima_atualizacao,
                profissao_informada=profissao_informada,
                renda_presumida=renda_presumida, registro_profissional=registro_profissional,
                registro_societario=registro_societario,
                reg_soc_razao_social=reg_soc_razao_social,
                reg_soc_data_abertura=reg_soc_data_abertura,
                reg_soc_situacao_cadastral=reg_soc_situacao,
                reg_soc_ramo_atividade=reg_soc_ramo,
                nome_empresa=nome_empresa, data_abertura=data_abertura,
                ramo_atividade=ramo_atividade, porte=porte,
                faturamento_presumido=faturamento_presumido, endereco=endereco,
                presenca_online=presenca_online,
                presenca_online_detalhe=presenca_online_detalhe,
                fachada_empresa=fachada_empresa,
                fachada_empresa_detalhe=fachada_empresa_detalhe,
                socios=list(socios),
                rep_nome=rep_nome, rep_renda_presumida=rep_renda,
                rep_reg_prof=rep_reg_prof, rep_reg_soc=rep_reg_soc,
                rep_hist_pld=rep_hist_pld, rep_hist_fraude=rep_hist_fraude,
                mov_periodo=mov_periodo, mov_total_credito=mov_total_credito,
                mov_total_contrapartes_credito=mov_total_cp_credito,
                mov_total_debito=mov_total_debito,
                mov_total_contrapartes_debito=mov_total_cp_debito,
                contrapartes_credito=list(st.session_state.cp_credito_tmp),
                contrapartes_debito=list(st.session_state.cp_debito_tmp),
                outras_movimentacoes=list(st.session_state.outras_mov_tmp),
                comp_arredondamento=comp_arredondamento,
                arredondamento_itens=list(st.session_state.arred_tmp),
                comp_pix=comp_pix, pix_itens=list(st.session_state.pix_tmp),
                comp_evasao=comp_evasao,
                comp_mudanca_comportamento=comp_mudanca_comportamento,
                comp_data_abertura_ultimo_reporte=comp_data_abertura_ultimo_reporte,
            )
            pdf_bytes = gerar_pdf_dossie(caso, grafico_png=st.session_state.grafico_tmp)
            store.salvar_caso(caso, pdf_bytes)
            limpar_formulario()
            st.success(f"Dossiê {caso.numero_caso} gerado e salvo no Banco de Dossiês.")
            st.download_button("⬇ Baixar PDF do dossiê", data=pdf_bytes,
                               file_name=f"dossie_{caso.numero_caso}.pdf",
                               mime="application/pdf")


# ---------------------------------------------------------------------------
# RESOLUÇÃO + SCORECARD
# ---------------------------------------------------------------------------
def tela_resolucao():
    numero = st.session_state.get("caso_selecionado")
    caso = store.carregar_caso(numero) if numero else None
    if not caso:
        st.error("Caso não encontrado.")
        if st.button("← Voltar ao Banco de Dossiês", type="secondary"):
            ir_para("banco")
            st.rerun()
        return

    estilo.cartao_home(
        eyebrow=f"Dossiê {caso.numero_caso}",
        titulo="RESOLUÇÃO",
        sub=f"{caso.nome_display()} · {caso.tipo_caso}",
        carimbo=f"Risco {caso.risco_geral()}",
        titulo_pequeno=True,
    )

    estilo.cabecalho_bloco("Resolução", "Parecer Final do Analista")
    with st.container(border=True):
        parecer_final = st.text_area("Parecer Final", value=caso.parecer_final, height=160)
        alineas = st.text_area("Alíneas (sem limite de caracteres)",
                               value=caso.alineas, height=100)

    estilo.cabecalho_bloco("Resolução", "Jurisprudências")
    with st.container(border=True):
        jur_nupag = st.multiselect(
            "NuPagamentos", JURISPRUDENCIA_NUPAGAMENTOS,
            default=[j for j in caso.jurisprudencias_selecionadas
                     if j in JURISPRUDENCIA_NUPAGAMENTOS])
        jur_rep_nuinvest = st.multiselect(
            "Reportar — NuInvest", JURISPRUDENCIA_REPORTAR_NUINVEST,
            default=[j for j in caso.jurisprudencias_selecionadas
                     if j in JURISPRUDENCIA_REPORTAR_NUINVEST])
        jur_canc_nuinvest = st.multiselect(
            "Reportar e Cancelar — NuInvest", JURISPRUDENCIA_REPORTAR_CANCELAR_NUINVEST,
            default=[j for j in caso.jurisprudencias_selecionadas
                     if j in JURISPRUDENCIA_REPORTAR_CANCELAR_NUINVEST])

    estilo.cabecalho_bloco("Resolução", "Razões e Diligência")
    with st.container(border=True):
        razoes_clear = st.multiselect("Razões de Clear", RAZOES_CLEAR,
                                      default=caso.razoes_clear_selecionadas)
        razoes_cancelamento = st.multiselect("Razões de Cancelamento", RAZOES_CANCELAMENTO,
                                             default=caso.razoes_cancelamento_selecionadas)
        diligencia = st.selectbox(
            "Diligência", [""] + DILIGENCIAS,
            index=(DILIGENCIAS.index(caso.diligencia) + 1)
            if caso.diligencia in DILIGENCIAS else 0)

        if st.button("Salvar resolução", use_container_width=True):
            caso.parecer_final = parecer_final
            caso.alineas = alineas
            caso.jurisprudencias_selecionadas = jur_nupag + jur_rep_nuinvest + jur_canc_nuinvest
            caso.razoes_clear_selecionadas = razoes_clear
            caso.razoes_cancelamento_selecionadas = razoes_cancelamento
            caso.diligencia = diligencia
            pdf_bytes = gerar_pdf_dossie(caso)
            store.salvar_caso(caso, pdf_bytes)
            st.success("Resolução salva e PDF atualizado.")
            st.download_button("⬇ Baixar PDF atualizado", data=pdf_bytes,
                               file_name=f"dossie_{caso.numero_caso}.pdf",
                               mime="application/pdf")

    scorecard_tipo_atual = caso.scorecard_tipo
    estilo.cabecalho_bloco("Qualidade", f"Avaliação de Qualidade")
    with st.container(border=True):
        scorecard_tipo = st.selectbox(
            "Rubrica", ["AML Nupag", "AML NuInvest"],
            index=0 if scorecard_tipo_atual != "AML NuInvest" else 1)
        marcados = set(caso.scorecard_drivers_marcados)
        novos_marcados = []
        for categoria in listar_drivers_scorecard(scorecard_tipo):
            titulo_exp = f"{categoria['categoria']} — peso {categoria['peso'] * 100:.1f}% por driver"
            with st.expander(titulo_exp):
                for driver in categoria["drivers"]:
                    if st.checkbox(driver["nome"], value=driver["nome"] in marcados,
                                   help=driver["aplicabilidade"],
                                   key=f"dr_{scorecard_tipo}_{driver['nome']}"):
                        novos_marcados.append(driver["nome"])
        nota_final = calcular_nota_scorecard(scorecard_tipo, novos_marcados)
        st.metric("Nota final", f"{nota_final:.1f}%")
        feedback = st.text_area("Feedback de qualidade", value=caso.scorecard_feedback)

        if st.button("Salvar Avaliação", use_container_width=True):
            caso.scorecard_tipo = scorecard_tipo
            caso.scorecard_drivers_marcados = novos_marcados
            caso.scorecard_feedback = feedback
            pdf_bytes = gerar_pdf_dossie(caso)
            store.salvar_caso(caso, pdf_bytes)
            st.success(f"Avaliação salva. Nota final: {nota_final:.1f}%")

    if st.button("← Voltar ao Banco de Dossiês", type="secondary"):
        ir_para("banco")
        st.rerun()


# ---------------------------------------------------------------------------
# BANCO DE DOSSIÊS
# ---------------------------------------------------------------------------
def tela_banco():
    estilo.cartao_home(
        eyebrow="Gerador de Casos - Calibração",
        titulo="BANCO DE DOSSIÊS",
        titulo_pequeno=True,
    )

    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        termo = col1.text_input("Consultar por número do caso",
                                placeholder="Ex: 2026-3E1DFA")
        col2.write("")
        buscar = col2.button("Buscar", use_container_width=True)
        estilo.nota("— ou, se não tiver o número —")
        consultar_tudo = st.button("Consultar banco de dados completo",
                                   use_container_width=True, type="secondary")

    resultados = None
    if buscar:
        resultados = store.buscar_por_numero(termo) if termo else []
        if not resultados:
            st.warning(f'Nenhum caso encontrado com o número "{termo}".')
    elif consultar_tudo:
        resultados = store.listar_indice()
        if not resultados:
            st.info("Nenhum dossiê salvo ainda. Gere um caso para ele aparecer aqui.")

    if resultados:
        for item in resultados:
            with st.container(border=True):
                cols = st.columns([3, 1])
                cols[0].write(
                    f"**{item['numero_caso']}** — {item['nome_cliente']}  \n"
                    f"{item['tipo_caso']} · risco **{item.get('risco', '—')}** · "
                    f"diligência: {item.get('diligencia', 'Pendente')}")
                cols[1].write("")
                if cols[1].button("Abrir", key=f"ab_{item['numero_caso']}",
                                  use_container_width=True):
                    st.session_state.caso_selecionado = item["numero_caso"]
                    st.rerun()

    if st.session_state.get("caso_selecionado"):
        numero = st.session_state.caso_selecionado
        caso = store.carregar_caso(numero)
        pdf_bytes = store.carregar_pdf(numero)
        if caso:
            estilo.cabecalho_bloco(f"Dossiê {caso.numero_caso}", caso.nome_display() or "Sem nome")
            with st.container(border=True):
                st.write(f"**Tipo:** {caso.tipo_caso} · **Risco:** {caso.risco_geral()} · "
                         f"**Diligência:** {caso.diligencia or 'Pendente'}")
                c1, c2 = st.columns(2)
                if pdf_bytes:
                    c1.download_button("⬇ Baixar PDF do dossiê", data=pdf_bytes,
                                       file_name=f"dossie_{caso.numero_caso}.pdf",
                                       mime="application/pdf", use_container_width=True)
                if c2.button("Resolução / Scorecard →", use_container_width=True):
                    ir_para("resolucao")
                    st.rerun()

    if st.button("← Voltar", type="secondary"):
        st.session_state.caso_selecionado = None
        ir_para("home")
        st.rerun()


# ---------------------------------------------------------------------------
# Roteamento
# ---------------------------------------------------------------------------
estilo.aplicar_estilo(com_fundo=True)

TELAS = {
    "home": tela_home,
    "escolher_tipo": tela_escolher_tipo,
    "modo_preenchimento": tela_modo_preenchimento,
    "preenchimento_ia": tela_preenchimento_ia,
    "formulario": tela_formulario,
    "resolucao": tela_resolucao,
    "banco": tela_banco,
}
TELAS.get(st.session_state.tela, tela_home)()
