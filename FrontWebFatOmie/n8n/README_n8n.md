# Fluxos N8N — Conferência de RFs (VALE)

Dois workflows prontos para importar no n8n (menu **⋯ → Import from file**):

| Arquivo | Função |
|---|---|
| `VALE_Consulta_RFs.json` | Webhook que o **front Streamlit** chama antes do envio. Recebe a lista de RFs e devolve os que já existem no banco. |
| `VALE_Gravar_RFs.json` | Grava os RFs novos no banco **depois** do envio — é a adaptação da esteira VALE. |

Ambos usam a **mesma normalização de RF do front** (string, sem espaços, sem sufixo `.0`), então a comparação é consistente ponta a ponta.

## 1. Banco de dados

Os fluxos vêm configurados para a tabela abaixo. Se o seu banco de RFs já existir com outro nome/colunas, **não precisa criar nada** — basta ajustar as constantes `TABELA` / `COL_*` no topo dos nós Code ("Normalizar RFs e montar SQL" e "Montar INSERT").

```sql
CREATE TABLE IF NOT EXISTS rfs_faturados (
  rf VARCHAR(32) NOT NULL,
  PRIMARY KEY (rf)
);
```

> Esquema mínimo, por decisão do projeto: **só a coluna `rf`, que é o próprio identificador único** (PRIMARY KEY). É essa chave que faz o `INSERT IGNORE` do fluxo de gravação nunca duplicar registros. Consequências: a coluna "registro no banco" no front exibe o próprio RF, e os RFs valem para todos os tipos (hoje só o VALE consulta).

## 2. Após importar (os dois fluxos)

1. Abrir cada nó **MySQL** ("Consultar banco" / "Gravar no banco") e **selecionar a credencial** do banco de faturamento (os JSONs não trazem credencial de propósito).
2. Conferir/ajustar as constantes `TABELA`, `COL_RF` etc. nos nós Code.
3. **Ativar** o workflow (a URL de produção `…/webhook/<path>` só funciona com o fluxo ativo).

## 3. VALE_Consulta_RFs — ligação com o front

- Path do webhook: `POST /webhook/consulta-rf`
- Copiar a **Production URL** do nó "Webhook Consulta RF" e preencher em:
  - `.streamlit/secrets.toml` local → `N8N_WEBHOOK_CONSULTA_RF_URL = "https://…/webhook/consulta-rf"`
  - **Secrets do Streamlit Cloud** (mesma chave).

Contrato (o front já fala exatamente isso):

```jsonc
// Request
{ "tipo_faturamento": "VALE", "rfs": ["6203134747", "6203134749"] }
// Response
{ "existentes": [ { "rf": "6203134747", "linha": 123 } ] }
```

`linha` é a referência "registro no banco" exibida na tela — com o esquema mínimo (tabela só com `rf`), ela devolve o próprio RF. Lista de RFs vazia responde `{"existentes": []}` sem tocar no banco.

Teste rápido:

```bash
curl -X POST https://SEU-N8N/webhook/consulta-rf \
  -H "Content-Type: application/json" \
  -d '{"tipo_faturamento":"VALE","rfs":["6203134747"]}'
```

## 4. VALE_Gravar_RFs — ligação com a esteira

O fluxo recebe **o mesmo payload que o front já envia** (`{email, empresa_select, filename, file_base64, mime_type, tipo_faturamento}`), extrai a coluna **RF** do arquivo (xlsx ou csv, 1ª aba, cabeçalho na linha 1) e faz um único `INSERT IGNORE INTO rfs_faturados (rf) VALUES …` com todos os RFs, sem duplicar (o `rf` é PRIMARY KEY).

Duas formas de plugar na esteira VALE (escolha uma):

- **Opção A (recomendada — 1 nó só):** no final do fluxo VALE atual, depois que o envio deu certo, adicionar um nó **HTTP Request** → `POST https://SEU-N8N/webhook/gravar-rf`, body JSON = o payload original recebido pelo webhook da esteira (ex.: `{{ $('Webhook').item.json.body }}`). O webhook responde na hora (fire-and-forget) e a gravação roda em paralelo.
- **Opção B (colar nós):** copiar os nós "Preparar binario" → … → "Gravar no banco" para dentro do fluxo VALE e conectar "Preparar binario" no ponto onde o payload do front está disponível. O nó "Montar INSERT" referencia `$('Preparar binario')`, então o conjunto funciona colado em qualquer fluxo, desde que os nomes dos nós sejam mantidos.

Observações:

- Como o front **remove do arquivo** as linhas dos RFs duplicados não marcados, tudo que chega aqui é RF novo (ou reenvio deliberado — o `INSERT IGNORE` só ignora o que já existe).
- `.xlsb` nunca chega: o front converte para `.xlsx` ao filtrar; sem filtro, a esteira VALE segue recebendo o arquivo original — **se** a esteira puder receber `.xlsb` sem filtro, o nó "Extrair XLSX" não o lê (caveat já registrado no contexto do projeto).
- CSV: o nó "Extrair CSV" usa o delimitador padrão (`,`). Se os CSVs da VALE usarem `;`, definir a opção *Delimiter* no nó.

## 5. Ordem de teste ponta a ponta

1. Criar tabela (ou ajustar constantes) e importar/ativar os dois fluxos.
2. `curl` no `consulta-rf` com RFs inexistentes → `{"existentes": []}`.
3. Enviar um arquivo VALE pelo front → esteira roda → `gravar-rf` grava os RFs.
4. Reenviar o **mesmo** arquivo → o front deve listar todos como duplicados, com a referência do banco.
