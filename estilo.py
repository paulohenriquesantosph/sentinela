# -*- coding: utf-8 -*-
"""
Sentinela PLD - Camada visual (Databricks / Streamlit)
=======================================================

Concentra TODO o visual do app, replicando o artefato original (capturas do
manual): paleta bege/roxo, fontes (Montserrat, Source Serif 4, IBM Plex
Sans/Mono), cartões de borda grossa com sombra deslocada, carimbo rotacionado,
botões "de papel" com sombra, selects roxos, abas sublinhadas e a arte de
robôs ao fundo.

Três decisões técnicas que importam:

1. st.html() em vez de st.markdown(): o markdown interpreta asteriscos de
   comentários CSS e quebra o bloco. Mas o st.html() passa o HTML por um
   sanitizador que REMOVE <svg>. Por isso a arte (robôs, cabo com raio,
   marca d'água) é desenhada como imagens SVG em data-URI dentro do CSS
   (background-image), que o sanitizador não toca.

2. Cartões: o Streamlit envolve TODO bloco vertical em um
   "stVerticalBlockBorderWrapper". Estilizar esse seletor a seco aninha
   bordas em tudo (colunas, botões...). Os cartões são marcados com um
   <span class="sx-card"> e o CSS usa :has() para estilizar só esses.

3. Telas "de cartão" (home, tipo, modo, instruções, banco): a própria área
   principal da página vira o cartão (ver css_tela()).
"""

from __future__ import annotations

from contextlib import contextmanager
from html import escape
from typing import Iterator, List, Optional, Tuple
from urllib.parse import quote

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
# Arte de fundo em SVG (data-URI)
# ---------------------------------------------------------------------------

def _uri(svg: str) -> str:
    return 'url("data:image/svg+xml;utf8,' + quote(svg, safe="") + '")'


def _robo(fill: str, stroke: str, accent: str, rot: float, pupila: str = "#2A1B45") -> str:
    """Robô do Sentinela como imagem SVG, já girado (o fundo CSS não gira)."""
    corpo = f"""
    <line x1="50" y1="4" x2="50" y2="16" stroke="{stroke}" stroke-width="5" stroke-linecap="round"/>
    <circle cx="50" cy="-2" r="7" fill="{accent}" stroke="{stroke}" stroke-width="4"/>
    <rect x="22" y="128" width="20" height="26" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="5"/>
    <rect x="58" y="128" width="20" height="26" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="5"/>
    <rect x="-2" y="78" width="20" height="44" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="5"/>
    <rect x="82" y="78" width="20" height="44" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="5"/>
    <circle cx="8" cy="126" r="9" fill="{accent}" stroke="{stroke}" stroke-width="4"/>
    <circle cx="92" cy="126" r="9" fill="{accent}" stroke="{stroke}" stroke-width="4"/>
    <rect x="14" y="70" width="72" height="60" rx="22" fill="{fill}" stroke="{stroke}" stroke-width="5"/>
    <circle cx="50" cy="102" r="13" fill="{accent}" stroke="{stroke}" stroke-width="4"/>
    <circle cx="50" cy="102" r="5" fill="{pupila}"/>
    <rect x="16" y="16" width="68" height="56" rx="26" fill="{fill}" stroke="{stroke}" stroke-width="5"/>
    <circle cx="37" cy="42" r="12" fill="{accent}" stroke="{stroke}" stroke-width="4"/>
    <circle cx="63" cy="42" r="12" fill="{accent}" stroke="{stroke}" stroke-width="4"/>
    <circle cx="39" cy="43" r="4.5" fill="{pupila}"/>
    <circle cx="65" cy="43" r="4.5" fill="{pupila}"/>
    <path d="M36 58 Q50 68 64 58" fill="none" stroke="{stroke}" stroke-width="4.5" stroke-linecap="round"/>
    """
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-30 -34 160 244" '
            f'preserveAspectRatio="xMidYMid meet"><g transform="rotate({rot} 50 88)">{corpo}</g></svg>')


def _blob(cor: str, opacidade: float) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            f'<circle cx="50" cy="50" r="50" fill="{cor}" fill-opacity="{opacidade}"/></svg>')


# (svg, tamanho CSS, posição CSS) — medidos nas capturas do manual (viewport 1280x860).
# O tamanho do <svg> inclui a folga da viewBox (160x244 para um robô de ~100x176).
def _camadas_fundo() -> Tuple[List[str], List[str], List[str]]:
    def robo(fill, stroke, accent, rot, w, pos):
        h = round(w * 244 / 160)
        return (_robo(fill, stroke, accent, rot), f"{w}px {h}px", pos)

    camadas = [
        # blobs (primeiro = mais ao fundo)
        (_blob("#9C82C4", .35), "220px 220px", "-70px -60px"),
        (_blob("#6C4E97", .25), "160px 160px", "calc(100% + 40px) calc(100% + 50px)"),
        (_blob("#19151F", .12), "90px 90px", "calc(100% - 77px) 40%"),
        # robôs (tamanho e posição medidos nas capturas do manual, viewport 1280x860)
        robo("#6C4E97", "#3E2A63", "#F3EADA", -8, 84, "2.9% 4.9%"),
        robo("#F3EADA", "#6C4E97", "#6C4E97", -6, 128, "14.4% -1.2%"),
        robo("#F3EADA", "#6C4E97", "#6C4E97", 9, 245, "calc(100% - 64px) 6%"),
        robo("#AE98CC", "#6C4E97", "#F3EADA", 6, 268, "57px calc(100% + 22px)"),
        robo("#9C82C4", "#6C4E97", "#F3EADA", -12, 110, "calc(100% - 48px) 100%"),
        robo("#6C4E97", "#3E2A63", "#F3EADA", 14, 62, "0.9% 37%"),
    ]
    return ([c[0] for c in camadas], [c[1] for c in camadas], [c[2] for c in camadas])


def _css_fundo() -> str:
    svgs, tamanhos, posicoes = _camadas_fundo()
    return (
        ".stApp::before{content:'';position:fixed;inset:0;z-index:0;pointer-events:none;"
        f"background-image:{','.join(_uri(s) for s in svgs)};"
        f"background-size:{','.join(tamanhos)};"
        f"background-position:{','.join(posicoes)};"
        "background-repeat:no-repeat;}"
    )


# Cabo com raio e cabeça do robô pendurado no topo do cartão da home.
_ROBO_PENDURADO = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 130 250">
  <g fill="none" stroke="#6C4E97" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round">
    <path d="M48 0 L74 0 L69 44 L83 44 L66 140 L70 74 L56 74 Z"/>
    <path d="M60 0 L82 0 L76 50 L91 50 L68 150 L73 82 L62 82 Z" stroke-opacity=".85"/>
    <path d="M40 0 L57 0 L63 62 L50 62 L58 130 L47 62" stroke-opacity=".55"/>
  </g>
  <line x1="65" y1="140" x2="65" y2="152" stroke="#2A1B45" stroke-width="5" stroke-linecap="round"/>
  <circle cx="65" cy="140" r="7" fill="#6C4E97" stroke="#2A1B45" stroke-width="4"/>
  <rect x="26" y="152" width="78" height="60" rx="24" fill="#4A2F6E" stroke="#2A1B45" stroke-width="5"/>
  <circle cx="47" cy="178" r="11" fill="#F3EADA" stroke="#2A1B45" stroke-width="3.5"/>
  <circle cx="83" cy="178" r="11" fill="#F3EADA" stroke="#2A1B45" stroke-width="3.5"/>
  <circle cx="49" cy="179" r="4.2" fill="#2A1B45"/>
  <circle cx="85" cy="179" r="4.2" fill="#2A1B45"/>
  <path d="M50 197 Q65 206 80 197" fill="none" stroke="#2A1B45" stroke-width="4.5" stroke-linecap="round"/>
  <circle cx="14" cy="214" r="10" fill="#6C4E97" stroke="#2A1B45" stroke-width="4"/>
  <circle cx="116" cy="214" r="10" fill="#6C4E97" stroke="#2A1B45" stroke-width="4"/>
</svg>
"""

# Marca d'água do cartão da home: documento + lupa.
_MARCA_DAGUA = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 300">
  <g fill="none" stroke="#E8DDCA" stroke-width="12" stroke-linecap="round" stroke-linejoin="round">
    <rect x="46" y="22" width="140" height="190" rx="14"/>
    <line x1="80" y1="70" x2="152" y2="70"/>
    <line x1="80" y1="108" x2="120" y2="108"/>
    <circle cx="168" cy="172" r="56"/>
    <line x1="208" y1="214" x2="244" y2="252"/>
  </g>
</svg>
"""


# ---------------------------------------------------------------------------
# CSS global
# ---------------------------------------------------------------------------
_FONTES = ("@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@800;900"
           "&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700"
           "&family=IBM+Plex+Sans:wght@400;500;600;700"
           "&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');")

CSS_BASE = """
:root{
  --paper:#EEE3CE; --paper-alt:#F3EADA; --paper-strong:#DFC89A;
  --ink:#2A2035; --ink-soft:#6C4E97; --line:#C9B6DE; --accent:#6C4E97;
  --purple-deep:#3E2A63; --purple-soft:#9C82C4; --home-black:#19151F; --gold:#C9A76B;
  --risk-baixo:#2F6F62; --risk-medio:#B8863B; --risk-alto:#A13D2E;
  --mono:'IBM Plex Mono', ui-monospace, Menlo, monospace;
  --sans:'IBM Plex Sans', system-ui, sans-serif;
  --serif:'Source Serif 4', Georgia, serif;
  --display:'Montserrat', system-ui, sans-serif;
}

html, body, .stApp{ background:var(--paper) !important; }
.stApp, [data-testid="stAppViewContainer"], .stApp *{ font-family:var(--sans); }
.stApp{ color:var(--ink); }
[data-testid="stAppViewContainer"], [data-testid="stMain"], section.main{ background:transparent !important; }
[data-testid="stHeader"], [data-testid="stDecoration"], [data-testid="stToolbar"],
[data-testid="stStatusWidget"], footer, #MainMenu{ display:none !important; }
.block-container, [data-testid="stAppViewBlockContainer"]{
  position:relative; z-index:1; margin-left:auto !important; margin-right:auto !important;
  padding:2.2rem 1.4rem 5rem !important; box-sizing:border-box;
}
/* elementos-marcador (só servem de âncora para o CSS) não ocupam espaço */
[data-testid="element-container"]:has(> .stHtml > .sx-mark){ display:none !important; }
[data-testid="stVerticalBlock"]{ gap:.8rem; }

h1,h2,h3,h4{ font-family:var(--serif) !important; color:var(--purple-deep) !important; }

/* ---- rótulos dos campos ---- */
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label{
  font-family:var(--mono) !important; font-size:10.5px !important; letter-spacing:.08em !important;
  text-transform:uppercase; color:var(--ink-soft) !important; font-weight:500 !important;
}
[data-testid="stCheckbox"] [data-testid="stWidgetLabel"] p{
  font-family:var(--sans) !important; font-size:14px !important; letter-spacing:0 !important;
  text-transform:none !important; color:var(--ink) !important; font-weight:600 !important;
}

/* ---- campos de texto ---- */
[data-baseweb="input"], [data-baseweb="textarea"]{
  background:var(--paper) !important; border:1px solid var(--line) !important;
  border-radius:4px !important; box-shadow:none !important;
}
[data-baseweb="input"] > div, [data-baseweb="base-input"]{ background:transparent !important; border:none !important; }
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea{
  background:transparent !important; color:var(--ink) !important;
  font-family:var(--sans) !important; font-size:14px !important;
  -webkit-text-fill-color:var(--ink);
}
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within{
  outline:2px solid var(--accent) !important; outline-offset:1px; border-color:var(--accent) !important;
}
[data-baseweb="input"] input::placeholder, [data-baseweb="textarea"] textarea::placeholder{
  color:#8D7FA3 !important; -webkit-text-fill-color:#8D7FA3; opacity:1;
}
[data-baseweb="input"]:has(input:disabled), [data-baseweb="textarea"]:has(textarea:disabled){
  background:#E5DED1 !important; border-color:#CFC4B4 !important;
}
[data-baseweb="input"] input:disabled, [data-baseweb="textarea"] textarea:disabled{
  -webkit-text-fill-color:#4A4350 !important; color:#4A4350 !important; opacity:1 !important;
}
.sx-mono-area textarea{ font-family:var(--mono) !important; font-size:13px !important; }

/* ---- selects: sólidos, roxos, texto branco ---- */
[data-baseweb="select"] > div{
  background:var(--accent) !important; border:1.5px solid var(--purple-deep) !important;
  border-radius:4px !important; color:#fff !important; min-height:38px;
}
[data-baseweb="select"] *{ color:#fff !important; font-family:var(--sans) !important; font-weight:700 !important; font-size:14px !important; }
[data-baseweb="select"] svg{ fill:#fff !important; }
[data-baseweb="select"] input{ -webkit-text-fill-color:#fff !important; }
[data-baseweb="select"]:has(input:disabled) > div{ background:#9B8DA6 !important; border-color:#8C7F98 !important; }
[data-baseweb="popover"] [role="listbox"], [data-baseweb="popover"] ul{ background:var(--paper-alt) !important; }
[data-baseweb="popover"] li, [data-baseweb="popover"] li *{
  font-family:var(--sans) !important; color:var(--ink) !important; font-weight:500 !important;
}
[data-baseweb="popover"] li:hover, [data-baseweb="popover"] li[aria-selected="true"]{ background:#E2D6EE !important; }
[data-baseweb="tag"]{ background:var(--accent) !important; border-radius:20px !important; }

/* ---- botões ---- */
[data-testid^="stBaseButton"], .stButton > button, .stDownloadButton > button{
  font-family:var(--mono) !important; font-size:13px !important; letter-spacing:.06em !important;
  text-transform:uppercase; font-weight:600 !important; line-height:1.25 !important;
  background:var(--purple-deep) !important; color:var(--paper-alt) !important;
  border:2px solid var(--purple-deep) !important; border-radius:8px !important;
  box-shadow:4px 4px 0 var(--purple-soft) !important;
  padding:12px 22px !important; min-height:0 !important;
  transition:transform .12s ease, box-shadow .12s ease, background .12s ease, color .12s ease;
}
[data-testid^="stBaseButton"] p, .stButton button p, .stDownloadButton button p{
  font-family:var(--mono) !important; font-size:13px !important; letter-spacing:.06em !important;
  text-transform:uppercase; font-weight:600 !important; color:inherit !important; margin:0;
}
[data-testid^="stBaseButton"]:hover:not(:disabled){
  background:var(--accent) !important; color:#fff !important; border-color:var(--accent) !important;
  transform:translate(-1px,-1px); box-shadow:5px 5px 0 var(--purple-soft) !important;
}
[data-testid^="stBaseButton"]:active:not(:disabled){
  transform:translate(3px,3px); box-shadow:1px 1px 0 var(--purple-soft) !important;
}
[data-testid^="stBaseButton"]:focus-visible{ outline:3px solid var(--purple-soft) !important; outline-offset:2px; }
[data-testid^="stBaseButton"]:disabled{
  background:#9B8DA6 !important; color:#EFE7DD !important; border-color:#9B8DA6 !important;
  box-shadow:none !important; cursor:not-allowed; opacity:1 !important;
}
/* secundário: contorno */
.stApp button[data-testid="stBaseButton-secondary"], .stApp button[data-testid="stBaseButton-secondaryFormSubmit"]{
  background:var(--paper-alt) !important; color:var(--purple-deep) !important;
  border:2px solid var(--purple-deep) !important;
}
.stApp button[data-testid="stBaseButton-secondary"]:hover:not(:disabled), .stApp button[data-testid="stBaseButton-secondaryFormSubmit"]:hover:not(:disabled){
  background:var(--purple-deep) !important; color:var(--paper-alt) !important; border-color:var(--purple-deep) !important;
}
.stApp button[data-testid="stBaseButton-secondary"]:disabled{ background:#D9D0C2 !important; color:#8F8499 !important; border-color:#B9AEC4 !important; }
.stApp button[data-testid="stBaseButton-secondary"] p{ color:inherit !important; }
/* download = botão escuro */
.stApp .stDownloadButton button{ background:var(--purple-deep) !important; color:var(--paper-alt) !important; border:2px solid var(--purple-deep) !important; }
.stApp .stDownloadButton button:hover{ background:var(--accent) !important; color:#fff !important; }

/* botão pequeno (SALVAR das seções): o container que contém o marcador .sx-sm */
[data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-sm) [data-testid^="stBaseButton"]{
  font-size:11px !important; padding:8px 18px !important; border-radius:6px !important;
  box-shadow:3px 3px 0 var(--purple-soft) !important;
}
[data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-sm) [data-testid^="stBaseButton"] p{ font-size:11px !important; }
[data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-sm) [data-testid^="stBaseButton"]:disabled{ box-shadow:none !important; }

/* link discreto ("← Voltar"): o container que contém o marcador .sx-lnk */
[data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-lnk) [data-testid^="stBaseButton"], [data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-lnk) [data-testid="stLinkButton"] a{
  background:transparent !important; border:none !important; box-shadow:none !important;
  color:var(--accent) !important; text-decoration:underline; text-underline-offset:3px;
  padding:2px 6px !important; transform:none !important;
}
[data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-lnk) [data-testid^="stBaseButton"] p, [data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-lnk) [data-testid="stLinkButton"] a p{
  font-size:12px !important; text-transform:none !important; font-weight:500 !important; letter-spacing:.02em !important;
}
[data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-lnk) [data-testid^="stBaseButton"]:hover:not(:disabled), [data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-lnk) [data-testid="stLinkButton"] a:hover{
  background:transparent !important; color:var(--purple-deep) !important; box-shadow:none !important;
}
[data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-lnk) .stButton, [data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-lnk) [data-testid="stLinkButton"]{ display:flex; justify-content:center; }

/* botão compacto escuro "← Voltar ao Sentinela" do dossiê */
[data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-topo) [data-testid^="stBaseButton"]{
  font-size:11.5px !important; padding:9px 16px !important; border-radius:6px !important; box-shadow:3px 3px 0 var(--purple-soft) !important;
}

/* botão de largura total, com texto em negrito (telas de escolha) */
[data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-opcoes) [data-testid^="stBaseButton"]{
  width:100%; padding:13px 20px !important; border-radius:12px !important; font-weight:700 !important;
}
[data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-opcoes) [data-testid^="stBaseButton"] p{ font-weight:700 !important; font-size:14px !important; }

/* botão largo de contorno (Banco: "Consultar banco de dados completo") */
[data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-larga) [data-testid^="stBaseButton"]{
  width:100%; border-radius:3px !important; padding:11px 16px !important; box-shadow:3px 3px 0 var(--purple-soft) !important;
}

/* linhas de resultado do Banco: botão alinhado à esquerda, contorno */
[data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-linhas) [data-testid^="stBaseButton"]{
  width:100%; justify-content:flex-start; text-align:left; padding:13px 18px !important; border-radius:12px !important;
  text-transform:none !important; box-shadow:3px 3px 0 var(--purple-soft) !important;
}
[data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] > .stHtml > .sx-linhas) [data-testid^="stBaseButton"] p{
  text-transform:none !important; font-family:var(--sans) !important; font-size:14.5px !important; font-weight:500 !important; letter-spacing:0 !important; text-align:left;
}

/* ---- cartões (containers marcados) ---- */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"] > [data-testid="element-container"] > .stHtml > .sx-card){
  background:var(--paper-alt); border:3px solid var(--purple-deep) !important; border-radius:16px !important;
  box-shadow:6px 6px 0 var(--accent); padding:14px 22px 20px !important; margin-bottom:22px;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"] > [data-testid="element-container"] > .stHtml > .sx-sub){
  background:rgba(255,255,255,.12); border:1px solid var(--line) !important; border-radius:6px !important; padding:12px 14px !important; margin-bottom:6px;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"] > [data-testid="element-container"] > .stHtml > .sx-box){
  background:rgba(255,255,255,.14); border:1.5px solid var(--line) !important; border-radius:10px !important; padding:14px 16px !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"] > [data-testid="element-container"] > .stHtml > .sx-box.ok){
  border:2px solid var(--risk-baixo) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"] > [data-testid="element-container"] > .stHtml > .sx-box.dash){
  border:2px dashed var(--risk-medio) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"] > [data-testid="element-container"] > .stHtml > .sx-box.nota){
  background:rgba(255,255,255,.14); border:1.5px solid var(--line) !important;
}

/* ---- cabeçalhos ---- */
.sx-bloco-num{ font-family:var(--mono); font-size:10.5px; letter-spacing:.12em; color:var(--ink-soft); text-transform:uppercase; }
.sx-bloco-titulo{
  font-family:var(--sans); font-weight:700; font-size:19px; margin:2px 0 0; text-transform:uppercase;
  color:var(--accent); padding-bottom:9px; border-bottom:1px solid var(--line);
}
.sx-sec-titulo{
  font-family:var(--serif); font-weight:700; font-size:20px; color:var(--ink);
  margin:0; padding:2px 0 10px; border-bottom:1px solid var(--line);
}
.sx-subhead{
  font-family:var(--serif); font-size:15px; font-weight:700; color:var(--purple-deep);
  margin:14px 0 8px; padding-bottom:4px; border-bottom:2px dotted var(--purple-soft);
}
.sx-subhead::before{ content:'\\2726  '; color:var(--accent); }
.sx-nota{ font-family:var(--mono); font-size:11px; color:var(--accent); line-height:1.5; }
.sx-hint{ font-family:var(--mono); font-size:12.5px; color:var(--accent); text-align:center; line-height:1.65; margin:6px 0 2px; }
.sx-ok{ font-family:var(--mono); font-size:12px; color:var(--risk-baixo); margin:2px 0; }
.sx-erro{ font-family:var(--mono); font-size:12px; color:var(--risk-alto); margin:2px 0; }
.sx-rotulo{ font-family:var(--mono); font-size:10px; letter-spacing:.1em; text-transform:uppercase; font-weight:600; margin:0 0 6px; }
.sx-rotulo.pend{ color:var(--risk-medio); } .sx-rotulo.ok{ color:var(--risk-baixo); }
.sx-salvo{ font-family:var(--mono); font-size:11.5px; color:var(--accent); margin:2px 0 0; }
.sx-vazio{ text-align:center; font-family:var(--sans); font-size:16px; line-height:1.45; color:var(--purple-deep); padding:6px 4px; }
.sx-sep{ text-align:center; font-family:var(--mono); font-size:10.5px; letter-spacing:.1em; color:var(--accent); text-transform:uppercase; margin:2px 0; }

/* ---- pílulas do dossiê ---- */
.sx-pills{ display:flex; flex-wrap:wrap; gap:8px 10px; margin:0 0 10px; }
.sx-pill{
  display:inline-flex; flex-direction:column; border:1.5px solid var(--purple-soft); border-radius:14px;
  padding:6px 14px 7px; background:var(--paper); max-width:100%;
}
.sx-pill-l{ font-family:var(--mono); font-size:9.5px; letter-spacing:.07em; color:var(--ink-soft); text-transform:uppercase; }
.sx-pill-v{ font-family:var(--sans); font-weight:700; font-size:14px; color:var(--ink); overflow-wrap:anywhere; }
.sx-pill.gde .sx-pill-v{ font-family:var(--sans); font-size:26px; font-weight:700; }
.sx-pill.verde .sx-pill-v{ color:var(--risk-baixo); } .sx-pill.vermelho .sx-pill-v{ color:var(--risk-alto); }
.sx-pill.verde, .sx-pill.vermelho{ border-color:var(--line); }
.sx-texto{ font-family:var(--sans); font-size:15px; line-height:1.55; color:var(--ink); margin:2px 0 8px; white-space:pre-wrap; }
.sx-linha-sep{ border:none; border-top:1px dashed var(--purple-soft); margin:12px 0; opacity:.8; }
.sx-resto{ font-family:var(--sans); font-size:14px; color:var(--ink); margin:2px 0 10px; }
.sx-grafico img{ width:100%; height:auto; display:block; }
.sx-mudanca{ font-family:var(--sans); font-size:15px; line-height:1.6; color:var(--ink); }

/* ---- cabeçalho do dossiê ---- */
.sx-dossie-cab{ display:flex; flex-direction:column; gap:2px; }
.sx-dossie-num{ font-family:var(--mono); font-size:12px; color:var(--ink-soft); letter-spacing:.04em; }
.sx-dossie-nome{ font-family:var(--serif); font-weight:700; font-size:29px; color:var(--ink); display:flex; align-items:center; gap:10px; }
.sx-avatar{ width:22px; height:30px; flex:0 0 auto; }

/* ---- selo (carimbo) ---- */
.sx-selo-wrap{ display:flex; justify-content:center; margin:2px 0 -6px; position:relative; z-index:2; }
.sx-selo{
  font-family:var(--mono); font-weight:700; font-size:12px; letter-spacing:.1em; text-transform:uppercase;
  padding:6px 16px; border-radius:6px; border:3px double currentColor; background:var(--paper-alt);
  transform:rotate(-3deg); color:var(--accent);
}
.sx-selo.verde{ color:var(--risk-baixo); } .sx-selo.ambar{ color:var(--risk-medio); }
.sx-selo.vermelho{ color:var(--risk-alto); } .sx-selo.neutro{ color:#6E6478; }

/* ---- nota ---- */
.sx-nota-rot{ font-family:var(--mono); font-size:10.5px; letter-spacing:.1em; color:var(--ink-soft); text-transform:uppercase; }
.sx-nota-val{ font-family:var(--display); font-weight:900; font-size:36px; line-height:1.15; }
.sx-nota-val.verde{ color:var(--risk-baixo); } .sx-nota-val.ambar{ color:var(--risk-medio); } .sx-nota-val.vermelho{ color:var(--risk-alto); }
.sx-drv-desc{ font-family:var(--sans); font-size:12.5px; line-height:1.4; color:var(--ink-soft);
  margin:-.55rem 0 0 28px; padding-bottom:9px; border-bottom:1px dashed var(--line); }

/* ---- abas ---- */
[data-baseweb="tab-list"]{ gap:0 !important; border-bottom:3px solid var(--purple-deep) !important; background:transparent !important; }
[data-baseweb="tab-border"]{ display:none !important; }
[data-baseweb="tab-highlight"]{ background:var(--purple-deep) !important; height:4px !important; }
button[data-baseweb="tab"]{
  background:transparent !important; padding:14px 22px !important; margin:0 !important;
}
button[data-baseweb="tab"] p{
  font-family:var(--mono) !important; font-size:12.5px !important; letter-spacing:.1em !important;
  text-transform:uppercase; color:var(--accent) !important; font-weight:500 !important;
}
button[data-baseweb="tab"][aria-selected="true"] p{ color:var(--purple-deep) !important; font-weight:700 !important; }
[data-baseweb="tab-panel"]{ padding-top:1.1rem !important; }

/* ---- diversos ---- */
[data-testid="stExpander"]{ border:1.5px dashed var(--purple-soft) !important; border-radius:10px !important; background:rgba(255,255,255,.25) !important; }
[data-testid="stExpander"] summary{ font-family:var(--sans) !important; font-weight:600 !important; color:var(--purple-deep) !important; }
[data-testid="stAlert"]{ border-radius:8px; font-family:var(--sans); }
[data-testid="stSpinner"] *{ font-family:var(--mono) !important; color:var(--accent) !important; }
hr{ border-color:var(--line) !important; }
[data-testid="stCaptionContainer"] p{ font-family:var(--mono) !important; font-size:11.5px !important; color:var(--ink-soft) !important; }
"""

# ---- cartão da home / telas "de cartão" -----------------------------------
CSS_CARTAO = """
.block-container, [data-testid="stAppViewBlockContainer"]{
  background:var(--paper-alt); border:4px solid var(--purple-deep); border-radius:18px;
  box-shadow:14px 14px 0 var(--accent); padding:40px 40px 44px !important;
  max-width:%(largura)spx !important; margin-top:%(topo)s !important; margin-bottom:60px !important;
  text-align:center;
}
.block-container > div, [data-testid="stAppViewBlockContainer"] > div{ position:relative; z-index:1; }
"""

CSS_HOME_EXTRA = """
.block-container::before, [data-testid="stAppViewBlockContainer"]::before{
  content:''; position:absolute; left:50%%; top:-205px; width:125px; height:240px; margin-left:-62px; z-index:3;
  background:%(cabo)s center/contain no-repeat; pointer-events:none;
}
.block-container::after, [data-testid="stAppViewBlockContainer"]::after{
  content:''; position:absolute; inset:0; z-index:0; pointer-events:none; opacity:.9;
  background:%(marca)s 50%% 46%%/250px no-repeat;
}
.sx-home-eyebrow{ margin-top:2px; }
"""

CSS_TELA = {
    # nome: (largura, margem superior)
    "home": (508, "193px"),
    "tipo": (458, "130px"),
    "modo": (452, "240px"),
    "ia": (554, "70px"),
    "banco": (638, "28px"),
    "manual": (760, "28px"),
}

# Textos centralizados / alinhamentos dos widgets dentro dos cartões.
CSS_CARTAO_WIDGETS = """
.block-container .stButton, [data-testid="stAppViewBlockContainer"] .stButton{ width:100%%; }
.block-container [data-testid="stWidgetLabel"], [data-testid="stAppViewBlockContainer"] [data-testid="stWidgetLabel"]{ width:100%%; text-align:left; }
.block-container [data-baseweb="input"] input, .block-container [data-baseweb="textarea"] textarea{ text-align:left; }
"""

CSS_HOME_BOTOES = """
.block-container .stButton{ display:flex; justify-content:center; }
.block-container .stButton button{ width:auto !important; min-width:190px; }
"""

CSS_LARGO = """
.block-container, [data-testid="stAppViewBlockContainer"]{ max-width:%(largura)spx !important; margin-top:0 !important; }
"""


def css_tela(nome: str) -> str:
    """CSS específico da tela (largura, margem, e se a página inteira vira cartão)."""
    if nome in CSS_TELA:
        largura, topo = CSS_TELA[nome]
        css = CSS_CARTAO % {"largura": largura, "topo": topo}
        css += CSS_CARTAO_WIDGETS % {}
        if nome != "banco":
            css += ".block-container .stButton{ display:flex; justify-content:center; }"
        else:
            css += ".block-container .stButton{ display:flex; justify-content:flex-start; }"
        if nome == "home":
            css += CSS_HOME_EXTRA % {"cabo": _uri(_ROBO_PENDURADO), "marca": _uri(_MARCA_DAGUA)}
            css += CSS_HOME_BOTOES
        return css
    largura = 960 if nome == "formulario" else 900
    return CSS_LARGO % {"largura": largura}


def aplicar_estilo(tela: str = "home") -> None:
    """Injeta o CSS global + o da tela atual e a arte de fundo (via st.html, sem
    passar pelo parser de markdown)."""
    st.html("<style>" + _FONTES + CSS_BASE + CSS_TITULOS + CSS_INFO + _css_fundo() + css_tela(tela) + "</style>")


# ---------------------------------------------------------------------------
# Helpers de renderização
# ---------------------------------------------------------------------------

def marcador(classe: str) -> None:
    """Âncora invisível para o CSS (display:none no container)."""
    st.html(f'<span class="sx-mark {escape(classe)}"></span>')


@contextmanager
def cartao() -> Iterator[None]:
    """Cartão de borda grossa com sombra (bloco do formulário, seção do dossiê)."""
    with st.container(border=True):
        st.html('<span class="sx-card sx-mark"></span>')
        yield


@contextmanager
def caixa(estado: str = "pend") -> Iterator[None]:
    """Caixa interna de seção: 'pend' (borda clara), 'ok' (verde, preenchida/bloqueada),
    'dash' (tracejada âmbar, diligência pendente)."""
    with st.container(border=True):
        st.html(f'<span class="sx-box {escape(estado)} sx-mark"></span>')
        yield


def titulo_cartao(eyebrow: str, titulo: str, descricao: str = "", sub: str = "",
                  carimbo: str = "", pequeno: bool = False, subtitulo_forte: str = "",
                  descricao_normal: str = "") -> None:
    """Cabeçalho das telas de cartão: eyebrow, título dourado com sombra, subtítulo,
    descrição em caixa-alta e carimbo rotacionado."""
    t = "sx-title sx-title-sm" if pequeno else "sx-title"
    partes = [f'<div class="sx-eyebrow">{escape(eyebrow)}</div>',
              f'<div class="{t}">{escape(titulo)}</div>']
    if subtitulo_forte:
        partes.append(f'<div class="sx-sub-forte">{escape(subtitulo_forte)}</div>')
    if sub:
        partes.append(f'<div class="sx-sub">{escape(sub)}</div>')
    if descricao:
        partes.append(f'<div class="sx-desc">{escape(descricao)}</div>')
    if descricao_normal:
        partes.append(f'<div class="sx-desc-n">{escape(descricao_normal)}</div>')
    if carimbo:
        partes.append(f'<div class="sx-stamp">{escape(carimbo)}</div>')
    st.html('<div class="sx-head">' + "".join(partes) + "</div>")


CSS_TITULOS = """
.sx-head{ text-align:center; margin-bottom:6px; }
.sx-eyebrow{ font-family:var(--mono); font-weight:700; font-size:11.5px; letter-spacing:.2em; text-transform:uppercase; color:var(--accent); }
.sx-title{
  font-family:var(--display); font-weight:900; font-size:56px; margin:14px 0 0; letter-spacing:.03em; line-height:1.1;
  text-transform:uppercase; color:var(--gold); text-shadow:3px 3px 0 var(--purple-soft), 6px 6px 0 var(--home-black);
}
.sx-title-sm{ font-size:34px; margin-top:12px; text-shadow:2px 2px 0 var(--purple-soft), 4px 4px 0 var(--home-black); }
.sx-sub-forte{ font-family:var(--mono); font-weight:700; font-size:14px; color:var(--accent); margin-top:14px; letter-spacing:.05em; text-transform:uppercase; }
.sx-sub{ font-family:var(--mono); font-weight:600; font-size:13px; color:var(--accent); margin-top:10px; letter-spacing:.04em; text-transform:uppercase; }
.sx-desc{ font-family:var(--mono); margin:20px auto 0; max-width:390px; line-height:1.7; font-size:12.5px; color:var(--accent); text-transform:uppercase; }
.sx-desc-n{ font-family:var(--mono); margin:18px auto 14px; max-width:400px; line-height:1.65; font-size:13px; color:var(--accent); }
.sx-sub-rot{ font-family:var(--mono); font-size:10.5px; letter-spacing:.08em; text-transform:uppercase; color:var(--ink-soft); font-weight:500; margin:10px 0 2px; }
.sx-rot-fixo{ font-family:var(--mono); font-size:10.5px; letter-spacing:.08em; text-transform:uppercase; color:var(--ink-soft); margin:12px 0 4px; }
.sx-pill-tracejada{ display:inline-block; font-family:var(--mono); font-size:13.5px; color:var(--ink); padding:6px 14px; border:1.5px dashed var(--purple-soft); border-radius:6px; margin-bottom:8px; }
.sx-nota-box{ border:1.5px solid var(--line); border-radius:10px; padding:12px 16px 10px; margin:6px 0 4px; background:rgba(255,255,255,.14); }
.sx-rodape{ text-align:center; font-family:var(--mono); font-size:11.5px; color:var(--ink-soft); margin:26px 0 8px; }
.sx-stamp{
  display:inline-block; margin:26px auto 8px; border:3px double var(--accent); color:var(--accent);
  font-family:var(--mono); font-weight:600; font-size:10.5px; letter-spacing:.14em; padding:6px 16px; border-radius:6px;
  transform:rotate(-3deg); text-transform:uppercase; background:var(--paper-alt);
}
"""


CSS_INFO = """
.sx-info-card{
  background:var(--paper-alt); border:3px solid var(--purple-deep); border-radius:16px;
  box-shadow:6px 6px 0 var(--accent); padding:18px 22px 14px; margin:0 6px 22px 0;
}
.sx-info-card .sx-sec-titulo{ margin-bottom:12px; }
"""


def cabecalho_bloco(numero: str, titulo: str) -> None:
    """Cabeçalho dentro do cartão do bloco ("BLOCO 2" + título + linha)."""
    st.html(f'<div class="sx-bloco-num">{escape(numero)}</div>'
            f'<div class="sx-bloco-titulo">{escape(titulo)}</div>')


def titulo_secao(texto: str) -> None:
    st.html(f'<div class="sx-sec-titulo">{escape(texto)}</div>')


def subtitulo(texto: str) -> None:
    st.html(f'<div class="sx-subhead">{escape(texto)}</div>')


def nota(texto: str) -> None:
    st.html(f'<div class="sx-nota">{escape(texto)}</div>')


def dica(texto_html: str) -> None:
    """Texto auxiliar centralizado (aceita <b>); NÃO passe texto do usuário aqui."""
    st.html(f'<div class="sx-hint">{texto_html}</div>')


def rotulo_estado(texto: str, ok: bool) -> None:
    st.html(f'<div class="sx-rotulo {"ok" if ok else "pend"}">{escape(texto)}</div>')


def salvo_em(texto: str) -> None:
    st.html(f'<div class="sx-salvo">{escape(texto)}</div>')


def msg_ok(texto: str) -> None:
    st.html(f'<div class="sx-ok">&#10003; {escape(texto)}</div>')


def msg_erro(texto: str) -> None:
    st.html(f'<div class="sx-erro">{escape(texto)}</div>')


def vazio(texto: str) -> None:
    st.html(f'<div class="sx-vazio">{escape(texto)}</div>')


def separador_ou(texto: str) -> None:
    st.html(f'<div class="sx-sep">&mdash; {escape(texto)} &mdash;</div>')


@contextmanager
def variante(nome: str) -> Iterator[None]:
    """Container que muda o aspecto dos botões dentro dele. nome: 'sm' (SALVAR pequeno),
    'lnk' (link "← Voltar"), 'topo' (Voltar ao Sentinela), 'opcoes' (botões grandes de escolha),
    'linhas' (resultados do Banco)."""
    with st.container():
        st.html(f'<span class="sx-{escape(nome)} sx-mark"></span>')
        yield


def selo(texto: str, estilo: str) -> None:
    st.html(f'<div class="sx-selo-wrap"><div class="sx-selo {escape(estilo)}">{escape(texto)}</div></div>')


def avatar_svg(genero: str) -> str:
    """Pictograma do cliente (masculino/feminino) para o cabeçalho do dossiê.
    Devolvido como <img> data-URI, porque <svg> inline é removido pelo st.html."""
    if genero == "F":
        corpo = ('<circle cx="11" cy="5" r="4.2" fill="#2A2035"/>'
                 '<path d="M11 10 L18 24 L4 24 Z" fill="#2A2035"/>'
                 '<rect x="8" y="23" width="2.2" height="6" fill="#2A2035"/>'
                 '<rect x="12.2" y="23" width="2.2" height="6" fill="#2A2035"/>')
    else:
        corpo = ('<circle cx="11" cy="5" r="4.2" fill="#2A2035"/>'
                 '<rect x="6" y="10" width="10" height="11" rx="3" fill="#2A2035"/>'
                 '<rect x="6.5" y="20" width="3.6" height="9" rx="1.4" fill="#2A2035"/>'
                 '<rect x="11.9" y="20" width="3.6" height="9" rx="1.4" fill="#2A2035"/>')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 22 30">{corpo}</svg>'
    return f'<img class="sx-avatar" alt="" src="data:image/svg+xml;utf8,{quote(svg, safe="")}"/>'


def link_externo(rotulo: str, url: str) -> None:
    """Link clicável para um endereço externo (abre em nova aba), com o aspecto do link discreto."""
    with variante("lnk"):
        st.link_button(rotulo, url)


def pilula(rotulo: str, valor: str, extra: str = "") -> str:
    return (f'<div class="sx-pill {extra}"><span class="sx-pill-l">{escape(rotulo)}</span>'
            f'<span class="sx-pill-v">{escape(valor)}</span></div>')


def pilulas(itens: List[Tuple[str, str]]) -> str:
    return '<div class="sx-pills">' + "".join(pilula(r, v) for r, v in itens) + "</div>"


def req(rotulo: str) -> str:
    """Rótulo de campo obrigatório (★, como no artefato)."""
    return f"{rotulo} ★"
