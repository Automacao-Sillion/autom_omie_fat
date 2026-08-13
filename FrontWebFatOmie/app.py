"""
Envio de faturamento — Front Streamlit (Sillion)
Encaminha arquivo (xlsx/xlsb/csv) + email + empresa de origem para o backend
N8N via POST JSON com base64.

Arquitetura:
- app.py        → lógica Python (config, envio, widgets de input)
- styles/       → CSS (visual)
- templates/    → HTML estrutural (header, hero, footer, etc.)
"""

import base64
import re
import mimetypes
from datetime import datetime
from pathlib import Path

import requests
import streamlit as st

import conferencia_rf as crf

# ============================================================
# Caminhos
# ============================================================
BASE_DIR = Path(__file__).parent
CSS_PATH = BASE_DIR / "styles" / "main.css"
# Tema Sillion: carregado DEPOIS do main.css e só redefine valores de
# variáveis (paleta do portal + modo escuro). Some o arquivo = volta o
# visual anterior, sem outra alteração.
TEMA_PATH = BASE_DIR / "styles" / "tema-sillion.css"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# ============================================================
# Recursos externos
# ============================================================
LOGO_EXTERNO = "https://www.sillion.com.br/wp-content/themes/sillion/images/logo-black-tm.svg"
FAVICON_URL  = "https://www.sillion.com.br/wp-content/themes/sillion/images/logo-white-tm.svg"
LOGO_LOCAL_FILE = STATIC_DIR / "logo-sillion.svg"


def resolver_logo_url() -> str:
    """
    Retorna o caminho do logo:
    - Se houver `static/logo-sillion.svg`, usa a versão local (mais rápida e offline).
    - Caso contrário, cai para a URL externa do site da Sillion.
    Streamlit sanitiza o atributo `onerror` em HTML, então o fallback
    precisa ser feito no Python, não no navegador.
    """
    if LOGO_LOCAL_FILE.exists():
        return "app/static/logo-sillion.svg"
    return LOGO_EXTERNO

# ============================================================
# Config da página
# ============================================================
st.set_page_config(
    page_title="Sillion · Envio de faturamento",
    page_icon=FAVICON_URL,
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ============================================================
# Constantes
# ============================================================
# Apenas emails @sillion.com.br são aceitos (case-insensitive)
DOMINIO_PERMITIDO = "sillion.com.br"
EMAIL_REGEX = re.compile(
    rf"^[A-Za-z0-9._%+\-]+@{re.escape(DOMINIO_PERMITIDO)}$",
    re.IGNORECASE,
)
TIPOS_ACEITOS = ["xlsx", "xlsb", "csv"]

# Tipos de faturamento aceitos pelo backend (esteira de processamento N8N)
TIPOS_FATURAMENTO = ["TOT", "VALE"]

# ------------------------------------------------------------------
# TEMPORÁRIO (12/08/2026, pedido do Willian) — vigente até o término
# da reforma: RF cujas notas estão TODAS canceladas pode ser reenviado
# mediante marcação explícita (começa desmarcado). Nota FATURADA segue
# bloqueando sempre; substituição (cancelada + faturada nova) também.
# Ao fim da reforma, mude para False — o bloqueio duro volta sozinho.
# ------------------------------------------------------------------
PERMITIR_REENVIO_CANCELADA = True

# Empresas que originam a solicitação (esteira de processamento no N8N)
EMPRESAS = ["Sitrack", "Sillion"]

TIMEOUT_REQ = 120  # segundos

MIME_FALLBACK = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xlsb": "application/vnd.ms-excel.sheet.binary.macroEnabled.12",
    "csv": "text/csv",
}


# ============================================================
# Helpers de renderização (templates + CSS)
# ============================================================
def render_template(nome: str, **variaveis) -> str:
    """
    Lê um arquivo .html em templates/ e substitui placeholders no
    formato {{nome_da_variavel}} pelos valores passados.
    """
    caminho = TEMPLATES_DIR / f"{nome}.html"
    html = caminho.read_text(encoding="utf-8")
    for chave, valor in variaveis.items():
        html = html.replace(f"{{{{{chave}}}}}", str(valor))
    return html


def inject(html: str) -> None:
    """Injeta um trecho HTML na página."""
    st.markdown(html, unsafe_allow_html=True)


def carregar_css(caminho: Path) -> None:
    """Lê o arquivo CSS e injeta na página via st.markdown."""
    try:
        css = caminho.read_text(encoding="utf-8")
        inject(f"<style>{css}</style>")
    except FileNotFoundError:
        st.warning(f"Arquivo de estilos não encontrado: {caminho}")


# Carrega meta tags + CSS antes de qualquer conteúdo
inject(render_template("meta"))
carregar_css(CSS_PATH)
if TEMA_PATH.exists():          # ordem importa: o tema sobrescreve o main.css
    carregar_css(TEMA_PATH)


# ============================================================
# Configuração segura: URL do webhook
# ============================================================
try:
    WEBHOOK_URL = st.secrets["N8N_WEBHOOK_URL"]
except (KeyError, FileNotFoundError):
    WEBHOOK_URL = None

# Webhook de CONSULTA de RFs já cadastrados (conferência do fluxo VALE).
try:
    WEBHOOK_CONSULTA_RF_URL = st.secrets["N8N_WEBHOOK_CONSULTA_RF_URL"]
except (KeyError, FileNotFoundError):
    WEBHOOK_CONSULTA_RF_URL = None


# ============================================================
# Helpers de negócio
# ============================================================
def email_valido(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email.strip()))


def detectar_mime(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in MIME_FALLBACK:
        return MIME_FALLBACK[ext]
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def montar_payload(
    email: str,
    empresa_select: str,
    arquivo,
    tipo_faturamento: str,
) -> dict:
    """
    Monta o payload JSON enviado ao N8N.
    `empresa_select` é uma string com o valor escolhido ('Sitrack' ou 'Sillion').
    """
    conteudo = arquivo.getvalue()
    return {
        "email": email.strip(),
        "empresa_select": empresa_select,
        "filename": arquivo.name,
        "file_base64": base64.b64encode(conteudo).decode("utf-8"),
        "mime_type": detectar_mime(arquivo.name),
        "tipo_faturamento": tipo_faturamento,
    }


def enviar_para_n8n(url: str, payload: dict) -> requests.Response:
    return requests.post(
        url,
        json=payload,
        timeout=TIMEOUT_REQ,
        headers={"Content-Type": "application/json"},
    )


# ============================================================
# UI — Header + Hero (vindos dos templates HTML)
# ============================================================
inject(render_template("header", logo_url=resolver_logo_url()))
inject(render_template(
    "hero",
    titulo="Envio de faturamento",
    subtitulo="Envie o arquivo de faturamento para processamento automático. "
              "O relatório retornará no seu email.",
))


# ============================================================
# Verificação de configuração
# ============================================================
if not WEBHOOK_URL:
    st.error(
        "A URL do webhook N8N não foi configurada. "
        "Crie o arquivo `.streamlit/secrets.toml` com a chave `N8N_WEBHOOK_URL` "
        "ou configure-a no painel do Streamlit Community Cloud."
    )
    st.stop()


# ============================================================
# UI — Formulário (widgets Streamlit — precisam falar com Python)
# ============================================================
email = st.text_input(
    "Email corporativo",
    placeholder=f"usuario@{DOMINIO_PERMITIDO}",
    help=f"Apenas emails do domínio @{DOMINIO_PERMITIDO} são aceitos. "
         "O relatório processado será enviado para este endereço.",
)

empresa_select = st.radio(
    "Selecione a empresa:",
    options=EMPRESAS,
    index=None,
    horizontal=True,
    help="Indica qual empresa originou a solicitação. O backend usa este valor "
         "para direcionar o processamento.",
)

arquivo = st.file_uploader(
    "Arquivo de faturamento",
    type=TIPOS_ACEITOS,
    help="Formatos aceitos: .xlsx, .xlsb, .csv",
)

tipo_faturamento = None
if arquivo is not None:
    tamanho_mb = len(arquivo.getvalue()) / (1024 * 1024)
    inject(render_template(
        "file_preview",
        nome_arquivo=arquivo.name,
        tamanho_mb=f"{tamanho_mb:.2f}",
    ))

    # Campo obrigatório: tipo de faturamento associado ao arquivo
    tipo_faturamento = st.selectbox(
        "Tipo de faturamento",
        options=TIPOS_FATURAMENTO,
        index=None,
        placeholder="Selecione o tipo...",
        help="Identifica em qual esteira o arquivo será processado pelo backend.",
    )

# ============================================================
# Helpers de exibição da conferência de RFs
# ============================================================
def _esc(valor) -> str:
    """Escapa texto para ir dentro do HTML da tabela."""
    return (
        str("" if valor is None else valor)
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def card_resumo(novos: int, bloqueados: int, legado: int, canceladas: int = 0) -> str:
    """Faixa com os números, para o usuário entender a situação num relance."""
    partes = [
        f'<div class="rf-card ok"><div class="rf-num">{novos}</div>'
        f'<div class="rf-rot">Novos</div></div>'
    ]
    if bloqueados:
        partes.append(
            f'<div class="rf-card bloq"><div class="rf-num">{bloqueados}</div>'
            f'<div class="rf-rot">Bloqueados</div></div>'
        )
    if canceladas:
        partes.append(
            f'<div class="rf-card aviso"><div class="rf-num">{canceladas}</div>'
            f'<div class="rf-rot">Canceladas · reenvio liberado</div></div>'
        )
    if legado:
        partes.append(
            f'<div class="rf-card aviso"><div class="rf-num">{legado}</div>'
            f'<div class="rf-rot">Já enviados</div></div>'
        )
    return f'<div class="rf-resumo">{"".join(partes)}</div>'


def selo_status(status: str, substituicao: bool) -> str:
    """Selo colorido do status da nota. Cancelada tem destaque próprio."""
    if substituicao:
        return '<span class="rf-selo subst">SUBSTITUÍDA</span>'
    if status == crf.STATUS_CANCELADA:
        return '<span class="rf-selo cancelada">CANCELADA</span>'
    return f'<span class="rf-selo faturada">{_esc(status or crf.STATUS_PADRAO)}</span>'


def cabecalho_liberados(n_total: int, n_novos: int, n_reenviaveis: int) -> str:
    """
    Cabeçalho do bloco de liberados, com a MESMA moldura do bloco de
    bloqueados (`.rf-bloco`).

    A tabela é montada com uma st.columns por linha — não com st.data_editor.
    Motivo: o data_editor desenha em canvas e não aceita HTML, então lá dentro
    não existe pílula nem fonte monoespaçada. Com st.columns, o checkbox é
    widget real do Streamlit e as outras células são HTML nosso, o que dá o
    layout do bloco de bloqueados COM o checkbox na linha.
    """
    extra = f" · {n_novos} novos, {n_reenviaveis} reenviáveis" if n_reenviaveis else ""
    return (
        '<div class="rf-bloco aprov" style="padding-bottom:4px;margin-bottom:0">'
        f"<h4>Liberados · {n_total} RFs{extra}</h4>"
        '<p class="rf-exp" style="margin-bottom:0">Desmarque para deixar de fora '
        "do envio. Reenviáveis começam desmarcados.</p>"
        "</div>"
    )


# larguras das colunas da tabela de liberados (checkbox, RF, linha, situação, histórico)
COLS_LIBERADOS = [0.7, 2.3, 0.9, 1.2, 2.9]


def celula(texto: str, classe: str = "") -> str:
    """Célula da tabela de liberados, com o mesmo estilo da tabela de bloqueados."""
    cls = f' class="rf-cel {classe}"' if classe else ' class="rf-cel"'
    return f"<div{cls}>{texto}</div>"


def tabela_bloqueados(bloqueados: list) -> str:
    """
    Tabela SOMENTE LEITURA dos RFs bloqueados.
    Não tem checkbox de propósito: RF com nota vinculada não é uma escolha
    do usuário — ele não vai, e a tela precisa deixar isso explícito.
    """
    linhas = []
    for b in bloqueados:
        info = b["info"]
        notas = info.get("notas") or [{}]
        # um RF substituído tem 2 notas: mostra as duas, uma por linha visual
        numeros = "<br>".join(
            f'{_esc(n.get("numero") or "—")} {selo_status(n.get("status"), False)}'
            for n in notas
        )
        linhas.append(
            "<tr>"
            f'<td class="rf-mono">{_esc(b["rf"])}</td>'
            f'<td>{b["linha"]}</td>'
            f'<td>{numeros}</td>'
            f'<td>{selo_status(None, True) if info.get("substituicao") else ""}</td>'
            f'<td class="rf-motivo">{_esc(crf.motivo_bloqueio(info))}</td>'
            "</tr>"
        )

    # Cabeçalho enxuto: o "por quê" de cada linha está na coluna Motivo.
    return (
        '<div class="rf-bloco">'
        f"<h4>Bloqueados · {len(bloqueados)} RFs não serão enviados</h4>"
        '<p class="rf-exp">Possuem nota fiscal emitida. Linhas removidas do arquivo.</p>'
        '<div class="rf-scroll"><table class="rf-tab"><thead><tr>'
        "<th>RF</th><th>Linha</th><th>Nota fiscal</th><th></th><th>Motivo</th>"
        "</tr></thead><tbody>" + "".join(linhas) + "</tbody></table></div></div>"
    )


# ============================================================
# UI — Conferência de RFs (ativa apenas no fluxo VALE, após upload)
# ============================================================
# `linhas_remover` acumula as linhas que NÃO vão no envio:
#   - bloqueados  -> entram à força, o usuário não escolhe
#   - legado      -> entram só se o usuário não marcar "Reenviar"
# O arquivo filtrado é gerado apenas na hora do envio, mantendo o payload
# N8N idêntico ao padrão atual.
linhas_remover = set()
conferencia_ok = True  # quando False, o envio VALE fica bloqueado


if arquivo is not None and tipo_faturamento == "VALE":
    st.markdown("---")
    st.subheader("Conferência de RFs")

    if not WEBHOOK_CONSULTA_RF_URL:
        conferencia_ok = False
        st.error(
            "O webhook de consulta de RFs não foi configurado. "
            "Adicione a chave `N8N_WEBHOOK_CONSULTA_RF_URL` em "
            "`.streamlit/secrets.toml` (ou nos Secrets do Streamlit Cloud)."
        )
    else:
        resultado = None
        try:
            with st.spinner("Consultando RFs já cadastrados no banco de dados..."):
                resultado = crf.conferir(
                    arquivo.name, arquivo.getvalue(), WEBHOOK_CONSULTA_RF_URL, "VALE",
                    liberar_canceladas=PERMITIR_REENVIO_CANCELADA,
                )
        except ValueError as exc:
            conferencia_ok = False
            st.error(f"Não foi possível conferir os RFs: {exc}")
        except requests.exceptions.RequestException as exc:
            conferencia_ok = False
            st.error(
                "Falha ao consultar o banco de RFs no N8N. "
                "O envio VALE fica bloqueado até a conferência funcionar. "
                f"Detalhe: {exc}"
            )

        if resultado is not None:
            bloqueados = resultado["bloqueados"]
            canceladas_lib = resultado.get("canceladas", [])
            legado = resultado["legado"]
            novos = resultado["novos"]

            if not resultado["rfs"]:
                conferencia_ok = False
                st.error(
                    'Nenhum RF encontrado no arquivo. Confirme se a coluna "RF" '
                    "está preenchida (cabeçalho na linha 1)."
                )
            else:
                # --- Bloqueados saem do envio SEMPRE, antes de qualquer escolha ---
                linhas_remover |= crf.linhas_bloqueadas(resultado)

                inject(card_resumo(
                    len(novos), len(bloqueados), len(legado), len(canceladas_lib)
                ))

                # ---- RF repetido dentro do PRÓPRIO arquivo ----------------
                # Só alerta para linhas que PODEM ir no envio: duplicata entre
                # linhas bloqueadas é irrelevante (não vão de qualquer jeito).
                linhas_bloq = crf.linhas_bloqueadas(resultado)
                repetidos = {
                    rf: [ln for ln in linhas if ln not in linhas_bloq]
                    for rf, linhas in resultado.get("duplicados_no_arquivo", {}).items()
                }
                repetidos = {rf: ls for rf, ls in repetidos.items() if len(ls) > 1}
                if repetidos:
                    lista = " · ".join(
                        f"RF {rf} nas linhas {', '.join(map(str, ls))}"
                        for rf, ls in sorted(repetidos.items())
                    )
                    st.warning(
                        f"**{len(repetidos)} RF(s) repetidos no arquivo:** {lista}. "
                        "Linhas repetidas ficam **bloqueadas para envio** — mantenha "
                        "apenas uma na planilha e envie o arquivo novamente."
                    )

                # ---- Balde 1: BLOQUEADOS (somente leitura) ----------------
                if bloqueados:
                    inject(tabela_bloqueados(bloqueados))

                    if not PERMITIR_REENVIO_CANCELADA:
                        canc_bloq = [b for b in bloqueados if crf.tem_cancelada(b["info"])]
                        if canc_bloq:
                            # o não-óbvio em uma linha: cancelar não devolve o RF
                            st.error(
                                f"**{len(canc_bloq)} RFs com nota cancelada.** "
                                "O cancelamento não libera o RF para novo faturamento."
                            )

                # ---- Balde 2 + 3 numa tabela só: o que PODE ir ------------
                # Novos, reenviáveis e canceladas liberadas convivem na mesma
                # lista; o checkbox é a única diferença. Novo já vem marcado;
                # reenvio e cancelada vêm desmarcados (decisão consciente).
                qtd_reenvio = 0
                qtd_canc_envio = 0
                total_envio = 0
                if novos or legado or canceladas_lib:
                    def _hist_cancelada(info):
                        nums = [n.get("numero") for n in info.get("notas", []) if n.get("numero")]
                        return "NF " + ", ".join(nums) + " cancelada" if nums else "nota cancelada"

                    candidatos = (
                        [{"rf": n["rf"], "linha": n["linha"], "tipo": "novo", "detalhe": ""}
                         for n in novos]
                        + [{"rf": l["rf"], "linha": l["linha"], "tipo": "reenvio",
                            "detalhe": (f"enviado em {l['info']['enviado_em']}"
                                        if l["info"].get("enviado_em") else "enviado antes")}
                           for l in legado]
                        + [{"rf": c["rf"], "linha": c["linha"], "tipo": "cancelada",
                            "detalhe": _hist_cancelada(c["info"])}
                           for c in canceladas_lib]
                    )
                    # marca as linhas com o mesmo RF repetido no arquivo:
                    # o NÚMERO ganha destaque visual na própria linha, além
                    # da anotação de em qual outra linha ele aparece
                    for c in candidatos:
                        outras = [ln for ln in repetidos.get(c["rf"], []) if ln != c["linha"]]
                        c["repetido"] = bool(outras)
                        if outras:
                            extra = "repetido na linha " + ", ".join(map(str, outras))
                            c["detalhe"] = f"{c['detalhe']} · {extra}" if c["detalhe"] else extra
                    candidatos.sort(key=lambda x: x["linha"])

                    if canceladas_lib:
                        st.warning(
                            f"**{len(canceladas_lib)} RF(s) de nota cancelada com reenvio "
                            "liberado** — exceção temporária durante a reforma. "
                            "Começam desmarcados; marque para reenviar."
                        )

                    inject(cabecalho_liberados(
                        len(candidatos), len(novos), len(legado) + len(canceladas_lib)
                    ))

                    chave = f"envio_{arquivo.name}_{len(arquivo.getvalue())}"

                    # rótulos curtos: "Desmarcar todos" quebrava em duas linhas e
                    # deixava os dois botões com alturas diferentes
                    col_a, col_b, _ = st.columns([1, 1, 3])
                    if col_a.button("Todos", key=f"{chave}_all", use_container_width=True):
                        st.session_state[f"{chave}_forcar_agora"] = True
                    if col_b.button("Nenhum", key=f"{chave}_none", use_container_width=True):
                        st.session_state[f"{chave}_forcar_agora"] = False

                    # "Marcar/Desmarcar todos" grava direto no state de cada
                    # checkbox. Precisa acontecer ANTES dos widgets nascerem —
                    # o clique no botão já provocou o rerun, então aqui é seguro.
                    # Linha repetida NUNCA é marcada, nem pelo "Marcar todos":
                    # a duplicidade se resolve na planilha, não na tela.
                    forcar = st.session_state.pop(f"{chave}_forcar_agora", None)
                    if forcar is not None:
                        for c in candidatos:
                            st.session_state[f"{chave}_chk_{c['linha']}"] = (
                                forcar and not c.get("repetido")
                            )

                    # Container com altura fixa = rolagem sem esticar a página.
                    # A chave é FIXA e sem o prefixo das outras chaves: o CSS
                    # escopa por `.st-key-tabliberados`, e se o prefixo fosse
                    # compartilhado com os botões/checkboxes (que usam `chave`)
                    # o estilo do painel vazaria para eles.
                    altura = min(330, 60 + 34 * len(candidatos))
                    try:
                        caixa = st.container(height=altura, key="tabliberados")
                    except TypeError:      # Streamlit sem `key` em container
                        caixa = st.container(height=altura)

                    with caixa:
                        # cabeçalho da tabela
                        h = st.columns(COLS_LIBERADOS, vertical_alignment="center")
                        for col, titulo in zip(h, ["", "RF", "LINHA", "SITUAÇÃO", "HISTÓRICO"]):
                            col.markdown(
                                f'<div class="rf-cab">{titulo}</div>', unsafe_allow_html=True
                            )

                        marcados = {}
                        for c in candidatos:
                            k = f"{chave}_chk_{c['linha']}"
                            if k not in st.session_state:
                                # novo já vai; reenvio é decisão consciente
                                # novo já vai; reenvio e cancelada são decisão consciente
                                st.session_state[k] = (
                                    c["tipo"] == "novo" and not c.get("repetido")
                                )
                            if c.get("repetido"):
                                # repetido é TRAVADO: desmarcado e sem interação,
                                # até o usuário corrigir a planilha
                                st.session_state[k] = False

                            cols = st.columns(COLS_LIBERADOS, vertical_alignment="center")
                            marcados[c["linha"]] = cols[0].checkbox(
                                f"Enviar RF {c['rf']}",
                                key=k,
                                label_visibility="collapsed",
                                disabled=bool(c.get("repetido")),
                            )
                            # RF repetido no arquivo: o NÚMERO fica destacado em
                            # âmbar com o selo REPETIDO colado nele — a linha
                            # denuncia sozinha, sem depender do histórico
                            rf_html = (
                                f'<span class="rf-num-rep">{_esc(c["rf"])}</span>'
                                '<span class="rf-selo repetido">REPETIDO</span>'
                                if c.get("repetido")
                                else _esc(c["rf"])
                            )
                            cols[1].markdown(
                                celula(rf_html, "rf-mono"), unsafe_allow_html=True
                            )
                            cols[2].markdown(celula(str(c["linha"])), unsafe_allow_html=True)
                            selo = {
                                "novo": '<span class="rf-selo novo">NOVO</span>',
                                "reenvio": '<span class="rf-selo reenvio">REENVIO</span>',
                                "cancelada": '<span class="rf-selo cancelada">CANCELADA</span>',
                            }[c["tipo"]]
                            cols[3].markdown(celula(selo), unsafe_allow_html=True)
                            cols[4].markdown(
                                celula(_esc(c["detalhe"]), "rf-motivo"), unsafe_allow_html=True
                            )

                    fora_linhas = {ln for ln, ok in marcados.items() if not ok}
                    linhas_remover |= fora_linhas
                    dentro = [c for c in candidatos if c["linha"] not in fora_linhas]
                    total_envio = len(dentro)
                    qtd_reenvio = sum(1 for c in dentro if c["tipo"] != "novo")
                    qtd_canc_envio = sum(1 for c in dentro if c["tipo"] == "cancelada")

                # ---- Trava do .xlsb: a estrutura do envio NÃO pode mudar --
                # Remover linha de .xlsb obriga a regravar o arquivo, e o
                # pyxlsb não escreve .xlsb -- o filtro converteria para .xlsx,
                # mudando `filename` e `mime_type` no payload. Como a remoção
                # de bloqueado é FORÇADA, isso passaria a acontecer sozinho.
                # Preferimos barrar o envio a entregar outra estrutura à esteira.
                ext_arquivo = arquivo.name.rsplit(".", 1)[-1].lower()
                if ext_arquivo == "xlsb" and linhas_remover:
                    conferencia_ok = False
                    st.error(
                        "**Arquivo .xlsb com linhas a remover: envio bloqueado.** "
                        "Salve a planilha como `.xlsx` e envie novamente."
                    )

                # ---- Rodapé: o que vai, afinal ---------------------------
                # total_envio e qtd_reenvio vêm da tabela acima (o usuário pode
                # ter desmarcado linhas), não de len(novos).
                if not conferencia_ok:
                    pass  # já há erro na tela; não sobrepor com outra mensagem
                elif total_envio == 0:
                    conferencia_ok = False
                    st.info("**Nenhum RF a enviar.** Todos estão bloqueados ou não foram selecionados.")
                else:
                    fora = len(linhas_remover)
                    canc_txt = (
                        f" Inclui {qtd_canc_envio} de nota cancelada."
                        if qtd_canc_envio else ""
                    )
                    st.success(
                        f"**{total_envio} RFs** serão enviados. "
                        f"{fora} linhas removidas, sendo {len(bloqueados)} bloqueadas."
                        f"{canc_txt}"
                    )

st.write("")
enviar = st.button("Enviar arquivo", type="primary", use_container_width=True)


# ============================================================
# Lógica de envio
# ============================================================
if enviar:
    erros = []

    if not email.strip():
        erros.append("Informe o email.")
    elif not email_valido(email):
        erros.append(
            f"Email inválido. Use um endereço corporativo @{DOMINIO_PERMITIDO} "
            "(ex: seu.nome@" + DOMINIO_PERMITIDO + ")."
        )

    if not empresa_select:
        erros.append("Selecione a empresa.")

    if arquivo is None:
        erros.append("Selecione um arquivo para enviar.")
    elif not tipo_faturamento:
        erros.append("Selecione o tipo de faturamento.")
    elif tipo_faturamento == "VALE" and not conferencia_ok:
        erros.append(
            "A conferência de RFs não foi concluída (ou não há RFs a enviar). "
            "O envio VALE está bloqueado."
        )

    if erros:
        for e in erros:
            st.error(e)
    else:
        with st.spinner("Enviando arquivo para processamento..."):
            try:
                # No fluxo VALE, remove do arquivo as linhas dos RFs duplicados
                # que o usuário optou por não reenviar. O formato do arquivo e
                # o payload permanecem no padrão que o N8N já espera.
                arquivo_envio = arquivo
                if tipo_faturamento == "VALE" and linhas_remover:
                    arquivo_envio = crf.gerar_arquivo_filtrado(
                        arquivo.name, arquivo.getvalue(), linhas_remover
                    )

                payload = montar_payload(
                    email=email,
                    empresa_select=empresa_select,
                    arquivo=arquivo_envio,
                    tipo_faturamento=tipo_faturamento,
                )
                resp = enviar_para_n8n(WEBHOOK_URL, payload)

                if 200 <= resp.status_code < 300:
                    @st.dialog("Envio realizado")
                    def confirmacao():
                        st.success("Arquivo enviado com sucesso!")
                        st.write(
                            f"O relatório processado será encaminhado para "
                            f"**{email.strip()}** assim que o backend concluir "
                            "o processamento."
                        )
                        st.caption(
                            f"Enviado em {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}"
                        )
                        if st.button("OK", use_container_width=True):
                            st.rerun()

                    confirmacao()
                else:
                    st.error(f"O backend respondeu com status {resp.status_code}.")
                    with st.expander("Detalhes da resposta"):
                        st.code(resp.text or "(sem corpo)")
            except requests.exceptions.Timeout:
                st.error("Tempo de resposta excedido. Verifique se o N8N está acessível.")
            except requests.exceptions.ConnectionError:
                st.error("Falha de conexão. Verifique a URL do webhook.")
            except Exception as exc:
                st.error(f"Erro inesperado: {exc}")


# ============================================================
# UI — Footer (vindo do template HTML)
# ============================================================
inject(render_template("footer", ano=datetime.now().year))
