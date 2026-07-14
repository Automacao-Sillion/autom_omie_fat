# Contexto — Conferência de RFs (fluxo VALE) · FrontWebFatOmie

> Documento de handoff para continuar o trabalho em outro chat.
> Data: 13/07/2026 · Autor da sessão: Claude + Willian Ramos (willian.silva@sillion.com.br)

## O projeto

- **Pasta:** `Projetos\autom_Fat_omie\FrontWebFatOmie`
- **App publicado:** https://faturamento-os.streamlit.app/ ("Sillion · Envio de faturamento")
- **Função:** front Streamlit que envia arquivo de faturamento (xlsx/xlsb/csv) + email + empresa (Sitrack/Sillion) + tipo (TOT/VALE) ao backend **N8N** via POST JSON com o arquivo em **Base64**.
- Não confundir com `FrontWebNFomie` (outra pasta, app de Download de NFSe/XML/Boleto — mesmo template visual, outro produto).

## O que foi implementado nesta sessão

Nova funcionalidade: **conferência de RFs duplicados**, ativa **somente quando o usuário seleciona a tag VALE após o upload**, antes do envio.

### Arquivos alterados/criados

| Arquivo | Mudança |
|---|---|
| `conferencia_rf.py` | **NOVO** — extração da coluna RF, consulta ao webhook N8N, geração de arquivo filtrado |
| `app.py` | Seção "Conferência de RFs" + bloqueios de envio + arquivo filtrado no envio |
| `requirements.txt` | + `pandas`, `openpyxl`, `pyxlsb` |
| `.streamlit/secrets.toml` | + chave comentada `N8N_WEBHOOK_CONSULTA_RF_URL` (falta preencher) |
| `README.md` | Seção "Conferência de RFs (fluxo VALE)" com o contrato do webhook |

### Comportamento

1. Upload + tag **VALE** → o front lê a coluna **RF** (cabeçalho na linha 1, 1ª aba) e consulta o webhook de conferência com a lista de RFs.
2. **Nenhum repetido** → mensagem de sucesso; arquivo original enviado **intacto** (byte a byte).
3. **Com repetidos** → lista com rolagem (`st.data_editor`, altura máx. 320px) mostrando: checkbox **Reenviar**, RF, linha no arquivo, registro no banco. Botões **Marcar todos / Desmarcar todos** (seleção em lote). Default: desmarcado.
4. As linhas dos RFs **não marcados** são removidas do arquivo no momento do envio. RFs novos sempre vão.
5. **Payload N8N inalterado** (não quebrar a esteira existente): `{email, empresa_select, filename, file_base64, mime_type, tipo_faturamento}`.
6. Envio VALE fica **bloqueado** se: consulta falhar, chave não configurada, coluna RF ausente/vazia, ou tudo duplicado sem nada marcado.
7. TOT não é afetado em nada.
8. Consulta **sem cache** (14/07/2026): sempre ao vivo, a cada rerun do Streamlit. O cache de 5 min original causava resultado defasado ao reenviar o mesmo arquivo logo após um envio (RFs recém-gravados não apareciam como duplicados) e foi removido a pedido do Willian — prioridade é ser dinâmico.

### Decisões tomadas com o usuário

- Banco de dados: **já existe**; o front **só consulta** via **webhook N8N** (sem credenciais no Streamlit).
- **Quem grava os RFs novos no banco é o N8N**, após o envio (Willian vai adaptar o fluxo atual de popular o banco). O front não escreve nada.
- Arquivo enviado = filtrado (sem as linhas não marcadas), mesmo formato/colunas.
- Caveat aceito: `.xlsb` filtrado é reenviado como `.xlsx` (formato binário não permite gravação); `.xlsx` e `.csv` mantêm o formato.

## Contrato do webhook de consulta (a criar no N8N)

```jsonc
// Request (POST, Content-Type: application/json, timeout 60s)
{ "tipo_faturamento": "VALE", "rfs": ["6203134747", "6203134749"] }

// Response — RFs que JÁ existem no banco (lista vazia se nenhum)
{ "existentes": [ { "rf": "6203134747", "linha": 123 } ] }
```

O parser também aceita: lista direta `[{"rf":..., "linha":...}]` ou lista simples `["123", ...]`.
Chaves aceitas para RF: `rf`, `RF`, `numero_rf`. Para a referência: `linha`, `linha_banco`, `row`, `registro`, `id`.
RFs são comparados como string normalizada (sem `.0`, sem espaços).

## Planilha de referência (VALE)

`RFs a Faturar 07-07-2026-10h11.xlsx` — aba única "RFs a Faturar", 21 colunas, cabeçalho linha 1, coluna **RF** = 13ª (M), RFs numéricos (ex.: 6203134747), dados a partir da linha 2.

## Testes já realizados (todos passaram)

Extração dos 57 RFs; filtro removendo 3 duplicados simulados (55 linhas restantes, cabeçalho/colunas idênticos, RFs corretos); sem remoção → arquivo original byte a byte; parser dos 3 formatos de resposta; `py_compile` de `app.py` e `conferencia_rf.py` OK (Streamlit 1.59, `st.data_editor`/`column_config` disponíveis).

## Fluxos N8N prontos para importar (13/07/2026)

Pasta `n8n/`: `VALE_Consulta_RFs.json` (webhook de conferência) e `VALE_Gravar_RFs.json` (gravação pós-envio), + `README_n8n.md` com instruções de importação, `CREATE TABLE` sugerido (`rfs_faturados`, UNIQUE em `rf+tipo_faturamento`) e as duas opções de ligação com a esteira VALE. Os fluxos VALE/TOT_&_VALE existentes estão com acesso MCP desabilitado no n8n — por isso a adaptação foi entregue como fluxo separado (plugar com 1 nó HTTP Request no fim da esteira, ou colar os nós). Tabela/colunas são constantes no topo dos nós Code; credencial MySQL precisa ser selecionada manualmente após importar.

## Pendências

- [ ] **Willian:** importar os 2 JSONs da pasta `n8n/` no N8N, selecionar a credencial MySQL, ajustar `TABELA`/`COL_*` se o banco real tiver outro nome, e ativar.
- [ ] **Willian:** preencher `N8N_WEBHOOK_CONSULTA_RF_URL` no `secrets.toml` local **e** nos Secrets do Streamlit Cloud (URL de produção do webhook `consulta-rf`).
- [ ] **Willian:** plugar o `gravar-rf` no fim da esteira VALE (Opção A do `n8n/README_n8n.md`: 1 nó HTTP Request com o payload original).
- [ ] Testar ponta a ponta com o webhook real.
- [ ] Commit/push para o GitHub → redeploy no Streamlit Cloud (o `requirements.txt` mudou — o Cloud reinstala sozinho).
- [ ] (Se a esteira VALE receber `.xlsb`) decidir tratamento do caveat xlsb→xlsx no filtro.

## Nota operacional

A pasta é sincronizada pelo OneDrive; o shell da sessão pode enxergar cópias defasadas dos arquivos recém-editados (usar as ferramentas de leitura/edição diretas, ou aguardar sync, ao validar).
