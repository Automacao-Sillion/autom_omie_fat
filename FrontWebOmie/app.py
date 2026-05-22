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

# ============================================================
# Caminhos
# ============================================================
BASE_DIR = Path(__file__).parent
CSS_PATH = BASE_DIR / "styles" / "main.css"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# ============================================================
# Recursos externos
# ============================================================
LOGO_EXTERNO = "https://www.sillion.com.br/wp-content/themes/sillion/images/logo-black-tm.svg"
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
    page_icon="",
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


# ============================================================
# Configuração segura: URL do webhook
# ============================================================
try:
    WEBHOOK_URL = st.secrets["N8N_WEBHOOK_URL"]
except (KeyError, FileNotFoundError):
    WEBHOOK_URL = None


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
        "⚠️ A URL do webhook N8N não foi configurada. "
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

empresa_select = st.selectbox(
    "Selecione a empresa",
    options=EMPRESAS,
    index=None,
    placeholder="Selecione a empresa...",
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

    if erros:
        for e in erros:
            st.error(e)
    else:
        with st.spinner("Enviando arquivo para processamento..."):
            try:
                payload = montar_payload(
                    email=email,
                    empresa_select=empresa_select,
                    arquivo=arquivo,
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
