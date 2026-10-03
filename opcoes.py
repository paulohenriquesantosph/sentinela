# -*- coding: utf-8 -*-
"""
Opções e rubricas extraídas literalmente do artefato Sentinela original
(razões de clear/cancelamento, jurisprudências e os scorecards de
qualidade AML Nupag / AML NuInvest). Gerado automaticamente a partir do
HTML original para garantir fidelidade -- não foi reescrito à mão.
"""

# Desfechos possíveis do caso (o selo do dossiê muda de cor conforme a escolha:
# Clear = verde, Reportar = âmbar, Reportar e Cancelar = vermelho, Cancelar = neutro).
DILIGENCIAS = ["Clear (arquivar)", "Reportar", "Reportar e Cancelar", "Cancelar"]

RAZOES_CLEAR = [
  "Conta com bloqueio judicial",
  "Contrapartes sem risco",
  "Indeferido pelo MLRO",
  "Indício de idoneidade da empresa",
  "KYC sem risco",
  "Outro",
  "Reporte recente sem novos indícios",
  "Sem indícios de estruturação das operações",
  "Volume transacionado de acordo com capacidade financeira"
]

RAZOES_CANCELAMENTO = [
  "Cancelamento de Conta Investimento (NuInvest)",
  "Encerramento de Conta Vinculada",
  "Fortes e recorrentes indícios de Lavagem de Dinheiro",
  "KYC Ops - PEP, Sanções e Mídia Negativa",
  "KYC EDD PJ",
  "Mídia Negativa",
  "Processos Criminais de Risco Elevado",
  "SAC PF E PJ",
  "Suspeita de Financiamento ao Terrorismo",
  "Suspeitas de Conta Laranja/Passagem ou Empresa de Fachada",
  "Titular com Colisões Cadastrais com Fraudadores ou com Movimentações Relevantes com Fraudadores",
  "Titular com Movimentação Suspeita além de Apresentar Atividade Sensível ou de Risco",
  "Titular com Suspeitas de Atividade Ilegal",
  "Titular Presente em Listas Restritas Internas ou Listas de Pessoas Sancionadas"
]

JURISPRUDENCIA_NUPAGAMENTOS = [
  "Ausência de Resposta ao EDD",
  "Movimentação Expressiva com Comportamento Suspeito e sem Fundamentação Econômico Financeira Identificada",
  "Movimentação Expressiva com Contrapartes sem Relação com a Atividade Exercida pela Titular",
  "Movimentação Expressiva Acompanhada por Fragmentação",
  "Movimentação Expressiva Acompanhada por Titular com Atividade Sensível/de Risco",
  "Movimentação Expressiva com Contrapartes de Risco",
  "Movimentação Expressiva e Injustificada Acompanhada por Titular/Contraparte Menor de Idade",
  "Movimentação Suspeita em Regiões de Risco ou Distantes do Endereço da Sede da Empresa",
  "Movimentação Suspeita, em Regiões de Risco ou distantes do Endereço de Cadastro do Titular",
  "Movimentações Atípicas com Criptoativos",
  "Movimentações Atípicas em Espécie",
  "Movimentações Expressivas com Indícios de Sonegação Fiscal",
  "Suspeitas de Conta Laranja/Passagem",
  "Suspeitas de Empresa de Fachada",
  "Titular com Fraude Confirmada e/ou Colisões Cadastrais ou Concentração Transacional com Fraudadores"
]

JURISPRUDENCIA_REPORTAR_NUINVEST = [
  "Gestão e Captação Irregular",
  "Menor de Idade com Uso Incorreto da Conta e Movimentação Incompatível e/ou Atípica.",
  "Movimentação Expressiva Acompanhada por Titular com Atividade Sensível/de Risco",
  "Movimentação Incompatível e/ou Atípica com Comportamento Suspeito",
  "Movimentação Incompatível e/ou Atípica com Perfil de Risco",
  "Movimentação Suspeita, em Regiões de Risco ou Distantes do Endereço de Cadastro do Titular",
  "Uso de Terceiro"
]

JURISPRUDENCIA_REPORTAR_CANCELAR_NUINVEST = [
  "Incluído em Listagem e/ou em Mídia Negativa de Terrorismo e/ou Armas de Destruição em Massa, bem como Proibição Temporária de Operação em Investimentos pela CVM.",
  "Menor de Idade em Mercado Futuro, a Termo e Opções",
  "Money Pass",
  "Movimentação Incompatível e/ou Atípica e Possuidor de Processos Jurídicos Relacionados à PLD",
  "Suspeita de Atividade Ilegal"
]

SCORECARD_NUPAG = [
  {
    "categoria": "Customer Critical",
    "peso": 0.15,
    "drivers": [
      {
        "nome": "Foi suprimida informação ou movimentação relevante",
        "aplicabilidade": "Deve ser utilizado quando o analista suprimir alguma informação relevante que foi gerada pelas automações de KYC, resumo de movimentações, entre outras."
      },
      {
        "nome": "Faltou inserir registro de Profissional Liberal e/ou Pessoa Obrigada em casos de Alto Risco",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de inserir o registro no conselho de classe nas ocasiões em que o cliente for profissional liberal ou pessoa obrigada, e a diligência for de alto risco."
      },
      {
        "nome": "Faltou incluir macro e/ou processo de alertas específicos",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de inserir macro obrigatória para o procedimento ou alerta."
      },
      {
        "nome": "Deixou de utilizar medidas de EDD",
        "aplicabilidade": "Deve ser utilizado quando o analistas deixa de fazer pesquisas de EDD que os procedimentos vigentes dizem ser obrigatórias."
      },
      {
        "nome": "Deixou de acrescentar a descrição da fachada ou rede social, e/ou inclusão dos links",
        "aplicabilidade": "Deve ser utilizado para os casos de PJ em que o analista não realiza a descrição da fachada e/ou das redes sociais, e/ou não incluiu os respectivos links."
      },
      {
        "nome": "Faltou a argumentação de alguma alínea inserida",
        "aplicabilidade": "Deve ser utilizado quando o analista insere uma alínea sem a respectiva argumentação no parecer."
      },
      {
        "nome": "Faltou inserir alínea de argumentação",
        "aplicabilidade": "Deve ser utilizado quando o analista realiza a argumentação do comportamento mas não insere a alínea, seja de alta ou baixa criticidade."
      },
      {
        "nome": "Faltou citar as principais contrapartes de origem ou destino dos valores",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de citar as principais contrapartes no parecer."
      },
      {
        "nome": "Faltou incluir alínea de maior criticidade",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de incluir alíneas classificadas como de maior criticidade, e não argumentou no parecer."
      },
      {
        "nome": "Parecer genérico sem especificidade e/ou mitigadores incluídos",
        "aplicabilidade": "Deve ser utilizado para casos clear em que o analista faz o parecer manual, mas deixa de incluir todos os mitigadores necessários."
      },
      {
        "nome": "Desencontro de informações na análise (storytelling inconsistente)",
        "aplicabilidade": "Deve ser utilizado quando o analista insere informações em desencontro durante a análise, ou quando a \"história\" contada não possuem relação com os indícios identificados."
      },
      {
        "nome": "Faltou incluir exemplos de mensagens Pix relevantes para o caso",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de incluir mensagens Pix que sejam relevantes para o caso, ainda que sejam apenas para corroborar comportamentos já identificados."
      },
      {
        "nome": "Caso sem cabimento para análise simplificada",
        "aplicabilidade": "Deve ser utilizado sempre que o analista utiliza algum procedimento de análise simplificada sem que os requisitos para este tenham sido cumpridos."
      },
      {
        "nome": "Caso não deveria ter sido Cancelado",
        "aplicabilidade": "Deve ser utilizado quando o analista faz o encerramento do relacionamento sozinho, sendo que não era uma hipótese de cancelamento."
      },
      {
        "nome": "Faltou análise da mídia negativa",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de analisar mídia negativa do cliente ou de contraparte. Exceto mídias de amplo conhecimento nacional."
      }
    ]
  },
  {
    "categoria": "Business Critical",
    "peso": 0.15,
    "drivers": [
      {
        "nome": "Faltou o preenchimento de widget obrigatório",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de preencher algum widget obrigatório no Holmes."
      },
      {
        "nome": "Não foi aberto alerta manual para encerramento de conta vinculada",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de abrir alerta para encerramento de conta vinculada."
      },
      {
        "nome": "[Varys] Não realizou os ajustes necessários",
        "aplicabilidade": "Deve ser utilizado quando o analista não realizou os ajustes necessários no parecer do Varys."
      },
      {
        "nome": "[Varys] Realizou ajustes desnecessários",
        "aplicabilidade": "Deve ser utilizado quando o analista realizou ajustes desnecessários no parecer do Varys."
      },
      {
        "nome": "Caso deveria ter sido recomendado para Fila de Altíssimo Risco",
        "aplicabilidade": "Deve ser utilizado quando o caso for uma hipótese de envio para a fila de altíssimo risco e o analista não enviou."
      },
      {
        "nome": "Caso não deveria ter sido recomendado para Fila de Altíssimo Risco",
        "aplicabilidade": "Deve ser utilizado quando o analista recomendar o caso indevidamente para a fila de altíssimo risco."
      },
      {
        "nome": "Caso deveria ter sido escalado ao MLRO",
        "aplicabilidade": "Deve ser utilizado quando o caso for uma hipótese de envio para do MLRO e o analista não enviou."
      },
      {
        "nome": "Utilização de porcentagem no parecer",
        "aplicabilidade": "Deve ser utilizado quando o analista replicar no parecer os percentuais movimentados com as contrapartes, que já constam no resumo de movimentação."
      },
      {
        "nome": "Utilizou indevidamente termos gramaticais particulares do Nubank",
        "aplicabilidade": "Deve ser utilizado sempre que o analista utilizar termos internos que não são de amplo conhecimento, inclusive em inglês."
      },
      {
        "nome": "Utilizou indevidamente nomes de pessoas internas no reporte (MLRO, etc)",
        "aplicabilidade": "Deve ser utilizado quando o analista mencionar no reporte o nome de pessoas internas."
      }
    ]
  },
  {
    "categoria": "Regulatory Critical",
    "peso": 1.0,
    "drivers": [
      {
        "nome": "Caso deveria ter sido Reportado ao COAF",
        "aplicabilidade": "Deve ser utilizado quando o analista finalizar o caso como clear, sendo que na verdade deveria ter sido comunicado ao COAF."
      },
      {
        "nome": "Caso deveria ter sido Clear",
        "aplicabilidade": "Deve ser utilizado quando o analista comunicar ao COAF um caso que deveria ter sido clear."
      },
      {
        "nome": "Caso deveria ter sido cancelado",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de cancelar um caso que estava na sua alçada."
      },
      {
        "nome": "Caso alterado após a conclusão do Reporte",
        "aplicabilidade": "Deve ser utilizado quando o analista altera alguma informação da análise após a conclusão do reporte e não informa sobre o ocorrido."
      },
      {
        "nome": "Acrescentou dados que invalidam o Reporte ao COAF",
        "aplicabilidade": "Deve ser utilizado quando o analista inclui na análise dados que invalidam o reporte como dados fiscais ou de ordens judiciais."
      },
      {
        "nome": "Cliente já reportado dentro do período de um mês com os mesmos fatores reincidentes",
        "aplicabilidade": "Deve ser utilizado quando o analista comunica um cliente ao COAF no período de um mês do último reporte, pelos mesmos motivos."
      }
    ]
  },
  {
    "categoria": "Business Intelligence",
    "peso": 0.0,
    "drivers": [
      {
        "nome": "Processo interno insuficiente",
        "aplicabilidade": "Deve ser utilizado quando QA identifica que o analista aplicou corretamente o procedimento vigente, mas este apresenta deficiências."
      },
      {
        "nome": "Ausência de dados por erros de automação",
        "aplicabilidade": "Deve ser utilizado quando houver a ausência de dados na análise por conta de erros de automação."
      },
      {
        "nome": "[Varys] Foi identificada alucinação",
        "aplicabilidade": "Deve ser utilizado quando for identificada alucinação no parecer do Varys, ainda que corrigido pelo analista."
      },
      {
        "nome": "[Varys] Oportunidades de melhorias identificadas",
        "aplicabilidade": "Deve ser utilizado quando QA identificar oportunidades de melhorias para o Varys."
      },
      {
        "nome": "Fatores adicionais complementariam o caso",
        "aplicabilidade": "Deve ser utilizado quando pesquisas adicionais complementariam o caso, ainda que não sejam obrigatórias com base nos procedimentos vigentes."
      },
      {
        "nome": "Descrição de contraparte com erro",
        "aplicabilidade": "Deve ser utilizado quando houver erro na descrição das contrapartes."
      },
      {
        "nome": "Link do ofício judicial incorreto",
        "aplicabilidade": "Deve ser utilizado quando se tratar de alerta de ofícios judiciais e o link do ofício foi inserido incorretamente."
      },
      {
        "nome": "Cabimento de Alínea de menor criticidade",
        "aplicabilidade": "Deve ser utilizado quando o analista não insere alínea de menor criticidade e nem argumenta o risco relacionado. Se houver apenas a argumentação ou apenas a alínea, torna-se passível de pontuação, ainda que seja alínea de menor criticidade."
      },
      {
        "nome": "Erro ortográfico/gramatical",
        "aplicabilidade": "Deve ser utilizado quando for identificado erro gramatical ou ortográfico que comprometa o entendimento do texto ou que estejam em evidente desconformidade com as normas da língua portuguesa."
      }
    ]
  }
]

SCORECARD_NUINVEST = [
  {
    "categoria": "Customer Critical",
    "peso": 0.15,
    "drivers": [
      {
        "nome": "Foi suprimida informação ou movimentação relevante",
        "aplicabilidade": "Deve ser utilizado quando o analista suprimir alguma informação relevante que foi gerada pelas automações de KYC, resumo de movimentações, entre outras."
      },
      {
        "nome": "Faltou inserir registro de Profissional Liberal e/ou Pessoa Obrigada em casos de Alto Risco",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de inserir o registro no conselho de classe nas ocasiões em que o cliente for profissional liberal ou pessoa obrigada, e a diligência for de alto risco."
      },
      {
        "nome": "Faltou incluir perfil Suitability ou incluiu incorretamente",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de incluir o perfil Suitability ou inclui incorretamente."
      },
      {
        "nome": "Faltou incluir macro e/ou processo de alertas específicos",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de inserir macro obrigatória para o procedimento ou alerta."
      },
      {
        "nome": "Deixou de utilizar medidas de EDD",
        "aplicabilidade": "Deve ser utilizado quando o analistas deixa de fazer pesquisas de EDD que os procedimentos vigentes dizem ser obrigatórias."
      },
      {
        "nome": "Deixou de acrescentar a descrição da fachada ou rede social, e/ou inclusão dos links",
        "aplicabilidade": "Deve ser utilizado para os casos de PJ em que o analista não realiza a descrição da fachada e/ou das redes sociais, e/ou não incluiu os respectivos links."
      },
      {
        "nome": "Faltou a argumentação de alguma alínea inserida",
        "aplicabilidade": "Deve ser utilizado quando o analista insere uma alínea sem a respectiva argumentação no parecer."
      },
      {
        "nome": "Faltou inserir alínea de argumentação",
        "aplicabilidade": "Deve ser utilizado quando o analista realiza a argumentação do comportamento mas não insere a alínea, seja de alta ou baixa criticidade."
      },
      {
        "nome": "Faltou citar as principais contrapartes de origem ou destino dos valores",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de citar as principais contrapartes no parecer."
      },
      {
        "nome": "Faltou incluir alínea de maior criticidade",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de incluir alíneas classificadas como de maior criticidade, e não argumentou no parecer."
      },
      {
        "nome": "Parecer genérico sem especificidade e/ou mitigadores incluídos",
        "aplicabilidade": "Deve ser utilizado para casos clear em que o analista faz o parecer manual, mas deixa de incluir todos os mitigadores necessários."
      },
      {
        "nome": "Desencontro de informações na análise (storytelling inconsistente)",
        "aplicabilidade": "Deve ser utilizado quando o analista insere informações em desencontro durante a análise, ou quando a \"história\" contada não possuem relação com os indícios identificados."
      },
      {
        "nome": "Faltou incluir exemplos de mensagens Pix relevantes para o caso",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de incluir mensagens Pix que sejam relevantes para o caso, ainda que sejam apenas para corroborar comportamentos já identificados."
      },
      {
        "nome": "Caso sem cabimento para análise simplificada",
        "aplicabilidade": "Deve ser utilizado sempre que o analista utiliza algum procedimento de análise simplificada sem que os requisitos para este tenham sido cumpridos."
      },
      {
        "nome": "Caso não deveria ter sido Cancelado",
        "aplicabilidade": "Deve ser utilizado quando o analista faz o encerramento do relacionamento sozinho, sendo que não era uma hipótese de cancelamento."
      },
      {
        "nome": "Faltou análise da mídia negativa",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de analisar mídia negativa do cliente ou de contraparte. Exceto mídias de amplo conhecimento nacional."
      }
    ]
  },
  {
    "categoria": "Business Critical",
    "peso": 0.15,
    "drivers": [
      {
        "nome": "Faltou o preenchimento de widget obrigatório",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de preencher algum widget obrigatório no Holmes."
      },
      {
        "nome": "Não foi aberto alerta manual para encerramento de conta vinculada",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de abrir alerta para encerramento de conta vinculada."
      },
      {
        "nome": "Havia motivos para que houvesse o questionamento de recursos",
        "aplicabilidade": "Deve ser utilizado quando o caso se enquadra em uma das situações para questionamento dos recursos e o analista não fez."
      },
      {
        "nome": "O cliente deveria ser alto risco [equivalente a “especial atenção”]",
        "aplicabilidade": "Deve ser utilizado quando o analista não classifica o cliente como alto risco e deveria."
      },
      {
        "nome": "[Varys] Não realizou os ajustes necessários",
        "aplicabilidade": "Deve ser utilizado quando o analista não realizou os ajustes necessários no parecer do Varys."
      },
      {
        "nome": "[Varys] Realizou ajustes desnecessários",
        "aplicabilidade": "Deve ser utilizado quando o analista realizou ajustes desnecessários no parecer do Varys."
      },
      {
        "nome": "Caso deveria ter sido recomendado para Fila de Altíssimo Risco",
        "aplicabilidade": "Deve ser utilizado quando o caso for uma hipótese de envio para a fila de altíssimo risco e o analista não enviou."
      },
      {
        "nome": "Caso não deveria ter sido recomendado para Fila de Altíssimo Risco",
        "aplicabilidade": "Deve ser utilizado quando o analista recomendar o caso indevidamente para a fila de altíssimo risco."
      },
      {
        "nome": "Caso deveria ter sido escalado ao MLRO",
        "aplicabilidade": "Deve ser utilizado quando o caso for uma hipótese de envio para do MLRO e o analista não enviou."
      },
      {
        "nome": "Utilização de porcentagem no parecer",
        "aplicabilidade": "Deve ser utilizado quando o analista replicar no parecer os percentuais movimentados com as contrapartes, que já constam no resumo de movimentação."
      },
      {
        "nome": "Utilizou indevidamente termos gramaticais particulares do Nubank",
        "aplicabilidade": "Deve ser utilizado sempre que o analista utilizar termos internos que não são de amplo conhecimento, inclusive em inglês."
      },
      {
        "nome": "Utilizou indevidamente nomes de pessoas internas no reporte (MLRO, etc)",
        "aplicabilidade": "Deve ser utilizado quando o analista mencionar no reporte o nome de pessoas internas."
      }
    ]
  },
  {
    "categoria": "Regulatory Critical",
    "peso": 1.0,
    "drivers": [
      {
        "nome": "Caso deveria ter sido Reportado ao COAF",
        "aplicabilidade": "Deve ser utilizado quando o analista finalizar o caso como clear, sendo que na verdade deveria ter sido comunicado ao COAF."
      },
      {
        "nome": "Caso deveria ter sido Clear",
        "aplicabilidade": "Deve ser utilizado quando o analista comunicar ao COAF um caso que deveria ter sido clear."
      },
      {
        "nome": "Caso deveria ter sido cancelado",
        "aplicabilidade": "Deve ser utilizado quando o analista deixa de cancelar um caso que estava na sua alçada."
      },
      {
        "nome": "Caso alterado após a conclusão do Reporte",
        "aplicabilidade": "Deve ser utilizado quando o analista altera alguma informação da análise após a conclusão do reporte e não informa sobre o ocorrido."
      },
      {
        "nome": "Acrescentou dados que invalidam o Reporte ao COAF",
        "aplicabilidade": "Deve ser utilizado quando o analista inclui na análise dados que invalidam o reporte como dados fiscais ou de ordens judiciais."
      },
      {
        "nome": "Cliente já reportado dentro do período de um mês com os mesmos fatores reincidentes",
        "aplicabilidade": "Deve ser utilizado quando o analista comunica um cliente ao COAF no período de um mês do último reporte, pelos mesmos motivos."
      }
    ]
  },
  {
    "categoria": "Business Intelligence",
    "peso": 0.0,
    "drivers": [
      {
        "nome": "Processo interno insuficiente",
        "aplicabilidade": "Deve ser utilizado quando QA identifica que o analista aplicou corretamente o procedimento vigente, mas este apresenta deficiências."
      },
      {
        "nome": "Ausência de dados por erros de automação",
        "aplicabilidade": "Deve ser utilizado quando houver a ausência de dados na análise por conta de erros de automação."
      },
      {
        "nome": "[Varys] Foi identificada alucinação",
        "aplicabilidade": "Deve ser utilizado quando for identificada alucinação no parecer do Varys, ainda que corrigido pelo analista."
      },
      {
        "nome": "[Varys] Oportunidades de melhorias identificadas",
        "aplicabilidade": "Deve ser utilizado quando QA identificar oportunidades de melhorias para o Varys."
      },
      {
        "nome": "Fatores adicionais complementariam o caso",
        "aplicabilidade": "Deve ser utilizado quando pesquisas adicionais complementariam o caso, ainda que não sejam obrigatórias com base nos procedimentos vigentes."
      },
      {
        "nome": "Descrição de contraparte com erro",
        "aplicabilidade": "Deve ser utilizado quando houver erro na descrição das contrapartes."
      },
      {
        "nome": "Link do ofício judicial incorreto",
        "aplicabilidade": "Deve ser utilizado quando se tratar de alerta de ofícios judiciais e o link do ofício foi inserido incorretamente."
      },
      {
        "nome": "Cabimento de Alínea de menor criticidade",
        "aplicabilidade": "Deve ser utilizado quando o analista não insere alínea de menor criticidade e nem argumenta o risco relacionado. Se houver apenas a argumentação ou apenas a alínea, torna-se passível de pontuação, ainda que seja alínea de menor criticidade."
      },
      {
        "nome": "Erro ortográfico/gramatical",
        "aplicabilidade": "Deve ser utilizado quando for identificado erro gramatical ou ortográfico que comprometa o entendimento do texto ou que estejam em evidente desconformidade com as normas da língua portuguesa."
      }
    ]
  }
]
