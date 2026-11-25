# Tutoriais animados do manual

Os GIFs em `videos/` são gerados a partir do app real, com a resposta da IA **simulada** (`cenas/*.json`) e a
gravação na base simulada como bem-sucedida. Nada é gravado de verdade.

Para regerar (precisa do Google Chrome e de `pip install playwright pillow` num ambiente separado):

```
mkdir -p /tmp/sentinela_demo && echo kyc > /tmp/cena.txt
DEMO_CENA_ARQ=/tmp/cena.txt SENTINELA_DATA_DIR=/tmp/sentinela_demo \
  streamlit run tools/videos/app_demo.py --server.port 8599 --server.headless true &
DEMO_CENA_ARQ=/tmp/cena.txt python tools/videos/gravar.py todas      # ou: inicio | kyc | mov | comp | final
```

Rode a gravação com `SENTINELA_VOLUME_DOSSIES` e `SENTINELA_SQL_WAREHOUSE_ID` indefinidas, e reinicie o app de
demonstração se apagar a pasta de dados.
