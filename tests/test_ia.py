# -*- coding: utf-8 -*-
"""Testes do preenchimento automático por IA (ia.py), com um servidor HTTP fake.

Rodar, da raiz do projeto:
    ./venv/bin/python -m unittest tests.test_ia -v
Nenhuma chamada de rede real é feita.
"""
import json
import os
import sys
import threading
import unittest
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ia  # noqa: E402
from core import Caso, NEUTRO, periodo_padrao  # noqa: E402

HOJE = date(2026, 10, 3)

CP_CRED = [
    ("Marcos Vinícius Andrade", "14%", "R$70.000,00", "23", 34, "Belo Horizonte/MG", "R$2.100,00", "Pedreiro, sem registro profissional"),
    ("Fernanda Lopes Ribeiro", "11%", "R$55.000,00", "18", 41, "Contagem/MG", "R$1.600,00", "Auxiliar de limpeza, sem registro profissional"),
    ("Rafael Souza Nunes", "9%", "R$45.000,00", "15", 26, "Betim/MG", "R$1.900,00", "Motoboy, sem registro profissional"),
    ("Camila Teixeira Rocha", "7%", "R$35.000,00", "12", 30, "Ribeirão das Neves/MG", "R$1.450,00", "Atendente de lanchonete, sem registro profissional"),
    ("Anderson Pires Moura", "6%", "R$30.000,00", "10", 45, "Sete Lagoas/MG", "R$1.750,00", "Porteiro, sem registro profissional"),
]
CP_DEB = [
    ("Diego Henrique Martins", "16%", "R$80.000,00", "20", 29, "São Paulo/SP", "R$1.800,00", "Ajudante geral, sem registro profissional"),
    ("Patrícia Gomes Silva", "12%", "R$60.000,00", "16", 37, "Guarulhos/SP", "R$1.500,00", "Diarista, sem registro profissional"),
    ("Lucas Ferreira Alves", "10%", "R$50.000,00", "14", 24, "Osasco/SP", "R$1.700,00", "Repositor de supermercado, sem registro profissional"),
    ("Juliana Costa Pereira", "8%", "R$40.000,00", "11", 33, "Santo André/SP", "R$2.000,00", "Cabeleireira, sem registro profissional"),
    ("Thiago Ramos Oliveira", "6%", "R$30.000,00", "9", 31, "São Bernardo do Campo/SP", "R$1.650,00", "Garçom, sem registro profissional"),
]


def _cps(lista):
    return [{"tipo": "Pessoa Física", "porcentagem": p, "valor": v, "numTransacoes": n, "nome": nome,
             "idade": str(idade), "cidadeEstado": cid, "rendaPresumida": renda, "registroProfissional": reg,
             "registroSocietario": "Não", "regiaoRisco": "Não", "pep": "Não", "historicoPld": "Não",
             "historicoFraude": "Não", "midiaNegativa": "Não"}
            for nome, p, v, n, idade, cid, renda, reg in lista]


def dados_joao():
    return {
        "kyc": {
            "nome": "João Paulo Carvalho Dias", "idade": "28", "cidadeEstado": "São Paulo/SP",
            "ultimaAtualizacaoCadastral": "15/03/2026", "profissaoInformada": "Auxiliar administrativo",
            "rendaPresumida": "R$1.200,00", "registroProfissional": "Sem registros profissionais",
            "registroSocietario": "Não", "regiaoRisco": "Não", "pep": "Não", "historicoPld": "Não",
            "historicoFraude": "Não", "midiaNegativa": "Não",
            "outrasInformacoes": "Sem redes sociais vinculadas; não foram localizados processos judiciais.",
        },
        "movimentacoes": {
            "periodo": "01/04/2026 até 30/09/2026", "totalCredito": "R$500.000,00",
            "totalContrapartesCredito": "63", "totalDebito": "R$500.000,00", "totalContrapartesDebito": "52",
            "contrapartesCredito": _cps(CP_CRED), "contrapartesDebito": _cps(CP_DEB),
        },
        "thundera": {
            "arredondamento": "Sim",
            "arredondamentoItens": [
                {"credDeb": "Créditos", "quantidade": "84", "valor": "R$1.000,00"},
                {"credDeb": "Créditos", "quantidade": "41", "valor": "R$2.000,00"},
                {"credDeb": "Créditos", "quantidade": "17", "valor": "R$5.000,00"},
                {"credDeb": "Débitos", "quantidade": "62", "valor": "R$1.000,00"},
                {"credDeb": "Débitos", "quantidade": "35", "valor": "R$2.000,00"},
                {"credDeb": "Débitos", "quantidade": "14", "valor": "R$5.000,00"},
            ],
            "pix": "Não", "pixItens": [], "evasao": "Rápida Evasão",
            "mudancaComportamento": {"houve": "Sim", "valorAproximado": "R$160.000,00"},
            "dataAberturaContaUltimoReporte": "10/01/2026",
        },
        "outrasMovimentacoes": [{"tipo": "Saques", "info": "R$90.000,00 em 38 saques fragmentados em 9 localidades."}],
    }


class FakeLLM:
    """Servidor HTTP em thread que imita /v1/chat/completions e /v1/messages."""

    def __init__(self):
        self.requisicoes = []   # (path, headers, corpo_json)
        self.roteiro = []       # lista de (status, corpo_dict) consumida em ordem; vazio = resposta padrão
        self.dados = dados_joao()
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                corpo = json.loads(self.rfile.read(n) or b"{}")
                fake.requisicoes.append((self.path, dict(self.headers), corpo))
                if fake.roteiro:
                    status, resp = fake.roteiro.pop(0)
                else:
                    status, resp = 200, fake.resposta_padrao(self.path)
                data = json.dumps(resp).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def resposta_padrao(self, path, texto=None):
        texto = texto if texto is not None else json.dumps(self.dados, ensure_ascii=False)
        if path.endswith("/chat/completions"):
            return {"choices": [{"message": {"content": texto}, "finish_reason": "stop"}]}
        return {"content": [{"type": "text", "text": texto}], "stop_reason": "end_turn"}

    def fechar(self):
        self.server.shutdown()
        self.server.server_close()


class BaseLLM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = FakeLLM()

    @classmethod
    def tearDownClass(cls):
        cls.fake.fechar()

    def setUp(self):
        self.fake.requisicoes.clear()
        self.fake.roteiro.clear()
        self.fake.dados = dados_joao()
        env = {"ANTHROPIC_BASE_URL": self.fake.url, "SENTINELA_LLM_FORMATO": "openai",
               "SENTINELA_LLM_MODELO": "anthropic/claude-sonnet-4-6"}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("ANTHROPIC_API_KEY", None)


class TestChamada(BaseLLM):
    def test_formato_openai(self):
        dados = ia.extrair_dados_do_texto("Cliente João...", "", api_key="chave-litellm")
        path, headers, corpo = self.fake.requisicoes[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer chave-litellm")
        self.assertNotIn("x-api-key", {k.lower() for k in headers})
        self.assertEqual(corpo["model"], "anthropic/claude-sonnet-4-6")
        self.assertEqual(corpo["messages"][0]["role"], "system")
        self.assertEqual(dados["kyc"]["nome"], "João Paulo Carvalho Dias")

    def test_formato_anthropic(self):
        with mock.patch.dict(os.environ, {"SENTINELA_LLM_FORMATO": "anthropic"}):
            dados = ia.extrair_dados_do_texto("Cliente João...", "", api_key="sk-ant-x")
        path, headers, corpo = self.fake.requisicoes[0]
        self.assertEqual(path, "/v1/messages")
        self.assertEqual(headers["x-api-key"], "sk-ant-x")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertIn("system", corpo)
        self.assertEqual(corpo["messages"][0]["role"], "user")
        self.assertEqual(dados["movimentacoes"]["totalCredito"], "R$500.000,00")

    def test_sem_chave(self):
        with self.assertRaises(ia.ErroExtracaoIA) as cm:
            ia.extrair_dados_do_texto("x")
        self.assertIn("ANTHROPIC_API_KEY", str(cm.exception))

    def test_modelo_padrao_e_override(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("SENTINELA_LLM_MODELO")
            ia.extrair_dados_do_texto("x", api_key="k")
            ia.extrair_dados_do_texto("x", api_key="k", model="outro")
        self.assertEqual(self.fake.requisicoes[0][2]["model"], "claude-sonnet-4-6")
        self.assertEqual(self.fake.requisicoes[1][2]["model"], "outro")

    def test_alerta_e_sentenca_fora_do_prompt(self):
        ia.extrair_dados_do_texto("Cliente João", "", api_key="k")
        corpo = self.fake.requisicoes[0][2]
        sistema = corpo["messages"][0]["content"].lower()
        for proibido in ("sentença", "sentenca", "fatorgerador", "dataalerta", "nome do alerta", "alerta"):
            self.assertNotIn(proibido, sistema)
        # preencher_caso_via_ia não manda os três campos do analista à IA
        caso, _ = ia.preencher_caso_via_ia(
            "Pessoa Física (PF)", "Transfer In", "01/10/2026", "SENTENCA-SECRETA-XYZ",
            "Cliente João", "", hoje=HOJE, api_key="k")
        tudo = json.dumps(self.fake.requisicoes[-1][2], ensure_ascii=False)
        self.assertNotIn("SENTENCA-SECRETA-XYZ", tudo)
        self.assertNotIn("Transfer In", tudo)
        self.assertEqual((caso.fator_gerador, caso.data_alerta, caso.sentenca),
                         ("Transfer In", "01/10/2026", "SENTENCA-SECRETA-XYZ"))

    def test_outras_movimentacoes_em_bloco_separado(self):
        ia.extrair_dados_do_texto("Resumo principal XPTO", "Saques de R$90.000 ABCD", api_key="k")
        msg = self.fake.requisicoes[0][2]["messages"][1]["content"]
        resumo, outras = msg.split("### OUTRAS MOVIMENTAÇÕES (NÃO BANCÁRIAS)")
        self.assertIn("### RESUMO DO CASO", resumo)
        self.assertIn("XPTO", resumo)
        self.assertNotIn("ABCD", resumo)
        self.assertIn("ABCD", outras)
        self.assertNotIn("XPTO", outras)

    def test_outras_movimentacoes_vazias_descartam_secao(self):
        dados = ia.extrair_dados_do_texto("Resumo", "", api_key="k")
        self.assertEqual(dados["outrasMovimentacoes"], [])
        dados = ia.extrair_dados_do_texto("Resumo", "Saques", api_key="k")
        self.assertEqual(len(dados["outrasMovimentacoes"]), 1)

    def test_prompt_pj_para_pj(self):
        ia.extrair_dados_do_texto("Empresa X", "", tipo_caso="Pessoa Jurídica (PJ)", api_key="k")
        ia.extrair_dados_do_texto("Cliente Y", "", tipo_caso="NuInvest", api_key="k")
        pj = self.fake.requisicoes[0][2]["messages"][0]["content"]
        pf = self.fake.requisicoes[1][2]["messages"][0]["content"]
        self.assertIn("nomeEmpresa", pj)
        self.assertIn("socios", pj)
        self.assertNotIn("nomeEmpresa", pf)
        self.assertIn("profissaoInformada", pf)
        self.assertNotIn("profissaoInformada", pj)

    def test_prompt_codifica_regras_do_manual(self):
        pf = ia.SYSTEM_PROMPT_PF
        for trecho in ("Profissão informada", "Registro profissional", "3 a 5 principais", "50%", "diversas",
                       "Sim", "R$1.000,00", "INVENÇÃO AUTORIZADA: SIM", "APENAS um objeto JSON",
                       "OUTRAS MOVIMENTAÇÕES (NÃO BANCÁRIAS)", "houve", "valorAproximado"):
            self.assertIn(trecho, pf, trecho)

    def test_invencao_autorizada_na_mensagem(self):
        ia.extrair_dados_do_texto("Cliente com renda baixa, valores aleatórios", "", api_key="k")
        ia.extrair_dados_do_texto("Cliente João, 34 anos, R$300.000 em créditos", "", api_key="k")
        ia.extrair_dados_do_texto("Gere o caso e invente os dados", "", api_key="k")
        msgs = [r[2]["messages"][1]["content"] for r in self.fake.requisicoes]
        self.assertTrue(msgs[0].startswith("INVENÇÃO AUTORIZADA: SIM"))
        self.assertTrue(msgs[1].startswith("INVENÇÃO AUTORIZADA: NÃO"))
        self.assertNotIn("INVENÇÃO AUTORIZADA: SIM", msgs[1])
        self.assertTrue(msgs[2].startswith("INVENÇÃO AUTORIZADA: SIM"))

    def test_401(self):
        self.fake.roteiro = [(401, {"error": "no"})]
        with self.assertRaises(ia.ErroExtracaoIA) as cm:
            ia.extrair_dados_do_texto("x", api_key="k")
        self.assertIn("401", str(cm.exception))
        self.assertIn("ANTHROPIC_BASE_URL", str(cm.exception))
        self.assertEqual(len(self.fake.requisicoes), 1)  # 401 não faz reintento

    def test_404(self):
        self.fake.roteiro = [(404, {})]
        with self.assertRaises(ia.ErroExtracaoIA) as cm:
            ia.extrair_dados_do_texto("x", api_key="k")
        self.assertIn("SENTINELA_LLM_FORMATO", str(cm.exception))

    def test_json_invalido(self):
        self.fake.roteiro = [(200, self.fake.resposta_padrao("/v1/chat/completions", "isto não é json"))]
        with self.assertRaises(ia.ErroExtracaoIA) as cm:
            ia.extrair_dados_do_texto("x", api_key="k")
        self.assertIn("JSON válido", str(cm.exception))

    def test_resposta_cortada_openai(self):
        self.fake.roteiro = [(200, {"choices": [{"message": {"content": "{"}, "finish_reason": "length"}]})]
        with self.assertRaises(ia.ErroExtracaoIA) as cm:
            ia.extrair_dados_do_texto("x", api_key="k")
        self.assertIn("cortada", str(cm.exception))

    def test_resposta_cortada_anthropic(self):
        with mock.patch.dict(os.environ, {"SENTINELA_LLM_FORMATO": "anthropic"}):
            self.fake.roteiro = [(200, {"content": [{"type": "text", "text": "{"}], "stop_reason": "max_tokens"})]
            with self.assertRaises(ia.ErroExtracaoIA) as cm:
                ia.extrair_dados_do_texto("x", api_key="k")
        self.assertIn("cortada", str(cm.exception))

    def test_reintento_depois_de_erro_de_servidor(self):
        self.fake.roteiro = [(500, {"error": "boom"})]  # 2ª tentativa usa a resposta padrão
        dados = ia.extrair_dados_do_texto("x", api_key="k")
        self.assertEqual(len(self.fake.requisicoes), 2)
        self.assertEqual(dados["kyc"]["idade"], "28")

    def test_duas_falhas_dao_erro(self):
        self.fake.roteiro = [(500, {}), (502, {})]
        with self.assertRaises(ia.ErroExtracaoIA) as cm:
            ia.extrair_dados_do_texto("x", api_key="k")
        self.assertIn("duas tentativas", str(cm.exception))

    def test_json_embrulhado_em_crases_e_com_texto_em_volta(self):
        corpo = "```json\n" + json.dumps(dados_joao(), ensure_ascii=False) + "\n```"
        self.fake.roteiro = [(200, self.fake.resposta_padrao("/v1/chat/completions", corpo))]
        self.assertEqual(ia.extrair_dados_do_texto("x", api_key="k")["kyc"]["nome"], "João Paulo Carvalho Dias")
        corpo = "Aqui está:\n" + json.dumps(dados_joao(), ensure_ascii=False) + "\nFim."
        self.fake.roteiro = [(200, self.fake.resposta_padrao("/v1/chat/completions", corpo))]
        self.assertEqual(ia.extrair_dados_do_texto("x", api_key="k")["kyc"]["idade"], "28")

    def test_preencher_caso_via_ia_ponta_a_ponta(self):
        caso, avisos = ia.preencher_caso_via_ia(
            "Pessoa Física (PF)", "Transfer In", "01/10/2026", "Sentença do analista", "Resumo", "Saques fragmentados",
            hoje=HOJE, api_key="k")
        self.assertEqual(caso.nome_cliente, "João Paulo Carvalho Dias")
        self.assertEqual(caso.genero, "M")
        self.assertEqual(caso.mov_total_credito, "R$500.000,00")
        self.assertEqual(len(caso.contrapartes_credito), 5)
        self.assertEqual(len(caso.arredondamento_itens), 6)
        self.assertEqual(caso.comp_evasao, "Rápida Evasão")
        self.assertEqual(caso.outras_movimentacoes[0].tipo, "Saques")
        self.assertEqual(avisos, [])


class TestMudancaRespondida(unittest.TestCase):
    def _caso(self):
        return Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)",
                    mov_total_credito="R$500.000,00", mov_total_debito="R$480.000,00")

    def test_detecta_mencao(self):
        self.assertTrue(ia.menciona_mudanca_comportamento("Houve mudança de comportamento em abril."))
        self.assertTrue(ia.menciona_mudanca_comportamento("cliente mudou o comportamento recentemente"))
        self.assertFalse(ia.menciona_mudanca_comportamento("Cliente com renda baixa e 12 contrapartes."))

    def test_validacao_ok(self):
        dados, erros = ia.validar_mudanca("10/01/2025", "15/06/2026")
        self.assertEqual(erros, [])
        self.assertEqual((dados["inicio"], dados["fim"], dados["mes_mudanca"]),
                         (date(2026, 1, 1), date(2026, 6, 1), date(2026, 6, 1)))

    def test_validacao_erros(self):
        _, erros = ia.validar_mudanca("", "15/06/2026")
        self.assertIn("abertura da conta", " ".join(erros))
        _, erros = ia.validar_mudanca("15/06/2026", "15/06/2026")  # mesma data: não é anterior
        self.assertIn("anterior à data do alerta", " ".join(erros))
        _, erros = ia.validar_mudanca("10/07/2026", "15/06/2026")
        self.assertIn("anterior à data do alerta", " ".join(erros))
        _, erros = ia.validar_mudanca("10/01/2025", "")
        self.assertIn("Data do alerta", " ".join(erros))

    def test_narrativa_seis_meses_terminando_no_alerta(self):
        caso = self._caso()
        dados, _ = ia.validar_mudanca("10/01/2025", "15/06/2026", "R$160.000,00")
        avisos = []
        ia.aplicar_mudanca_respondida(caso, dados, avisos)
        self.assertEqual(caso.comp_mudanca_comportamento.split("\n"), [
            "Janeiro R$1.000,00", "Fevereiro R$1.500,00", "Março R$2.000,00",
            "Abril R$0,00", "Maio R$0,10", "Junho R$160.000,00"])
        self.assertEqual(caso.comp_data_abertura_ultimo_reporte, "10/01/2025")
        self.assertEqual(avisos, [])

    def test_virada_de_ano_inclui_o_ano(self):
        caso = self._caso()
        dados, _ = ia.validar_mudanca("10/01/2025", "10/02/2026", "R$1,00")
        ia.aplicar_mudanca_respondida(caso, dados, [])
        linhas = caso.comp_mudanca_comportamento.split("\n")
        self.assertEqual((linhas[0], linhas[-1]), ("Setembro/2025 R$1.000,00", "Fevereiro/2026 R$1,00"))

    def test_valor_criado_respeita_total_do_periodo(self):
        for _ in range(30):
            caso = self._caso()
            dados, _ = ia.validar_mudanca("10/01/2025", "15/03/2026")
            avisos = []
            ia.aplicar_mudanca_respondida(caso, dados, avisos)
            pico = caso.comp_mudanca_comportamento.split("\n")[-1].split(" ")[-1]
            self.assertLessEqual(core_parse(pico), 500000.0)
            self.assertGreater(core_parse(pico), 100000.0)
            self.assertEqual(len(avisos), 1)

    def test_valor_informado_acima_do_total_gera_aviso(self):
        caso = self._caso()
        dados, _ = ia.validar_mudanca("10/01/2025", "15/03/2026", "R$900.000,00")
        avisos = []
        ia.aplicar_mudanca_respondida(caso, dados, avisos)
        self.assertIn("maior que o total", avisos[0])

    def test_regras_de_invencao_no_prompt(self):
        self.assertIn("rendaPresumida BAIXA", ia.SYSTEM_PROMPT_PF)
        self.assertIn("cargos aleatórios", ia.SYSTEM_PROMPT_PF)


def core_parse(v):
    from core import parse_valor_br
    return parse_valor_br(v)


class TestPerguntasKYC(unittest.TestCase):
    def _caso(self, **kw):
        return Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)", **kw)

    def test_sem_sim_nao_ha_perguntas(self):
        self.assertEqual(ia.faltas_kyc(self._caso()), [])

    def test_sim_sem_detalhes_pergunta_cada_campo(self):
        caso = self._caso(registro_societario="Sim", regiao_risco="Sim", pep="Sim", midia_negativa="Sim",
                          historico_pld="Sim", historico_fraude="Sim")
        self.assertEqual(ia.faltas_kyc(caso), [
            "reg_soc_razao_social", "reg_soc_data_abertura", "reg_soc_situacao_cadastral",
            "reg_soc_ramo_atividade", "cidade_estado", "tipo_regiao_risco", "tipo_regiao_risco_2",
            "tipo_pep", "descricao_pep", "midia_negativa_detalhe", "historico_pld_detalhe",
            "historico_fraude_detalhe"])

    def test_so_pergunta_o_que_faltou(self):
        caso = self._caso(registro_societario="Sim", reg_soc_razao_social="ACME LTDA",
                          reg_soc_data_abertura="01/02/2020", reg_soc_situacao_cadastral="Ativa",
                          reg_soc_ramo_atividade="Comércio", regiao_risco="Sim", cidade_estado="Foz do Iguaçu/PR",
                          tipo_regiao_risco="Região de Fronteira", pep="Sim", tipo_pep="PEP Titular",
                          descricao_pep="Vereador, carência até 2028")
        self.assertEqual(ia.faltas_kyc(caso), [])

    def test_outras_regioes_exige_nome_da_regiao(self):
        caso = self._caso(regiao_risco="Sim", cidade_estado="X/PA", tipo_regiao_risco="Outras Regiões de Risco")
        self.assertEqual(ia.faltas_kyc(caso), ["tipo_regiao_risco_2"])

    def test_pj_nao_pergunta_registro_societario_nem_cidade(self):
        caso = Caso(numero_caso="t", tipo_caso="Pessoa Jurídica (PJ)", registro_societario="Sim",
                    regiao_risco="Sim", tipo_regiao_risco="Região de Fronteira")
        self.assertEqual(ia.faltas_kyc(caso), [])

    def test_respostas_resolvem_as_faltas(self):
        caso = self._caso(pep="Sim", regiao_risco="Sim")
        ia.aplicar_respostas_kyc(caso, {"tipo_pep": "PEP Relacionado", "descricao_pep": "Esposa de prefeito",
                                        "cidade_estado": "Tabatinga/AM", "tipo_regiao_risco": "Região de Fronteira",
                                        "tipo_regiao_risco_2": "lixo"})
        self.assertEqual(ia.faltas_kyc(caso), [])
        self.assertEqual(caso.tipo_regiao_risco_2, "")  # só vale para "Outras Regiões de Risco"

    def test_ia_nao_preenche_tipos_por_padrao_mas_o_fechamento_sim(self):
        d = {"kyc": {"regiaoRisco": "Sim", "pep": "Sim", "descricaoPep": "Deputado"}}
        caso = ia.aplicar_dados_extraidos(self._caso(), d, HOJE)
        self.assertEqual((caso.tipo_regiao_risco, caso.tipo_pep), ("", ""))
        self.assertIn("tipo_pep", ia.faltas_kyc(caso))
        ia.completar_obrigatorios(caso, HOJE)
        self.assertEqual((caso.tipo_regiao_risco, caso.tipo_pep), ("Outras Regiões de Risco", "PEP Titular"))

    def test_descricao_da_regiao_e_outras_informacoes_em_lista(self):
        d = {"kyc": {"regiaoRisco": "Sim", "tipoRegiaoRisco": "Outras Regiões de Risco",
                     "descricaoRegiaoRisco": "Garimpo ilegal no Tapajós",
                     "outrasInformacoes": ["Compartilha dispositivo com 3 contas", "Exchange: Binance"]}}
        caso = ia.aplicar_dados_extraidos(self._caso(), d, HOJE)
        self.assertEqual(caso.tipo_regiao_risco_2, "Garimpo ilegal no Tapajós")
        self.assertEqual(caso.outras_info, "Compartilha dispositivo com 3 contas\nExchange: Binance")

    def test_regras_no_prompt(self):
        self.assertIn("UMA INFORMAÇÃO POR LINHA", ia.SYSTEM_PROMPT_PF)
        self.assertIn("descricaoRegiaoRisco", ia.SYSTEM_PROMPT_PJ)


class TestPerguntasKYCContrapartes(unittest.TestCase):
    def _caso(self):
        d = {"movimentacoes": {"periodo": "01/04/2026 até 30/06/2026", "totalCredito": "R$300.000,00",
                               "totalDebito": "R$100.000,00", "totalContrapartesCredito": "10",
                               "contrapartesCredito": [
                                   {"tipo": "Pessoa Física", "nome": "Ana", "porcentagem": "30%", "pep": "Sim",
                                    "pepDetalhe": "Vereadora, carência até 2028"},
                                   {"tipo": "Pessoa Física", "nome": "", "porcentagem": "20%", "pep": "Sim",
                                    "midiaNegativa": "Sim"},
                                   {"tipo": "Pessoa Física", "nome": "Beto", "porcentagem": "10%",
                                    "registroSocietario": "Sim", "regiaoRisco": "Sim"}],
                               "contrapartesDebito": [
                                   {"tipo": "Pessoa Física", "nome": "Caio", "porcentagem": "40%",
                                    "historicoPld": "Sim", "historicoFraude": "Sim"}]}}
        return ia.aplicar_dados_extraidos(Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)"), d, HOJE)

    def test_pergunta_por_contraparte_so_o_que_falta(self):
        caso = self._caso()
        self.assertEqual(ia.faltas_kyc(caso), [
            "cp__cred__1__pep_detalhe", "cp__cred__1__midia_negativa_detalhe",
            "cp__cred__2__registro_societario_detalhe", "cp__cred__2__regiao_risco_detalhe",
            "cp__deb__0__historico_pld_detalhe", "cp__deb__0__historico_fraude_detalhe"])

    def test_grupos_e_rotulos(self):
        caso = self._caso()
        self.assertEqual(ia.grupo_kyc(caso, "cp__cred__1__pep_detalhe"), "Contraparte de crédito 2")
        self.assertEqual(ia.grupo_kyc(caso, "cp__cred__2__regiao_risco_detalhe"), "Contraparte de crédito 3 — Beto")
        self.assertEqual(ia.grupo_kyc(caso, "cp__deb__0__historico_pld_detalhe"), "Contraparte de débito 1 — Caio")
        self.assertEqual(ia.rotulo_kyc(caso, "cp__cred__1__midia_negativa_detalhe")[0], "Mídia negativa")
        self.assertEqual(ia.grupo_kyc(caso, "cidade_estado"), "Cliente (KYC)")

    def test_respostas_vao_para_a_contraparte_certa(self):
        caso = self._caso()
        ia.aplicar_respostas_kyc(caso, {"cp__cred__1__pep_detalhe": "Prefeito, sem carência",
                                        "cp__deb__0__historico_pld_detalhe": "COAF 2025",
                                        "cp__cred__1__midia_negativa_detalhe": ""})
        self.assertEqual(caso.contrapartes_credito[1].pep_detalhe, "Prefeito, sem carência")
        self.assertEqual(caso.contrapartes_debito[0].historico_pld_detalhe, "COAF 2025")
        self.assertEqual(caso.contrapartes_credito[0].pep_detalhe, "Vereadora, carência até 2028")
        self.assertEqual(len(ia.faltas_kyc(caso)), 4)  # a resposta vazia segue pendente

    def test_regra_de_varias_contrapartes_no_prompt_e_schema(self):
        self.assertIn("MAIS DE UMA contraparte", ia.SYSTEM_PROMPT_PF)
        self.assertIn("CRIE uma entrada por contraparte", ia.SYSTEM_PROMPT_PJ)
        self.assertIn('"pepDetalhe"', ia.SYSTEM_PROMPT_PF)


class TestPerguntasKYCSocios(unittest.TestCase):
    def _caso(self):
        d = {"kyc": {"nomeEmpresa": "Padaria Estrela Ltda", "presencaOnline": "Sim", "fachadaEmpresa": "Não",
                     "presencaOnlineDetalhe": "ignorado",
                     "socios": [
                         {"nome": "Maria Souza", "pep": "Sim", "tipoPep": "PEP Titular",
                          "descricaoPep": "Vereadora, carência até 2028"},
                         {"nome": "", "pep": "Sim", "midiaNegativa": "Sim"},
                         {"nome": "Beto", "regiaoRisco": "Sim", "historicoPld": "Sim"},
                         {"nome": "", "idade": "50"}]}}
        return ia.aplicar_dados_extraidos(Caso(numero_caso="t", tipo_caso="Pessoa Jurídica (PJ)"), d, HOJE)

    def test_socio_sem_nome_so_entra_com_sinal(self):
        caso = self._caso()
        self.assertEqual([s.nome for s in caso.socios], ["Maria Souza", "", "Beto"])

    def test_presenca_e_fachada_so_sim_ou_nao(self):
        caso = self._caso()
        self.assertEqual((caso.presenca_online, caso.fachada_empresa), ("Sim", "Não"))
        self.assertFalse(hasattr(caso, "presenca_online_detalhe"))
        self.assertFalse(hasattr(caso, "fachada_empresa_detalhe"))
        self.assertNotIn("Detalhe", ia.SCHEMA_EXTRACAO_PJ.split('"socios"')[0].split('"presencaOnline"')[1][:80])

    def test_perguntas_por_socio(self):
        caso = self._caso()
        self.assertEqual(ia.faltas_kyc(caso), [
            "so__1__tipo_pep", "so__1__descricao_pep", "so__1__midia_negativa_detalhe",
            "so__2__tipo_regiao_risco", "so__2__historico_pld_detalhe"])
        self.assertEqual(ia.grupo_kyc(caso, "so__1__tipo_pep"), "Sócio 2")
        self.assertEqual(ia.grupo_kyc(caso, "so__2__tipo_regiao_risco"), "Sócio 3 — Beto")
        self.assertEqual(ia.rotulo_kyc(caso, "so__1__descricao_pep")[0], "Descrição do PEP e carência")
        self.assertEqual(ia.opcoes_kyc("so__2__tipo_regiao_risco"), ia.TIPOS_REGIAO_RISCO_1)
        self.assertIsNone(ia.opcoes_kyc("so__1__descricao_pep"))

    def test_respostas_vao_para_o_socio_certo_e_defaults_no_fechamento(self):
        caso = self._caso()
        ia.aplicar_respostas_kyc(caso, {"so__1__tipo_pep": "PEP Relacionado", "so__1__descricao_pep": "Filho de prefeito",
                                        "so__2__historico_pld_detalhe": "COAF 2025"})
        self.assertEqual((caso.socios[1].tipo_pep, caso.socios[1].descricao_pep), ("PEP Relacionado", "Filho de prefeito"))
        self.assertEqual(caso.socios[2].historico_pld_detalhe, "COAF 2025")
        self.assertEqual(caso.socios[0].descricao_pep, "Vereadora, carência até 2028")
        ia.completar_obrigatorios(caso, HOJE)
        self.assertEqual(caso.socios[2].tipo_regiao_risco, "Outras Regiões de Risco")

    def test_regras_pj_no_prompt(self):
        self.assertIn("2 sócios são PEP", ia.SYSTEM_PROMPT_PJ)
        self.assertIn("só \"Sim\" ou \"Não\"", ia.SYSTEM_PROMPT_PJ)


class TestFragmentacaoFracionamentoArredondamento(unittest.TestCase):
    def test_detectores(self):
        self.assertTrue(ia.menciona_fragmentacao("Houve fragmentação nos créditos."))
        self.assertFalse(ia.menciona_fragmentacao("Poucas contrapartes."))
        self.assertTrue(ia.menciona_fracionamento("alto fracionamento entre as contrapartes"))
        self.assertTrue(ia.menciona_fracionamento("valores fracionados"))
        self.assertTrue(ia.menciona_arredondamento_diverso("Diversas transações arredondadas nos créditos"))
        self.assertTrue(ia.menciona_arredondamento_diverso("muitas transações em perfil de arredondamento de milhar"))
        self.assertFalse(ia.menciona_arredondamento_diverso("84 transações de R$1.000,00 em arredondamento"))
        self.assertFalse(ia.menciona_arredondamento_diverso("Diversas contrapartes e saques."))

    def test_mensagem_traz_as_diretrizes(self):
        m = ia.montar_mensagem_usuario("Fragmentação e alto fracionamento; diversas transações arredondadas.")
        self.assertTrue(m.startswith("INVENÇÃO AUTORIZADA: NÃO\n"))
        for linha in ("FRAGMENTAÇÃO: SIM", "FRACIONAMENTO ENTRE CONTRAPARTES: SIM", "ARREDONDAMENTO DIVERSO: SIM"):
            self.assertIn(linha, m)
        m = ia.montar_mensagem_usuario("Cliente com renda baixa.")
        for linha in ("FRAGMENTAÇÃO: NÃO", "FRACIONAMENTO ENTRE CONTRAPARTES: NÃO", "ARREDONDAMENTO DIVERSO: NÃO"):
            self.assertIn(linha, m)

    def test_regras_no_prompt(self):
        for trecho in ("fragmentação = ALTO número de contrapartes", "CADA contraparte enviou ou recebeu",
                       "43 transações de R$1.000,00 nos créditos e 54 nos débitos", "prevalece sobre a regra 4"):
            self.assertIn(trecho, ia.SYSTEM_PROMPT_PF)

    def _caso(self, total_cp, pcts, ntrans, itens=()):
        d = {"movimentacoes": {"periodo": "01/04/2026 até 30/06/2026", "totalCredito": "R$100.000,00",
                               "totalDebito": "R$50.000,00", "totalContrapartesCredito": total_cp,
                               "contrapartesCredito": [{"tipo": "Pessoa Física", "nome": f"C{i}", "porcentagem": p,
                                                        "numTransacoes": ntrans} for i, p in enumerate(pcts)]},
             "thundera": {"arredondamento": "Sim", "arredondamentoItens": list(itens)}}
        return ia.aplicar_dados_extraidos(Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)"), d, HOJE)

    def test_fragmentacao_ok_nao_avisa(self):
        caso = self._caso("120", ["6%", "5%", "4%"], "80")
        self.assertEqual(ia.coerencia_extracao(caso, "fragmentação com alto fracionamento"), [])

    def test_fragmentacao_com_poucas_contrapartes_ou_concentracao_avisa(self):
        caso = self._caso("5", ["40%", "5%"], "10")
        txt = " | ".join(ia.coerencia_extracao(caso, "fragmentação e alto fracionamento"))
        self.assertIn("fragmentação, mas o total de contrapartes de crédito é 5", txt)
        self.assertIn("20% ou mais", txt)
        self.assertIn("menos de 20 transações", txt)

    def test_fragmentacao_e_fracionamento_juntos(self):
        txt = "Houve fragmentação e fracionamento nos créditos."
        self.assertTrue(ia.menciona_fragmentacao(txt) and ia.menciona_fracionamento(txt))
        m = ia.montar_mensagem_usuario(txt)
        self.assertIn("FRAGMENTAÇÃO: SIM", m)
        self.assertIn("FRACIONAMENTO ENTRE CONTRAPARTES: SIM", m)
        self.assertIn("os DOIS comportamentos existem ao mesmo tempo", ia.SYSTEM_PROMPT_PF)
        # só um dos termos não liga o outro
        self.assertIn("FRACIONAMENTO ENTRE CONTRAPARTES: NÃO", ia.montar_mensagem_usuario("Houve fragmentação."))

    def test_percentuais_diferentes_entre_si(self):
        self.assertIn("DIFERENTES entre si", ia.SYSTEM_PROMPT_PF)
        self.assertIn("NUNCA todas iguais", ia.SYSTEM_PROMPT_PF)
        iguais = self._caso("120", ["8%", "8%", "8%"], "80")
        self.assertIn("todas a mesma porcentagem (8%)", " ".join(ia.coerencia_extracao(iguais, "fragmentação")))
        variadas = self._caso("120", ["7%", "5%", "3,5%"], "80")
        self.assertEqual(ia.coerencia_extracao(variadas, "fragmentação"), [])

    def test_arredondamento_acima_do_total_avisa(self):
        itens = [{"credDeb": "Créditos", "quantidade": "43", "valor": "R$1.000,00"},
                 {"credDeb": "Créditos", "quantidade": "20", "valor": "R$2.000,00"},
                 {"credDeb": "Débitos", "quantidade": "54", "valor": "R$1.000,00"}]
        caso = self._caso("10", ["10%"], "5", itens)
        avisos = ia.coerencia_extracao(caso, "")  # créditos: 83.000 <= 100.000; débitos: 54.000 > 50.000
        self.assertEqual(len(avisos), 1)
        self.assertIn("arredondadas de débitos somam R$54.000,00", avisos[0])


class TestAplicar(unittest.TestCase):
    def test_narrativa_mudanca_de_comportamento(self):
        caso = ia.aplicar_dados_extraidos(Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)"), dados_joao(), HOJE)
        self.assertEqual(caso.comp_mudanca_comportamento.split("\n"), [
            "Novembro R$1.000,00", "Dezembro R$1.500,00", "Janeiro R$2.000,00",
            "Fevereiro R$0,00", "Março R$0,10", "Abril R$160.000,00"])

    def test_sem_mudanca_de_comportamento(self):
        d = dados_joao()
        d["thundera"]["mudancaComportamento"] = {"houve": "Não", "valorAproximado": ""}
        caso = ia.aplicar_dados_extraidos(Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)"), d, HOJE)
        self.assertEqual(caso.comp_mudanca_comportamento, "")

    def test_campos_mapeados_e_normalizados(self):
        caso = ia.aplicar_dados_extraidos(Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)"), dados_joao(), HOJE)
        self.assertEqual(caso.profissao_informada, "Auxiliar administrativo")
        self.assertEqual(caso.registro_profissional, "Sem registros profissionais")
        self.assertEqual(caso.renda_presumida, "R$1.200,00")
        self.assertEqual(caso.mov_periodo, "01/04/2026 até 30/09/2026")
        self.assertEqual(caso.contrapartes_credito[0].nome, "Marcos Vinícius Andrade")
        self.assertEqual(caso.contrapartes_credito[0].pep, "Não")
        self.assertEqual([a.valor for a in caso.arredondamento_itens][:3], ["R$1.000,00", "R$2.000,00", "R$5.000,00"])
        self.assertEqual([a.cred_deb for a in caso.arredondamento_itens], ["Créditos"] * 3 + ["Débitos"] * 3)
        self.assertEqual(caso.comp_data_abertura_ultimo_reporte, "10/01/2026")

    def test_nao_sobrescreve_com_vazio(self):
        caso = Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)", nome_cliente="Já digitado", idade="40")
        ia.aplicar_dados_extraidos(caso, {"kyc": {"nome": "", "idade": None}}, HOJE)
        self.assertEqual((caso.nome_cliente, caso.idade), ("Já digitado", "40"))

    def test_nao_toca_nos_campos_do_analista(self):
        caso = Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)", fator_gerador="A", data_alerta="B", sentenca="C")
        d = dados_joao()
        d["kyc"].update({"fatorGerador": "X", "sentenca": "Y", "dataAlerta": "Z"})
        ia.aplicar_dados_extraidos(caso, d, HOJE)
        self.assertEqual((caso.fator_gerador, caso.data_alerta, caso.sentenca), ("A", "B", "C"))

    def test_sem_periodo_usa_padrao(self):
        d = dados_joao()
        d["movimentacoes"]["periodo"] = ""
        caso = ia.aplicar_dados_extraidos(Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)"), d, HOJE)
        self.assertEqual(caso.mov_periodo, periodo_padrao(HOJE))
        self.assertEqual(caso.mov_periodo, "01/07/2026 até 01/09/2026")
        # a narrativa parte do período padrão: julho (pico) e cinco meses antes (fev..jun)
        self.assertTrue(caso.comp_mudanca_comportamento.startswith("Fevereiro R$1.000,00"))
        self.assertTrue(caso.comp_mudanca_comportamento.endswith("Julho R$160.000,00"))

    def test_formato_antigo_arredondamento_e_pix(self):
        d = {"thundera": {"arredondamento": "Sim", "arredondamentoQuantidade": "84", "arredondamentoValor": "1000",
                          "arredondamentoCredDeb": "Débitos", "pix": "Sim", "pixQuantidade": "5",
                          "pixMensagem": "pagamento", "pixCredDeb": "Créditos"}}
        caso = ia.aplicar_dados_extraidos(Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)"), d, HOJE)
        self.assertEqual((caso.arredondamento_itens[0].cred_deb, caso.arredondamento_itens[0].quantidade,
                          caso.arredondamento_itens[0].valor), ("Débitos", "84", "R$1.000,00"))
        self.assertEqual((caso.pix_itens[0].quantidade, caso.pix_itens[0].mensagem), ("5", "pagamento"))

    def test_normaliza_sim_nao_e_regiao(self):
        d = {"kyc": {"regiaoRisco": "sim", "tipoRegiaoRisco": "fronteira com o Paraguai", "pep": True,
                     "tipoPep": "relacionado a político", "descricaoPep": "Primo de deputado",
                     "midiaNegativa": "nao", "historicoPld": "Não"}}
        caso = ia.aplicar_dados_extraidos(Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)"), d, HOJE)
        self.assertEqual((caso.regiao_risco, caso.tipo_regiao_risco), ("Sim", "Região de Fronteira"))
        self.assertEqual((caso.pep, caso.tipo_pep), ("Sim", "PEP Relacionado"))
        self.assertEqual(caso.midia_negativa, "Não")

    def test_pj_aplica_empresa_e_socios(self):
        d = {"kyc": {"nomeEmpresa": "Mercado Alfa Ltda", "dataAbertura": "10/05/2019", "ramoAtividade": "Varejo",
                     "porte": "ME", "faturamentoPresumido": "R$80.000,00", "endereco": "Rua A, 10 - Recife/PE",
                     "nome": "NÃO USAR", "idade": "55",
                     "socios": [{"nome": "Carlos Souza", "idade": "52", "pep": "Sim", "regiaoRisco": "Não"},
                                {"nome": "", "idade": "30"}]},
             "movimentacoes": {}}
        caso = ia.aplicar_dados_extraidos(Caso(numero_caso="t", tipo_caso="Pessoa Jurídica (PJ)"), d, HOJE)
        self.assertEqual(caso.nome_empresa, "Mercado Alfa Ltda")
        self.assertEqual(caso.faturamento_presumido, "R$80.000,00")
        self.assertEqual(caso.nome_cliente, "")
        self.assertEqual(caso.idade, "")
        self.assertEqual(len(caso.socios), 1)
        # o tipo de PEP não é presumido: o app pergunta; o padrão só entra no fechamento
        self.assertEqual((caso.socios[0].pep, caso.socios[0].tipo_pep), ("Sim", ""))
        self.assertIn("so__0__tipo_pep", ia.faltas_kyc(caso))
        ia.completar_obrigatorios(caso, HOJE)
        self.assertEqual(caso.socios[0].tipo_pep, "PEP Titular")
        self.assertEqual(caso.genero, "")

    def test_under18_responsavel_legal(self):
        d = {"kyc": {"nome": "Pedro Lima", "idade": "16", "responsavelLegal": {
            "nome": "Marta Lima", "rendaPresumida": "3000", "historicoPld": "Não"}}}
        caso = ia.aplicar_dados_extraidos(Caso(numero_caso="t", tipo_caso="Under 18"), d, HOJE)
        self.assertEqual((caso.rep_nome, caso.rep_renda_presumida), ("Marta Lima", "R$3.000,00"))
        pf = ia.aplicar_dados_extraidos(Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)"), d, HOJE)
        self.assertEqual(pf.rep_nome, "")

    def test_outras_movimentacoes_tipo_normalizado(self):
        d = {"outrasMovimentacoes": [{"tipo": "saque em espécie", "info": "R$1.000"},
                                     {"tipo": "Cartão de crédito", "info": "R$500"},
                                     {"tipo": "algo", "info": ""}]}
        caso = ia.aplicar_dados_extraidos(Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)"), d, HOJE)
        self.assertEqual([o.tipo for o in caso.outras_movimentacoes], ["Saques", "Gastos Cartão de Crédito"])


class TestCompletar(unittest.TestCase):
    def test_pf_vazio_recebe_neutros(self):
        caso = ia.completar_obrigatorios(Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)"), HOJE)
        for attr in ("nome_cliente", "idade", "cidade_estado", "ultima_atualizacao_cadastral", "registro_profissional"):
            self.assertEqual(getattr(caso, attr), NEUTRO, attr)
        self.assertEqual(caso.renda_presumida, "R$0,00")
        self.assertEqual((caso.mov_total_credito, caso.mov_total_debito), ("R$0,00", "R$0,00"))
        self.assertEqual((caso.mov_total_contrapartes_credito, caso.mov_total_contrapartes_debito), ("0", "0"))
        self.assertEqual(caso.mov_periodo, "01/07/2026 até 01/09/2026")

    def test_pj_vazio_recebe_neutros(self):
        caso = ia.completar_obrigatorios(Caso(numero_caso="t", tipo_caso="Pessoa Jurídica (PJ)"), HOJE)
        for attr in ("nome_empresa", "data_abertura", "ramo_atividade", "porte", "endereco"):
            self.assertEqual(getattr(caso, attr), NEUTRO, attr)
        self.assertEqual(caso.faturamento_presumido, "R$0,00")
        self.assertEqual(caso.nome_cliente, "")

    def test_nao_completa_campos_do_analista_nem_genero(self):
        caso = ia.completar_obrigatorios(Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)"), HOJE)
        self.assertEqual((caso.fator_gerador, caso.data_alerta, caso.sentenca, caso.genero), ("", "", "", ""))

    def test_preserva_o_que_ja_existe(self):
        caso = Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)", nome_cliente="Ana", idade="30",
                    mov_periodo="01/01/2026 até 28/02/2026", mov_total_credito="R$10,00")
        ia.completar_obrigatorios(caso, HOJE)
        self.assertEqual((caso.nome_cliente, caso.idade, caso.mov_total_credito), ("Ana", "30", "R$10,00"))
        self.assertEqual(caso.mov_periodo, "01/01/2026 até 28/02/2026")

    def test_genero_ambiguo_fica_vazio_e_conhecido_e_inferido(self):
        d = {"kyc": {"nome": "Alex Santos"}}
        c1 = ia.completar_obrigatorios(ia.aplicar_dados_extraidos(Caso(numero_caso="t", tipo_caso="Cripto"), d, HOJE), HOJE)
        self.assertEqual(c1.genero, "")
        d = {"kyc": {"nome": "Mariana Costa Ribeiro"}}
        c2 = ia.aplicar_dados_extraidos(Caso(numero_caso="t", tipo_caso="Cripto"), d, HOJE)
        self.assertEqual(c2.genero, "F")


class TestCoerencia(unittest.TestCase):
    def _caso(self, cps, total="R$100.000,00", n_cp="20"):
        c = Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)", mov_total_credito=total,
                 mov_total_contrapartes_credito=n_cp)
        c.contrapartes_credito = cps
        return c

    def test_valor_calculado_a_partir_da_porcentagem(self):
        from core import ContraparteMovimentacao as CP
        c = self._caso([CP(nome="A", porcentagem="30%")])
        ia.coerencia_extracao(c)
        self.assertEqual(c.contrapartes_credito[0].valor, "R$30.000,00")

    def test_porcentagem_calculada_a_partir_do_valor(self):
        from core import ContraparteMovimentacao as CP
        c = self._caso([CP(nome="A", valor="R$25.000,00")])
        ia.coerencia_extracao(c)
        self.assertEqual(c.contrapartes_credito[0].porcentagem, "25%")

    def test_soma_acima_de_100_e_reescalada(self):
        from core import ContraparteMovimentacao as CP
        c = self._caso([CP(nome="A", porcentagem="60%", valor="R$60.000,00"),
                        CP(nome="B", porcentagem="60%", valor="R$60.000,00")])
        avisos = ia.coerencia_extracao(c, "texto com concentração")
        self.assertTrue(any("acima de 100%" in a for a in avisos))
        pcts = [float(x.porcentagem.rstrip("%")) for x in c.contrapartes_credito]
        self.assertAlmostEqual(sum(pcts), 100.0, delta=0.2)
        self.assertEqual(c.contrapartes_credito[0].valor, "R$50.000,00")

    def test_total_de_contrapartes_vago_vira_numero(self):
        from core import ContraparteMovimentacao as CP
        c = self._caso([CP(nome="A", porcentagem="10%", valor="R$10.000,00")] * 3, n_cp="diversas")
        avisos = ia.coerencia_extracao(c)
        self.assertTrue(c.mov_total_contrapartes_credito.isdigit())
        self.assertGreaterEqual(int(c.mov_total_contrapartes_credito), 3 + 5)
        self.assertTrue(any("diversas" in a for a in avisos))

    def test_total_menor_que_listadas_e_ajustado(self):
        from core import ContraparteMovimentacao as CP
        c = self._caso([CP(nome=str(i), porcentagem="5%", valor="R$5.000,00") for i in range(5)], n_cp="3")
        ia.coerencia_extracao(c)
        self.assertEqual(c.mov_total_contrapartes_credito, "5")

    def test_aviso_de_concentracao_so_sem_autorizacao(self):
        from core import ContraparteMovimentacao as CP
        c = self._caso([CP(nome="Grande", porcentagem="70%", valor="R$70.000,00")])
        self.assertTrue(any("concentração" in a for a in ia.coerencia_extracao(c, "Cliente recebeu de várias pessoas")))
        self.assertFalse(any("concentração" in a for a in ia.coerencia_extracao(c, "Há concentração em uma contraparte")))
        self.assertFalse(any("concentração" in a for a in ia.coerencia_extracao(c, "valores aleatórios")))
        self.assertEqual(c.contrapartes_credito[0].porcentagem, "70%")  # só avisa, não altera

    def test_caso_do_manual_nao_gera_avisos(self):
        caso = ia.aplicar_dados_extraidos(Caso(numero_caso="t", tipo_caso="Pessoa Física (PF)"), dados_joao(), HOJE)
        self.assertEqual(ia.coerencia_extracao(caso, "Cliente João"), [])
        self.assertEqual(caso.contrapartes_credito[0].valor, "R$70.000,00")


class TestInvencao(unittest.TestCase):
    def test_detecta(self):
        for t in ("valores ALEATÓRIOS", "aleatorio", "Invente os dados", "pode inventar", "à sua escolha",
                  "a sua escolha", "de livre escolha", "crie valores plausíveis", "gere dados"):
            self.assertTrue(ia.autoriza_invencao(t), t)

    def test_nao_detecta(self):
        for t in ("Cliente João, 34 anos", "", "escolha da conta", "Recebeu R$300.000,00 de 12 contrapartes"):
            self.assertFalse(ia.autoriza_invencao(t), t)


if __name__ == "__main__":
    unittest.main()
