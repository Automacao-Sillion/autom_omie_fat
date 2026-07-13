"""
Conferência de RFs (fluxo VALE) — Front Streamlit (Sillion)

Responsabilidades:
1. Extrair a coluna "RF" do arquivo enviado (xlsx / xlsb / csv, cabeçalho na linha 1).
2. Consultar o webhook N8N de conferência com a lista de RFs e receber os já
   cadastrados no banco de dados (com a referência de onde estão no banco).
3. Gerar, quando necessário, um arquivo filtrado SEM as linhas dos RFs que o
   usuário optou por não reenviar — preservando o mesmo formato/colunas do
   arquivo original, para não quebrar a esteira existente no N8N.

Contrato do webhook de consulta (N8N):
  Request  (POST JSON): {"tipo_faturamento": "VALE", "rfs": ["6203134747", ...]}
  Response (JSON) — qualquer um dos formatos abaixo é aceito:
    a) {"existentes": [{"rf": "6203134747", "linha": 123}, ...]}
    b) [{"rf": "6203134747", "linha": 123}, ...]
    c) ["6203134747", ...]                       (sem a referência de linha)
  Chaves aceitas para o RF:    rf, RF, numero_rf
  Chaves aceitas para a linha: linha, linha_banco, row, registro, id
"""

import io
from datetime import datetime

import requests

RF_COLUNA = "RF"
TIMEOUT_CONSULTA = 60  # segundos


class ArquivoMemoria:
    """Imita a interface do UploadedFile do Streamlit (name + getvalue)."""

    def __init__(self, name: str, conteudo: bytes):
        self.name = name
        self._conteudo = conteudo

    def getvalue(self) -> bytes:
        return self._conteudo


# ============================================================
# Normalização
# ============================================================
def normalizar_rf(valor) -> str:
    """
    Converte o RF para string canônica para comparação:
    remove espaços e sufixo '.0' de floats vindos do Excel.
    Retorna "" para valores vazios/None.
    """
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    texto = str(valor).strip()
    if texto.endswith(".0"):
        try:
            texto = str(int(float(texto)))
        except ValueError:
            pass
    return texto


def _ext(nome: str) -> str:
    return nome.rsplit(".", 1)[-1].lower() if "." in nome else ""


# ============================================================
# 1) Extração dos RFs
# ============================================================
def extrair_rfs(nome_arquivo: str, conteudo: bytes) -> list:
    """
    Lê o arquivo e retorna [{"linha": <nº da linha no arquivo>, "rf": <str>}].
    A linha é a linha real da planilha (cabeçalho = 1, dados a partir da 2).
    Linhas com RF vazio são ignoradas na conferência (mas permanecem no arquivo).
    Levanta ValueError se a coluna "RF" não existir.
    """
    ext = _ext(nome_arquivo)
    if ext == "xlsx":
        return _extrair_xlsx(conteudo)
    if ext == "xlsb":
        return _extrair_xlsb(conteudo)
    if ext == "csv":
        return _extrair_csv(conteudo)
    raise ValueError(f"Extensão não suportada para conferência: .{ext}")


def _indice_coluna_rf(cabecalho) -> int:
    for i, nome in enumerate(cabecalho):
        if nome is not None and str(nome).strip().upper() == RF_COLUNA:
            return i
    raise ValueError(
        f'Coluna "{RF_COLUNA}" não encontrada no cabeçalho (linha 1) do arquivo.'
    )


def _extrair_xlsx(conteudo: bytes) -> list:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    linhas = ws.iter_rows(values_only=True)
    cabecalho = next(linhas, None)
    if cabecalho is None:
        raise ValueError("Arquivo vazio.")
    idx = _indice_coluna_rf(cabecalho)

    resultado = []
    for n, row in enumerate(linhas, start=2):
        rf = normalizar_rf(row[idx] if idx < len(row) else None)
        if rf:
            resultado.append({"linha": n, "rf": rf})
    wb.close()
    return resultado


def _extrair_xlsb(conteudo: bytes) -> list:
    from pyxlsb import open_workbook

    with open_workbook(io.BytesIO(conteudo)) as wb:
        with wb.get_sheet(1) as ws:
            resultado = []
            idx = None
            for row in ws.rows():
                valores = [c.v for c in row]
                num_linha = row[0].r + 1 if row else 0  # pyxlsb: r é 0-based
                if idx is None:
                    idx = _indice_coluna_rf(valores)
                    continue
                rf = normalizar_rf(valores[idx] if idx < len(valores) else None)
                if rf:
                    resultado.append({"linha": num_linha, "rf": rf})
    return resultado


def _decodificar_csv(conteudo: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return conteudo.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Não foi possível decodificar o CSV.")


def _detectar_separador(linha_cabecalho: str) -> str:
    candidatos = [";", ",", "\t", "|"]
    return max(candidatos, key=lambda s: linha_cabecalho.count(s))


def _extrair_csv(conteudo: bytes) -> list:
    import csv as csv_mod

    texto = _decodificar_csv(conteudo)
    primeira_linha = texto.splitlines()[0] if texto.splitlines() else ""
    sep = _detectar_separador(primeira_linha)

    leitor = csv_mod.reader(io.StringIO(texto), delimiter=sep)
    cabecalho = next(leitor, None)
    if cabecalho is None:
        raise ValueError("Arquivo vazio.")
    idx = _indice_coluna_rf(cabecalho)

    resultado = []
    for n, row in enumerate(leitor, start=2):
        rf = normalizar_rf(row[idx] if idx < len(row) else None)
        if rf:
            resultado.append({"linha": n, "rf": rf})
    return resultado


# ============================================================
# 2) Consulta ao webhook N8N
# ============================================================
def consultar_rfs(url: str, rfs: list, tipo_faturamento: str = "VALE") -> dict:
    """
    Envia a lista de RFs ao N8N e retorna {rf_normalizado: referência_no_banco}.
    A referência é a linha/registro informado pelo N8N (ou "-" se não vier).
    Levanta requests.RequestException em falha de rede e ValueError em
    resposta inesperada.
    """
    resp = requests.post(
        url,
        json={"tipo_faturamento": tipo_faturamento, "rfs": rfs},
        timeout=TIMEOUT_CONSULTA,
        headers={"Content-Type": "application/json"},
    )
    resp.raise_for_status()

    try:
        dados = resp.json()
    except ValueError:
        raise ValueError(f"Resposta do webhook não é JSON: {resp.text[:300]}")

    if isinstance(dados, dict):
        dados = dados.get("existentes", dados.get("data", []))
    if dados is None:
        dados = []
    if not isinstance(dados, list):
        raise ValueError(f"Formato de resposta inesperado do webhook: {type(dados)}")

    existentes = {}
    for item in dados:
        if isinstance(item, dict):
            rf = item.get("rf", item.get("RF", item.get("numero_rf")))
            ref = item.get(
                "linha",
                item.get("linha_banco", item.get("row", item.get("registro", item.get("id", "-")))),
            )
        else:
            rf, ref = item, "-"
        rf = normalizar_rf(rf)
        if rf:
            existentes[rf] = ref if ref is not None else "-"
    return existentes


# ============================================================
# 3) Arquivo filtrado (remove linhas de RFs não selecionados)
# ============================================================
def gerar_arquivo_filtrado(nome_arquivo: str, conteudo: bytes, linhas_remover: set):
    """
    Retorna um ArquivoMemoria sem as linhas indicadas (números de linha reais
    da planilha, cabeçalho = 1). Preserva o formato original:
      - xlsx → xlsx (openpyxl.delete_rows, mantém estilos/colunas)
      - csv  → csv  (remove as linhas do texto original)
      - xlsb → convertido para xlsx (xlsb não pode ser gravado; o conteúdo e
               as colunas são preservados)
    Se não houver linhas a remover, retorna o arquivo original intacto.
    """
    if not linhas_remover:
        return ArquivoMemoria(nome_arquivo, conteudo)

    ext = _ext(nome_arquivo)
    if ext == "xlsx":
        return ArquivoMemoria(nome_arquivo, _filtrar_xlsx(conteudo, linhas_remover))
    if ext == "csv":
        return ArquivoMemoria(nome_arquivo, _filtrar_csv(conteudo, linhas_remover))
    if ext == "xlsb":
        novo_nome = nome_arquivo.rsplit(".", 1)[0] + ".xlsx"
        return ArquivoMemoria(novo_nome, _xlsb_para_xlsx_filtrado(conteudo, linhas_remover))
    raise ValueError(f"Extensão não suportada para filtro: .{ext}")


def _filtrar_xlsx(conteudo: bytes, linhas_remover: set) -> bytes:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(conteudo))
    ws = wb[wb.sheetnames[0]]
    # Remove de baixo para cima para não deslocar os índices
    for n in sorted(linhas_remover, reverse=True):
        ws.delete_rows(n)
    saida = io.BytesIO()
    wb.save(saida)
    return saida.getvalue()


def _filtrar_csv(conteudo: bytes, linhas_remover: set) -> bytes:
    texto = _decodificar_csv(conteudo)
    fim_linha = "\r\n" if "\r\n" in texto else "\n"
    linhas = texto.splitlines()
    mantidas = [l for i, l in enumerate(linhas, start=1) if i not in linhas_remover]
    return fim_linha.join(mantidas).encode("utf-8")


def _xlsb_para_xlsx_filtrado(conteudo: bytes, linhas_remover: set) -> bytes:
    import openpyxl
    from pyxlsb import open_workbook, convert_date

    novo = openpyxl.Workbook()
    ws_novo = novo.active
    with open_workbook(io.BytesIO(conteudo)) as wb:
        ws_novo.title = wb.sheets[0]
        with wb.get_sheet(1) as ws:
            for row in ws.rows():
                num_linha = row[0].r + 1 if row else 0
                if num_linha in linhas_remover:
                    continue
                ws_novo.append([c.v for c in row])
    saida = io.BytesIO()
    novo.save(saida)
    return saida.getvalue()


# ============================================================
# Orquestração (usada pelo app.py)
# ============================================================
def conferir(nome_arquivo: str, conteudo: bytes, url_consulta: str,
             tipo_faturamento: str = "VALE") -> dict:
    """
    Executa extração + consulta e devolve:
    {
      "rfs":        [{"linha": n, "rf": str}],          # todos os RFs do arquivo
      "duplicados": [{"linha": n, "rf": str, "ref_banco": ...}],
      "novos":      [{"linha": n, "rf": str}],
      "consultado_em": datetime,
    }
    """
    rfs = extrair_rfs(nome_arquivo, conteudo)
    existentes = consultar_rfs(url_consulta, [r["rf"] for r in rfs], tipo_faturamento)

    duplicados, novos = [], []
    for r in rfs:
        if r["rf"] in existentes:
            duplicados.append({**r, "ref_banco": existentes[r["rf"]]})
        else:
            novos.append(r)

    return {
        "rfs": rfs,
        "duplicados": duplicados,
        "novos": novos,
        "consultado_em": datetime.now(),
    }
