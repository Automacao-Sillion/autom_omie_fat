# Sillion · Envio de faturamento

Front-end em **Streamlit** para envio de arquivos de faturamento (xlsx / xlsb / csv) ao backend de processamento em **N8N**. O arquivo é codificado em **Base64** e transmitido em um POST JSON. Após o processamento, o relatório final é enviado por email ao usuário.

> Projeto interno da Sillion. Acesso restrito ao domínio `@sillion.com.br`.

---

## Sumário

- [Visão geral](#visão-geral)
- [Como funciona o fluxo](#como-funciona-o-fluxo)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Stack e dependências](#stack-e-dependências)
- [Configuração inicial](#configuração-inicial)
- [Rodar localmente](#rodar-localmente)
- [Deploy no Streamlit Community Cloud](#deploy-no-streamlit-community-cloud)
- [Contrato com o N8N (payload)](#contrato-com-o-n8n-payload)
- [Customização visual](#customização-visual)
- [Troubleshooting](#troubleshooting)
- [Roadmap / próximos passos](#roadmap--próximos-passos)

---

## Visão geral

A Sillion possui um backend de processamento de faturamento construído no N8N. Este projeto é a **camada de front-end** que permite a colaboradores enviarem seus arquivos sem precisar acessar o N8N diretamente.

**Decisões de design:**

- **Streamlit** como framework de UI — permite escrever em Python puro com componentes prontos (upload, dialog, spinner) e fica simples de hospedar.
- **Arquitetura híbrida** — widgets interativos via Streamlit, estrutura visual em HTML/CSS separados em arquivos próprios para facilitar manutenção.
- **URL do webhook em `st.secrets`** — não fica exposta no código.
- **Validação de domínio corporativo** — apenas emails `@sillion.com.br` são aceitos.

---

## Como funciona o fluxo

```
┌─────────────┐     ┌──────────────┐     ┌──────────┐     ┌────────────┐
│   Usuário   │ ──→ │  Streamlit   │ ──→ │   N8N    │ ──→ │   Email    │
│ (navegador) │     │  (front-end) │     │ (back)   │     │ (relatório)│
└─────────────┘     └──────────────┘     └──────────┘     └────────────┘
```

1. Colaborador acessa o app.
2. Informa email corporativo e seleciona o arquivo de faturamento.
3. Ao clicar em **Enviar arquivo**:
   - Email é validado contra o domínio `@sillion.com.br`.
   - Arquivo é lido em bytes e convertido para Base64.
   - Streamlit faz um `POST` JSON ao webhook do N8N.
4. Pop-up confirma que o relatório retornará por email.
5. O N8N processa o arquivo e envia o relatório final ao email informado.

---

## Estrutura do projeto

```
FrontWebOmie/
│
├── app.py                      # Entry point — lógica Python e widgets
├── requirements.txt            # Dependências (streamlit, requests)
├── README.md                   # Este arquivo
├── .gitignore                  # Padrões a serem ignorados pelo Git
│
├── styles/
│   └── main.css                # Tema completo (variáveis CSS + componentes)
│
├── templates/                  # Fragmentos HTML estruturais
│   ├── meta.html               # Meta tags (notranslate)
│   ├── header.html             # Navbar com logo + breadcrumb
│   ├── hero.html               # Título + subtítulo
│   ├── file_preview.html       # Cartão exibido ao selecionar arquivo
│   └── footer.html             # Rodapé navy com copyright
│
├── static/                     # Arquivos servidos diretamente ao navegador
│   ├── README.md               # Instruções de uso da pasta
│   └── logo-sillion.svg        # (opcional) Logo local
│
└── .streamlit/
    ├── config.toml             # Tema do Streamlit + maxUploadSize
    └── secrets.toml            # URL do webhook N8N — NÃO COMMITAR
```

### Por que essa separação?

- **`app.py`** contém apenas lógica Python e os widgets que precisam de interação com Python (`st.text_input`, `st.file_uploader`, `st.button`, `st.dialog`).
- **`styles/main.css`** centraliza toda a aparência. Trocar de tema é mudar uma variável.
- **`templates/`** mantém o HTML "estrutural" (navbar, hero, footer) longe do código Python. Cada template usa placeholders `{{nome_variavel}}` substituídos no momento de injetar.
- **`static/`** é servida pelo Streamlit em `/app/static/` quando `enableStaticServing = true`. Ideal para imagens e arquivos referenciados em HTML.
- **`.streamlit/`** contém configurações sensíveis e ajustes do servidor.

---

## Stack e dependências

**Linguagem:** Python 3.9+
**Framework:** Streamlit ≥ 1.32
**HTTP client:** Requests ≥ 2.31

Arquivo `requirements.txt`:

```
streamlit>=1.32.0
requests>=2.31.0
```

Bibliotecas padrão usadas: `base64`, `re`, `mimetypes`, `pathlib`, `datetime`.

---

## Configuração inicial

### 1. Clonar o repositório

```bash
git clone https://github.com/<sua-org>/front-web-omie.git
cd front-web-omie
```

### 2. Criar virtualenv (recomendado)

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar secrets

Crie o arquivo `.streamlit/secrets.toml` com a URL do seu webhook N8N:

```toml
N8N_WEBHOOK_URL = "https://seu-n8n.app.n8n.cloud/webhook/<seu-id>"
```

> Este arquivo **não** é versionado (já está no `.gitignore`). Cada ambiente (local, staging, produção) tem o seu.

### 5. (Opcional) Baixar logo localmente

```bash
# Windows PowerShell:
Invoke-WebRequest -Uri "https://www.sillion.com.br/wp-content/themes/sillion/images/logo-black-tm.svg" -OutFile "static/logo-sillion.svg"

# Linux/Mac/Git Bash:
curl -o static/logo-sillion.svg "https://www.sillion.com.br/wp-content/themes/sillion/images/logo-black-tm.svg"
```

Se o arquivo não existir, o app automaticamente carrega a URL pública da Sillion como fallback.

---

## Rodar localmente

```bash
streamlit run app.py
```

O app abre em `http://localhost:8501`.

Streamlit recarrega automaticamente ao salvar mudanças no `app.py`. Para mudanças em CSS/HTML, basta dar refresh no navegador.

---

## Deploy no Streamlit Community Cloud

### Preparação

Certifique-se de que estes arquivos estão no repositório do GitHub (privado preferencialmente):

- `app.py`
- `requirements.txt`
- `README.md`
- `.gitignore`
- `styles/main.css`
- `templates/*.html`
- `.streamlit/config.toml`

E **garanta** que `.streamlit/secrets.toml` está no `.gitignore` (não pode subir).

### Subir para o GitHub

```bash
git init
git branch -M main

# VERIFICAÇÃO CRÍTICA antes de adicionar
git status
git check-ignore -v .streamlit/secrets.toml

git add .
git commit -m "feat: front Streamlit para envio de faturamento"

git remote add origin https://github.com/<sua-org>/front-web-omie.git
git push -u origin main
```

### Criar o app no Streamlit Cloud

1. Acesse [share.streamlit.io](https://share.streamlit.io).
2. **New app** → escolha o repositório, branch `main`, arquivo principal `app.py`.
3. Antes do deploy, vá em **Advanced settings → Secrets** e cole:

```toml
N8N_WEBHOOK_URL = "https://seu-n8n.app.n8n.cloud/webhook/<seu-id>"
```

4. Clique em **Deploy**. Em poucos minutos seu app estará no ar.

---

## Contrato com o N8N (payload)

O Streamlit envia um `POST` JSON com o seguinte formato:

```json
{
  "email": "willian.silva@sillion.com.br",
  "filename": "faturamento_mai_2026.xlsx",
  "file_base64": "UEsDBBQABgAIAAAAIQ...",
  "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "tipo_faturamento": "TOT"
}
```

| Campo              | Tipo   | Descrição                                                    |
|--------------------|--------|--------------------------------------------------------------|
| `email`            | string | Email corporativo do remetente (já validado)                 |
| `filename`         | string | Nome original do arquivo                                     |
| `file_base64`      | string | Conteúdo do arquivo codificado em Base64                     |
| `mime_type`        | string | Tipo MIME (útil para reconstruir o arquivo no N8N)           |
| `tipo_faturamento` | string | Esteira de processamento — valores aceitos: `TOT` ou `VALE`  |

### Como consumir no N8N

No nó **Webhook** (POST), os campos ficam em `$json`:

- `{{ $json.email }}`
- `{{ $json.filename }}`
- `{{ $json.file_base64 }}`
- `{{ $json.mime_type }}`
- `{{ $json.tipo_faturamento }}` (útil para rotear a esteira correta com um nó **Switch**)

Para reconstruir o arquivo a partir do Base64, use o nó **Move Binary Data** ou uma expressão em Code/Function:

```javascript
const buffer = Buffer.from($json.file_base64, 'base64');
return [{
  binary: {
    data: {
      data: buffer,
      mimeType: $json.mime_type,
      fileName: $json.filename
    }
  },
  json: { email: $json.email }
}];
```

---

## Customização visual

### Trocar a paleta de cores

Toda a paleta está em variáveis CSS no topo de `styles/main.css`:

```css
:root {
    --cor-primaria:       #0F2A33;  /* navy escuro */
    --cor-primaria-hover: #1B3D48;
    --cor-acento:         #4FB7B8;  /* ciano */
    --cor-link:           #2680C2;
    --cor-texto:          #1A2D38;
    --cor-texto-muted:    #5A6B78;
    --cor-fundo:          #FFFFFF;
    --cor-fundo-sutil:    #F3F5F7;
    --cor-fundo-card:     #E7F1F4;
    --cor-borda:          #D4DCE0;
}
```

Também atualize o tema do Streamlit em `.streamlit/config.toml`:

```toml
[theme]
primaryColor = "#0F2A33"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F3F5F7"
textColor = "#1A2D38"
```

### Trocar textos

- **Título e subtítulo:** parâmetros `titulo` e `subtitulo` no `inject(render_template("hero", ...))` em `app.py`.
- **Navbar e breadcrumb:** edite `templates/header.html`.
- **Rodapé:** edite `templates/footer.html`.

### Trocar logo

- Substitua o arquivo `static/logo-sillion.svg`.
- Se o logo já estiver em branco, remova o filtro de `app-navbar .brand-logo` em `main.css`.

### Permitir outros domínios de email

Em `app.py`, troque:

```python
DOMINIO_PERMITIDO = "sillion.com.br"
```

Para aceitar múltiplos domínios, ajuste a regex manualmente — exemplo:

```python
EMAIL_REGEX = re.compile(
    r"^[A-Za-z0-9._%+\-]+@(sillion\.com\.br|sitrack\.com\.br)$",
    re.IGNORECASE,
)
```

### Aceitar outros tipos de arquivo

Em `app.py`:

```python
TIPOS_ACEITOS = ["xlsx", "xlsb", "csv", "pdf"]  # adicione extensões
```

E adicione o MIME correspondente em `MIME_FALLBACK` se não for detectado automaticamente.

---

## Troubleshooting

### "A URL do webhook N8N não foi configurada"
Falta o arquivo `.streamlit/secrets.toml` (local) ou os Secrets no painel do Streamlit Cloud. Veja a seção [Configuração inicial](#configuração-inicial).

### Logo aparece como ícone de imagem quebrada
- O arquivo `static/logo-sillion.svg` não existe **e** a URL externa não está acessível.
- Solução: baixe o SVG manualmente (instruções em [Configuração inicial](#configuração-inicial)) ou aguarde acesso à internet.

### Botões com texto invisível ou ícones aparecendo como palavras
- Causa quase sempre: **Google Translate ativo** na página, que injeta `<font>` quebrando ícones Material.
- Solução: desativar tradução para este site (clique no ícone de tradução do Chrome → "Nunca traduzir este site"), ou abrir em aba anônima.

### "Failed to fetch" ou timeout ao clicar em Enviar
- N8N está fora do ar, URL incorreta ou requisição passou de 120s.
- Verifique no painel do N8N se o webhook está ativo. Aumente `TIMEOUT_REQ` em `app.py` se precisar.

### Email rejeitado mesmo sendo @sillion.com.br
- Verifique se há espaços em branco no email.
- Confirme em `app.py` se `DOMINIO_PERMITIDO = "sillion.com.br"`.

---

## Roadmap / próximos passos

- [ ] Adicionar autenticação (Streamlit `st.login` ou OAuth via Google Workspace).
- [ ] Persistir histórico de envios em planilha ou banco (Google Sheets, Supabase).
- [ ] Aceitar múltiplos arquivos em um único envio.
- [ ] Mostrar progresso real do processamento no N8N (polling do status).
- [x] ~~Adicionar campo de "tipo de faturamento" (dropdown TOT/VALE) para o N8N rotear a esteira correta.~~ ✓ implementado
- [ ] Logar tentativas inválidas (anti-abuso, monitoramento).

---

## Licença

Uso interno da Sillion. Não distribuir externamente.

---

**Mantenedor:** Willian Ramos Silva — `willian.silva@sillion.com.br`
