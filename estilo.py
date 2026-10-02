# -*- coding: utf-8 -*-
"""
Sentinela PLD - Camada visual (Databricks / Streamlit)
========================================================

Este módulo concentra TODO o visual do app, replicando o design do artefato
original: paleta bege/roxo, fontes (Montserrat, Source Serif 4, IBM Plex
Sans/Mono), cartões com borda grossa e sombra deslocada, carimbo rotacionado
e a arte de robôs no fundo.

IMPORTANTE -- por que st.html() e não st.markdown():
    O st.markdown() passa o conteúdo por um parser de Markdown antes de
    renderizar o HTML. Isso faz com que asteriscos dentro de comentários CSS
    (/* ... */) sejam interpretados como itálico, quebrando o bloco e
    fazendo o CSS cru aparecer como texto visível na tela.
    O st.html() (Streamlit >= 1.33) injeta o HTML direto, sem parser de
    markdown no meio -- é o jeito correto e estável de fazer isso.

Os valores de cor, tamanho, borda e sombra abaixo foram copiados do CSS do
artefato original, não estimados.
"""

import streamlit as st


# ---------------------------------------------------------------------------
# Paleta (idêntica ao :root do artefato original)
# ---------------------------------------------------------------------------
PAPER = "#EEE3CE"
PAPER_ALT = "#F3EADA"
PAPER_STRONG = "#DFC89A"
INK = "#2A2035"
INK_SOFT = "#6C4E97"
LINE = "#C9B6DE"
ACCENT = "#6C4E97"
PURPLE_DEEP = "#3E2A63"
PURPLE_SOFT = "#9C82C4"
HOME_BLACK = "#19151F"
GOLD = "#C9A76B"
RISK_BAIXO = "#2F6F62"
RISK_MEDIO = "#B8863B"
RISK_ALTO = "#A13D2E"


# ---------------------------------------------------------------------------
# CSS global
# ---------------------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@800;900&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');

:root{
  --paper:#EEE3CE;
  --paper-alt:#F3EADA;
  --paper-strong:#DFC89A;
  --ink:#2A2035;
  --ink-soft:#6C4E97;
  --line:#C9B6DE;
  --accent:#6C4E97;
  --purple-deep:#3E2A63;
  --purple-soft:#9C82C4;
  --home-black:#19151F;
  --gold:#C9A76B;
  --risk-baixo:#2F6F62;
  --risk-medio:#B8863B;
  --risk-alto:#A13D2E;
}

.stApp, body, [data-testid="stAppViewContainer"]{
  background:var(--paper) !important;
  font-family:'IBM Plex Sans', sans-serif !important;
  color:var(--ink);
}
[data-testid="stHeader"]{ background:transparent !important; }
[data-testid="stToolbar"]{ right:12px; }
.block-container{ max-width:940px; padding-top:2rem; padding-bottom:5rem; }
[data-testid="stAppViewContainer"] > .main{ position:relative; z-index:1; }

.sentinela-bg{
  position:fixed; inset:0; z-index:0; pointer-events:none; overflow:hidden;
}
.sentinela-blob{ position:absolute; border-radius:50%; filter:blur(1px); }
.sentinela-robot{ position:absolute; }

.sentinela-card{
  background:var(--paper-alt);
  border:4px solid var(--purple-deep);
  border-radius:18px;
  padding:44px 38px;
  box-shadow:14px 14px 0 var(--accent);
  text-align:center;
  position:relative;
  margin-bottom:26px;
}
.sentinela-eyebrow{
  font-family:'IBM Plex Mono', monospace;
  font-weight:700; font-size:12px; letter-spacing:.2em;
  text-transform:uppercase; color:var(--accent);
}
.sentinela-title{
  font-family:'Montserrat', sans-serif;
  font-weight:900; font-size:60px; margin:16px 0 0;
  letter-spacing:.03em; line-height:1.1; text-transform:uppercase;
  color:var(--gold);
  text-shadow:4px 4px 0 var(--purple-soft), 8px 8px 0 var(--home-black);
}
.sentinela-title-sm{ font-size:34px; text-shadow:2px 2px 0 var(--purple-soft), 4px 4px 0 var(--home-black); }
.sentinela-sub{
  font-family:'IBM Plex Mono', monospace; font-weight:600; font-size:15px;
  color:var(--accent); margin-top:10px; letter-spacing:.04em; text-transform:uppercase;
}
.sentinela-desc{
  font-family:'IBM Plex Mono', monospace; margin:22px auto 0; max-width:440px;
  line-height:1.65; font-size:13px; color:var(--accent);
}
.sentinela-stamp{
  display:inline-block; margin:26px auto 0;
  border:3px double var(--accent); color:var(--accent);
  font-family:'IBM Plex Mono', monospace; font-weight:600; font-size:11px;
  letter-spacing:.14em; padding:6px 16px; border-radius:6px;
  transform:rotate(-4deg); text-transform:uppercase; background:var(--paper);
}
.sentinela-note{
  margin-top:14px; font-family:'IBM Plex Mono', monospace; font-size:11px; color:var(--accent);
}

.sentinela-panel-head{
  background:var(--paper-alt);
  border:3px solid var(--purple-deep);
  border-radius:14px 14px 0 0;
  border-bottom:none;
  padding:14px 20px 10px;
  margin:26px 0 0;
  box-shadow:6px 0 0 var(--accent);
}
.sentinela-block-num{
  font-family:'IBM Plex Mono', monospace; font-size:11px; letter-spacing:.1em;
  color:var(--ink-soft); text-transform:uppercase;
}
.sentinela-panel-head h2{
  font-family:'IBM Plex Sans', sans-serif !important; font-weight:700 !important;
  font-size:19px !important; margin:4px 0 0 !important; text-transform:uppercase;
  color:var(--accent) !important; border:none !important; padding:0 !important;
}
.sentinela-subhead{
  font-family:'Source Serif 4', serif; font-size:15px; font-weight:700;
  color:var(--purple-deep); margin:22px 0 8px; padding-bottom:4px;
  border-bottom:2px dotted var(--purple-soft);
}
.sentinela-subhead::before{ content:'\\2726  '; color:var(--accent); }

h1, [data-testid="stMarkdownContainer"] h1{
  font-family:'Montserrat', sans-serif !important; font-weight:900 !important;
  text-transform:uppercase; letter-spacing:.03em; color:var(--gold) !important;
  text-shadow:3px 3px 0 var(--purple-soft), 6px 6px 0 var(--home-black);
}
h2, h3, [data-testid="stMarkdownContainer"] h2, [data-testid="stMarkdownContainer"] h3{
  font-family:'Source Serif 4', serif !important;
  color:var(--purple-deep) !important;
}

[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label{
  font-family:'IBM Plex Mono', monospace !important;
  font-size:11px !important; letter-spacing:.06em !important;
  text-transform:uppercase; color:var(--ink-soft) !important; font-weight:500 !important;
}

[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input{
  border:1px solid var(--line) !important;
  background:var(--paper) !important;
  color:var(--ink) !important;
  border-radius:2px !important;
  font-family:'IBM Plex Sans', sans-serif !important;
  font-size:14px !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus{
  outline:2px solid var(--accent) !important; outline-offset:1px;
  box-shadow:none !important; border-color:var(--accent) !important;
}
[data-baseweb="select"] > div{
  border:1.5px solid var(--purple-deep) !important;
  background:var(--paper) !important;
  border-radius:2px !important;
  font-family:'IBM Plex Sans', sans-serif !important;
  color:var(--accent) !important; font-weight:600 !important;
}
[data-baseweb="popover"] li{ font-family:'IBM Plex Sans', sans-serif !important; }
[data-baseweb="tag"]{
  background:var(--accent) !important; border-radius:20px !important;
  font-family:'IBM Plex Sans', sans-serif !important;
}

div.stButton > button, div.stFormSubmitButton > button, div.stDownloadButton > button{
  font-family:'IBM Plex Mono', monospace !important;
  font-size:13px !important; letter-spacing:.05em !important;
  text-transform:uppercase; font-weight:700 !important;
  background:var(--purple-deep) !important; color:var(--paper-alt) !important;
  border:none !important; border-radius:8px !important;
  box-shadow:4px 4px 0 var(--purple-soft) !important;
  padding:12px 20px !important; transition:background .15s ease;
}
div.stButton > button:hover, div.stFormSubmitButton > button:hover,
div.stDownloadButton > button:hover{
  background:var(--accent) !important; color:#FFFFFF !important;
}
div.stButton > button:active, div.stFormSubmitButton > button:active{
  transform:translate(2px, 2px); box-shadow:2px 2px 0 var(--purple-soft) !important;
}
div.stButton > button[kind="secondary"]{
  background:transparent !important; color:var(--purple-deep) !important;
  border:2px solid var(--purple-deep) !important;
}
div.stButton > button[kind="secondary"]:hover{
  background:var(--purple-deep) !important; color:var(--paper-alt) !important;
}

[data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stVerticalBlock"]){
  background:var(--paper-alt);
  border:3px solid var(--purple-deep) !important;
  border-radius:14px !important;
  box-shadow:6px 6px 0 var(--accent);
  padding:14px 18px !important;
  margin-bottom:16px;
}

[data-testid="stExpander"]{
  border:1.5px dashed var(--purple-soft) !important;
  border-radius:10px !important;
  background:rgba(255,255,255,.25) !important;
}
[data-testid="stExpander"] summary{
  font-family:'IBM Plex Sans', sans-serif !important;
  font-weight:600 !important; color:var(--purple-deep) !important;
}

[data-testid="stMetricValue"]{
  color:var(--risk-baixo) !important;
  font-family:'Montserrat', sans-serif !important; font-weight:900 !important;
}
[data-testid="stMetricLabel"] p{
  font-family:'IBM Plex Mono', monospace !important; text-transform:uppercase;
}

[data-testid="stCheckbox"] label span{ font-family:'IBM Plex Sans', sans-serif !important; }

hr{ border-color:var(--line) !important; }
[data-testid="stCaptionContainer"] p{
  font-family:'IBM Plex Mono', monospace !important; font-size:11.5px !important;
  color:var(--ink-soft) !important;
}
</style>
"""


# ---------------------------------------------------------------------------
# Arte de fundo (robôs e blobs), igual à .bg-art do artefato
# ---------------------------------------------------------------------------
_ROBO_SYMBOL = """
<svg width="0" height="0" style="position:absolute;">
  <symbol id="roboSentinela" viewBox="-6 -12 112 176">
    <line x1="50" y1="4" x2="50" y2="16" stroke="var(--robot-stroke)" stroke-width="5" stroke-linecap="round"/>
    <circle cx="50" cy="-2" r="7" fill="var(--robot-accent)" stroke="var(--robot-stroke)" stroke-width="4"/>
    <rect x="22" y="128" width="20" height="26" rx="9" fill="var(--robot-fill)" stroke="var(--robot-stroke)" stroke-width="5"/>
    <rect x="58" y="128" width="20" height="26" rx="9" fill="var(--robot-fill)" stroke="var(--robot-stroke)" stroke-width="5"/>
    <rect x="-2" y="78" width="20" height="44" rx="9" fill="var(--robot-fill)" stroke="var(--robot-stroke)" stroke-width="5"/>
    <rect x="82" y="78" width="20" height="44" rx="9" fill="var(--robot-fill)" stroke="var(--robot-stroke)" stroke-width="5"/>
    <circle cx="8" cy="126" r="9" fill="var(--robot-accent)" stroke="var(--robot-stroke)" stroke-width="4"/>
    <circle cx="92" cy="126" r="9" fill="var(--robot-accent)" stroke="var(--robot-stroke)" stroke-width="4"/>
    <rect x="14" y="70" width="72" height="60" rx="22" fill="var(--robot-fill)" stroke="var(--robot-stroke)" stroke-width="5"/>
    <circle cx="50" cy="102" r="13" fill="var(--robot-accent)" stroke="var(--robot-stroke)" stroke-width="4"/>
    <circle cx="50" cy="102" r="5" fill="var(--robot-stroke)"/>
    <rect x="16" y="16" width="68" height="56" rx="26" fill="var(--robot-fill)" stroke="var(--robot-stroke)" stroke-width="5"/>
    <circle cx="37" cy="42" r="12" fill="var(--robot-accent)" stroke="var(--robot-stroke)" stroke-width="4"/>
    <circle cx="63" cy="42" r="12" fill="var(--robot-accent)" stroke="var(--robot-stroke)" stroke-width="4"/>
    <circle cx="39" cy="43" r="4.5" fill="var(--robot-stroke)"/>
    <circle cx="65" cy="43" r="4.5" fill="var(--robot-stroke)"/>
    <path d="M36 58 Q50 68 64 58" fill="none" stroke="var(--robot-stroke)" stroke-width="4.5" stroke-linecap="round"/>
  </symbol>
</svg>
"""

FUNDO_ART = _ROBO_SYMBOL + """
<div class="sentinela-bg" aria-hidden="true">
  <div class="sentinela-blob" style="width:220px;height:220px;top:-60px;left:-70px;background:#9C82C4;opacity:.35;"></div>
  <div class="sentinela-blob" style="width:160px;height:160px;bottom:-50px;right:-40px;background:#6C4E97;opacity:.25;"></div>
  <div class="sentinela-blob" style="width:90px;height:90px;top:40%;right:6%;background:#19151F;opacity:.12;"></div>
  <svg class="sentinela-robot" style="top:6%;left:3%;width:60px;height:94px;opacity:.85;transform:rotate(-8deg);--robot-fill:#6C4E97;--robot-stroke:#3E2A63;--robot-accent:#F3EADA;"><use href="#roboSentinela"/></svg>
  <svg class="sentinela-robot" style="top:1%;left:13%;width:92px;height:144px;opacity:.75;transform:rotate(-6deg);--robot-fill:#F3EADA;--robot-stroke:#3E2A63;--robot-accent:#6C4E97;"><use href="#roboSentinela"/></svg>
  <svg class="sentinela-robot" style="top:10%;right:5%;width:170px;height:266px;opacity:.75;transform:rotate(9deg);--robot-fill:#F3EADA;--robot-stroke:#3E2A63;--robot-accent:#6C4E97;"><use href="#roboSentinela"/></svg>
  <svg class="sentinela-robot" style="bottom:6%;left:5%;width:190px;height:298px;opacity:.8;transform:rotate(6deg);--robot-fill:#9C82C4;--robot-stroke:#3E2A63;--robot-accent:#F3EADA;"><use href="#roboSentinela"/></svg>
  <svg class="sentinela-robot" style="bottom:4%;right:4%;width:76px;height:119px;opacity:.85;transform:rotate(-12deg);--robot-fill:#9C82C4;--robot-stroke:#3E2A63;--robot-accent:#F3EADA;"><use href="#roboSentinela"/></svg>
  <svg class="sentinela-robot" style="top:38%;left:1%;width:42px;height:66px;opacity:.8;transform:rotate(14deg);--robot-fill:#6C4E97;--robot-stroke:#3E2A63;--robot-accent:#F3EADA;"><use href="#roboSentinela"/></svg>
</div>
"""


# ---------------------------------------------------------------------------
# Helpers de renderização
# ---------------------------------------------------------------------------

def aplicar_estilo(com_fundo: bool = True) -> None:
    """Injeta o CSS global e (opcionalmente) a arte de fundo.

    Usa st.html(), que NÃO passa pelo parser de markdown -- ver explicação no
    topo deste módulo.
    """
    st.html(CSS)
    if com_fundo:
        st.html(FUNDO_ART)


def cartao_home(eyebrow: str, titulo: str, descricao: str = "", sub: str = "",
                 carimbo: str = "", titulo_pequeno: bool = False) -> None:
    """Cartão central do artefato (home, escolha de tipo, etc)."""
    classe_titulo = "sentinela-title sentinela-title-sm" if titulo_pequeno else "sentinela-title"
    partes = [
        '<div class="sentinela-card">',
        f'<div class="sentinela-eyebrow">{eyebrow}</div>',
        f'<div class="{classe_titulo}">{titulo}</div>',
    ]
    if sub:
        partes.append(f'<div class="sentinela-sub">{sub}</div>')
    if descricao:
        partes.append(f'<div class="sentinela-desc">{descricao}</div>')
    if carimbo:
        partes.append(f'<div class="sentinela-stamp">{carimbo}</div>')
    partes.append("</div>")
    st.html("".join(partes))


def cabecalho_bloco(numero: str, titulo: str) -> None:
    """Cabeçalho numerado dos blocos do formulário (Bloco 1, Bloco 2...)."""
    st.html(
        '<div class="sentinela-panel-head">'
        f'<div class="sentinela-block-num">{numero}</div>'
        f'<h2>{titulo}</h2>'
        '</div>'
    )


def subtitulo(texto: str) -> None:
    """Subtítulo interno de seção, com o marcador ✦ do artefato."""
    st.html(f'<div class="sentinela-subhead">{texto}</div>')


def nota(texto: str) -> None:
    st.html(f'<div class="sentinela-note">{texto}</div>')
