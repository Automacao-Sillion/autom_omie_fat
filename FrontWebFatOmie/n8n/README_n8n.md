# Fluxos N8N — Conferência de RFs (VALE)

Workflows prontos para importar no n8n (menu **⋯ → Import from file**):

| Arquivo | Função |
|---|---|
| `VALE_Consulta_RFs.json` | Webhook que o **front Streamlit** chama antes do envio. Recebe a lista de RFs e devolve os que já existem no banco. |
| `VALE_Gravar_RFs.json` | Grava os RFs novos no banco **depois** do envio — é a adaptação da esteira VALE. |
| `VALE_Sync_Status_RF_Nota.json` | **(10/08/2026)** Sincroniza o status das notas da Omie na listinha `rf_nota`. Ver `PLANO_BLOQUEIO_RF_NOTA.md` e a seção 6 abaixo. |
| `VALE_Consulta_RFs_v2.json` | **(10/08/2026)** Substitui o `VALE_Consulta_RFs`. Mesmo path e mesmo contrato, mas devolve **bloqueado / legado / novo** por RF. Seção 7 abaixo. |

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

---

# 6. VALE_Sync_Status_RF_Nota (10/08/2026)

Metade "status" do upgrade pedido pelo CFO (bloquear RF já vinculada a nota).
Contexto completo: `PLANO_BLOQUEIO_RF_NOTA.md`. Depende de `sql/01_cria_rf_nota.sql`.

**O que ele NÃO faz:** não cria vínculo RF→nota e não insere linha nenhuma. Ele só
**atualiza o status** de linhas que já existem em `rf_nota` (`WHERE nIdNf IN (...)`).
Quem cria vínculo é a esteira VALE (ainda pendente) ou o backfill.

## Nós

| Nó | Função |
|---|---|
| `Config` | `OMIE_APP_KEY`, `OMIE_APP_SECRET` e `DRY_RUN`. Único lugar a preencher. |
| `Lista_Status_Omie` | `ListarNFSEs` paginado, 300 ms entre páginas. **40 chamadas** para 3.919 notas. |
| `Dry_run?` | Desvia para o relatório (não grava) ou para a gravação. |
| `Resumo_DryRun` | Relata os códigos de `cStatusNFSe` encontrados e quais faltam mapear. |
| `Montar_UPDATEs` | Monta 1 `UPDATE` por lote de 500 notas (`CASE nIdNf WHEN…`), não 1 por linha. |
| `Gravar_Status` | MySQL `executeQuery`. **Selecionar a credencial manualmente** (o JSON não traz). |

## ✅ Vocabulário de status — RESOLVIDO (execução real de 10/08/2026)

O dry-run rodou em produção e respondeu a última incógnita do projeto:

```
3.919 notas lidas em 40 chamadas → vocabulario: { "C": 63, "F": 3856 }
```

| Código | Qtd | Significado |
|---|---|---|
| `F` | 3.856 | FATURADA |
| `C` | 63 | CANCELADA |

**Só existem esses dois códigos.** O `MAPA` do nó `Montar_UPDATEs` já vem completo.

**Não existe código para SUBSTITUÍDA.** Na Omie a substituição aparece como
cancelamento + nota nova. Detectar substituição = **o mesmo `rf` em duas linhas de
`rf_nota`** — que é exatamente o que a PK `(rf, nIdNf)` permite. Como os dois códigos
bloqueiam sob a regra do CFO, o status vira o **motivo exibido**, não a decisão.

**Correção da estimativa:** eu previa ~8 chamadas; foram **40**. A Omie limita a página a
~100 registros mesmo pedindo `nRegPorPagina: 500`. Continua barato (40 contra 3.919).

## Uma empresa só — e por que a Omie tem mais notas que a `NF`

**A Sitrack não usa RF** (confirmado com o Willian em 10/08/2026): RF é controle da Vale,
faturada pela Sillion. Então o fluxo roda com **uma app_key** e não há pendência de chave
da Sitrack. Contagem no banco: `sillion 3.871`, `sitrack 154`.

Sobre a diferença **3.919 (Omie) × 3.871 (`NF` sillion)** — é **esperado**, não é defasagem:
são as **canceladas**. O fluxo diário descarta `cStatusNFSe === 'C'` antes de inserir, então
boa parte das 63 canceladas **nunca entrou na `NF`**.

> Isso é justamente o motivo de a `rf_nota` guardar `nIdNf` direto e **não** ter FK para
> `NF`: um bloqueio que dependesse da `NF` teria buraco exatamente nas canceladas, que são
> o caso que o CFO quer barrar.

## Onde a tabela vive — atenção ao nome

A tabela é **`kvm4_db.rf_nota`**, no mesmo banco de `NF` e `rfs_faturados`.
**Não** existe `faturamento.rf_nota` — a credencial do n8n chamada *"MySQL faturamento"*
confunde, mas o schema é `kvm4_db`.

Por isso o `TABELA` do nó `Montar_UPDATEs` vem **qualificado com o banco**
(`kvm4_db.rf_nota`): assim o UPDATE funciona independente de qual schema a credencial
MySQL tenha como default. Um `rf_nota` solto quebraria com *table doesn't exist* se a
credencial apontar para outro banco.

## Ordem de uso (importante)

1. Rodar `sql/01_cria_rf_nota.sql` (já rodado em 10/08/2026 — tabela criada, 0 linhas).
2. Importar o fluxo e preencher **`OMIE_APP_KEY` / `OMIE_APP_SECRET`** no nó `Config`
   (as chaves estão no nó `Define_key_secret` do fluxo "Popula tabela NF & boleto").
3. Selecionar a credencial MySQL no nó `Gravar_Status`.
4. Executar com **`DRY_RUN = true`** (padrão). Nada é gravado.
5. Conferir `precisa_mapear` **vazio**.
6. **Só então** virar `DRY_RUN = false` no `Config`.

> ⚠️ Se aparecer código novo e você virar `DRY_RUN = false` sem mapear, ele é gravado como
> `FATURADA` e o nó grita no log (`CODIGO FORA DO MAPA`). O bloqueio continua correto —
> quem fica errado é o rótulo mostrado na tela.

## Decisões de consumo de API (risco de ban — regra do Willian)

- Status vem da **lista** (`ListarNFSEs`, ~8 chamadas), **nunca** do `ObterNFSe`
  (seria 1 chamada por nota, ~4.000, para o mesmo campo).
- Sem o filtro `APENAS_EMITIDAS` do fluxo diário: as canceladas são justamente 1 dos 3
  status a bloquear.
- Pausa de 300 ms entre páginas, chamadas em série. Nunca paralelizar.
- Este fluxo **não altera** o consumo do fluxo diário existente.

## Erro 500 da Omie — o que fazer

Aconteceu em 10/08/2026, num rerun poucos minutos depois de uma varredura completa:

```
"errorMessage": "Request failed with status code 500", "errorDescription": "AxiosError",
"errorDetails": {}
```

**A Omie devolve HTTP 500 com o motivo real no corpo** (`faultstring`), mas o n8n mostra só
o envelope e `errorDetails` vazio. Causas típicas: **consumo redundante** (repetir a mesma
requisição pouco depois), app_key/app_secret inválidos, ou instabilidade momentânea.

No caso de 10/08 era **transitório**: minutos depois o fluxo rodou completo. É o
comportamento clássico do bloqueio de consumo redundante liberando.

O nó `Lista_Status_Omie` foi endurecido para isso:

| Recurso | O que faz |
|---|---|
| `motivoOmie()` | Cava o `faultstring` nos vários lugares onde axios/n8n escondem o corpo e mostra na mensagem de erro. |
| Retry com espera crescente | 3 tentativas na mesma página, esperando 5 s → 15 s → 30 s. Não é insistência cega: é dar tempo de a Omie liberar. |
| Retorno **parcial** | Se morrer na página 30, **não joga fora** as 29 já lidas — devolve o parcial marcado (`parcial: true`, `proxima_pagina`) e o UPDATE aproveita. Reprocessar do zero é o consumo redundante que causou o erro. |
| `PAGINA_INICIAL` | Constante no topo do nó. Morreu na página 30? Ponha `30` e rode de novo — pula as 29 já lidas. |

O `Resumo_DryRun` mostra `varredura: "COMPLETA"` ou
`"PARCIAL - parou na pagina N de M. …"`, então parcial nunca passa por completo.

## Pegadinhas conhecidas

- **Ver quantas linhas foram afetadas:** o nó MySQL devolve só `success: true` em
  UPDATE. Ligar **"Output Query Execution Details"** no nó `Gravar_Status` e ler
  `$json.data.affectedRows`.
- **`affectedRows` = 0 é esperado no começo**, porque `rf_nota` nasce vazia. Não é bug:
  é a metade do RF que ainda não existe.
- SQL gerado: ~34 KB por lote de 500 notas — folgadíssimo no `max_allowed_packet`.
- O SQL não contém `$`, então não cai no bug do nó MySQL que corrompe cifrão em strings.

## Testes já realizados (10/08/2026)

- Sintaxe dos 3 nós Code validada com Node (`new Function` em contexto async).
- `Config.OMIE_CONTAS` valida como JSON, 2 empresas.
- **Dry-run real em produção:** 3.919 notas, 40 chamadas, vocabulário `{C:63, F:3856}`.
- Teste funcional reproduzindo o retorno real (3.919 notas, 63 `C` + 3.856 `F`, 2 empresas):
  8 lotes (500×7 + 419), soma conferindo com 3.919; `C → CANCELADA`; `F → FATURADA`;
  `precisa_mapear` vazio; nenhum aviso de código fora do mapa.
- Teste de regressão: injetando um código `X` inexistente, o alarme dispara
  (`CODIGO FORA DO MAPA, gravado como FATURADA: {"X":1}`).
- Teste anterior com `NULL`: status vazio preservado como `NULL`, sem virar string.
- SQL: ~34 KB por lote de 500, sem `$` (escapa do bug do nó MySQL com cifrão).
- `UPDATE` e `SELECT` de bloqueio validados com `EXPLAIN` contra a tabela real
  `kvm4_db.rf_nota` (parseiam e usam índice), sem alterar dado.
- **Tratamento do 500** (Omie mockada devolvendo `faultstring`): caminho completo ok;
  falha na página 3 devolve parcial com as 4 notas já lidas, `proxima_pagina: 3`,
  `faultstring` capturado e 3 tentativas registradas; falha na página 1 estoura com
  motivo legível; `Resumo_DryRun` mostra `PARCIAL`; `PAGINA_INICIAL = 3` pula as
  páginas 1 e 2.
- **Execução real em produção (10/08/2026):** rodou completo em `DRY_RUN = true` e também
  em `DRY_RUN = false`, sem erro. Credencial, nome qualificado `kvm4_db.rf_nota`, os 8
  lotes e o `executeQuery` todos ok.
- ⚠️ **O efeito do UPDATE ainda NÃO foi verificado**: a `rf_nota` está com **0 linhas**,
  então o `UPDATE` casou com nada (`status_nota` e `status_em` seguem nulos na tabela).
  Está provado que o fluxo **executa**; falta provar que o status **grava certo**.
  Ver "Teste de ponta a ponta pendente" abaixo.

## Teste de ponta a ponta pendente (status gravando de verdade)

Enquanto a esteira VALE não cria vínculo, dá para validar com 2 linhas falsas de RF
apontando para notas **reais**, rodar o fluxo e conferir o status. Escolher RF com prefixo
`TESTE` deixa a limpeza inequívoca.

```sql
-- 1) semear (nIdNf reais, colhidos da NF em 10/08/2026)
INSERT INTO kvm4_db.rf_nota (rf, nIdNf, cNumNFSe, cNumOs, emp, origem) VALUES
 ('TESTE0000000001', 2862955285, '0000000011669', '000000000005575', 'sillion', 'BACKFILL'),
 ('TESTE0000000002', 2862955288, '0000000011670', '000000000005576', 'sillion', 'BACKFILL');

-- 2) rodar o fluxo com DRY_RUN = false, depois conferir:
SELECT rf, nIdNf, cStatusNFSe, status_nota, status_em
FROM kvm4_db.rf_nota WHERE rf LIKE 'TESTE%';
--    esperado: cStatusNFSe = 'F', status_nota = 'FATURADA', status_em preenchido

-- 3) limpar
DELETE FROM kvm4_db.rf_nota WHERE rf LIKE 'TESTE%';
```

Para cobrir o caso que mais interessa ao CFO, incluir **uma nota cancelada**: pegar um
`nIdNf` com `cStatusNFSe: "C"` na saída do `Lista_Status_Omie` (o dry-run lista os 63) e
semear uma terceira linha — o esperado é `status_nota = 'CANCELADA'`.

---

# 7. VALE_Consulta_RFs_v2 (10/08/2026) — TESTADO EM PRODUÇÃO ✅

Substitui o `VALE_Consulta_RFs`. **Mesmo path `consulta-rf`, mesmo request** — o que muda é
que a resposta agora diz, por RF, se o envio **continua ou não**.

> ⚠️ Os dois fluxos usam o path `consulta-rf` e **não podem ficar ativos juntos**.
> Desative o antigo antes de ativar o v2.

## A regra que ele implementa

Sobe a planilha → analisa → devolve o que continua e o que não continua:

| Onde o RF está | Resposta | Resultado |
|---|---|---|
| em nenhuma tabela | **não volta na lista** | **NOVO** → continua |
| em `kvm4_db.rf_nota` | `bloqueado: true` + nota + status | **BLOQUEADO** → não continua |
| só em `kvm4_db.rfs_faturados` | `bloqueado: false, legado: true` + `enviado_em` | enviado antes sem gerar nota → continua com aviso |

Uma linha **por nota**: RF substituído volta em 2 linhas, ambas com `substituicao: true`.

## Retrocompatibilidade (deploy sem risco)

A chave `existentes` e o campo `linha` da resposta antiga foram **mantidos**. Dá para subir o
webhook v2 **antes** de mexer no front: o front atual continua funcionando, apenas tratando
os bloqueados como duplicados com checkbox (comportamento de hoje). Sem erro, sem tela branca.

O `linha` virou uma referência legível — `"NF 0000000099002 / CANCELADA"` ou
`"enviado em 2026-08-05 12:57:20 (sem nota)"` — que é o que o front antigo mostra na coluna
"Registro no banco".

## Teste executado em produção (10/08/2026)

Semeadas 4 linhas com RF prefixado `TESTE_` na `rf_nota` (nenhum RF real tocado), o webhook
foi chamado e as linhas removidas depois.

```bash
curl -s -X POST https://n8n.srv1776004.hstgr.cloud/webhook/consulta-rf \
  -H "Content-Type: application/json" \
  -d '{"tipo_faturamento":"VALE","rfs":["TESTE_FATURADA","TESTE_CANCELADA","TESTE_SUBSTIT","6203136190","0000000000"]}'
```

**Resultado: HTTP 200 em 195 ms, 1.247 bytes, resposta idêntica à prevista.**

```json
"resumo": { "bloqueados": 4, "rfs_bloqueados": 3, "legado": 1, "com_substituicao": 2 }
```

| Caso | RF | Voltou |
|---|---|---|
| bloqueio por nota faturada | `TESTE_FATURADA` | `bloqueado: true`, FATURADA, NF 0000000099001 |
| **bloqueio por cancelada** (o caso do CFO) | `TESTE_CANCELADA` | `bloqueado: true`, CANCELADA, NF 0000000099002 |
| substituição | `TESTE_SUBSTIT` | **2 linhas**, ambas `substituicao: true` |
| legado sem nota | `6203136190` | `bloqueado: false, legado: true` + data de envio |
| RF novo | `0000000000` | **não apareceu** |

Antes do curl, o mesmo SQL foi rodado direto no banco e devolveu as mesmas 5 linhas —
então divergência no curl aponta n8n (credencial, path, fluxo antigo ativo), não a lógica.

Também validado com `EXPLAIN` contra as tabelas reais: o `UNION` usa índice nos dois ramos
(`range` na PK) e o anti-join do ramo 2 resolve com `Not exists; Using index`.
Limpeza conferida: `rf_nota` voltou a 0 linhas.

---

# 8. VALE_Backfill_RF_Nota (10/08/2026) — vincula as notas JÁ existentes

Reconstrói o vínculo RF → nota das notas antigas, preenchendo a `kvm4_db.rf_nota`.
É o que faz o bloqueio valer para o passado, não só para o que for faturado de agora em diante.

## ✅ A descoberta que destravou isso

**O RF não está na nota. Está na Ordem de Serviço.**

O `ObterNFSe` (usado pelo fluxo diário) **não** traz o RF — o retorno dele é só
`cNumOs, cNumNFSe, cSerieNFSe, cLinkPortal, cCodVerif, cUrlNFSe, cPdfNFSe, cXmlNFSe,
cCodStatus, cDesStatus`. Nenhum campo de observação.

A chamada certa é `POST /api/v1/servicos/os/` com `call: "ListarOS"`. E tem uma
**pegadinha que custou caro**:

> Sem `apenas_importado_api: "S"` vêm apenas **157 OSs** — as criadas à mão.
> As OSs da esteira são criadas **via API** e ficam fora do filtro padrão.
> Com `"S"`, vêm **3.734**.

O RF aparece em **3 campos da OS**, e nos testes os três sempre concordaram:

| Campo | Conteúdo |
|---|---|
| `Observacoes.cObsOS` | o RF **puro**: `"6203092738"` — melhor fonte, sem parsing |
| `InformacoesAdicionais.cDadosAdicNF` | `"Nº RF:6203092738 \| Nº Contrato:… \| Nº Pedido/item:… \| Nº FRS:…"` (é o que imprime na nota — a exigência da Vale) |
| `Cabecalho.cCodIntOS` | `"OS-VALE-<CNPJ>-<RF>-<seq>"` |

**A corrente do vínculo** (conferida 6/6 com dado real):

```
RF → OS.cNumOS → LPAD(cNumOS,15,'0') = NF.cNumOs → nIdNf
```

**Bônus:** `InfoCadastro` da OS traz `cFaturada`, `cCancelada` e `dDtFat` — o
`status_nota` sai de graça, sem chamada extra.

## Custo de API

**~75 chamadas** (3.734 OSs a 50/página), não uma por nota. O `ListarOS` devolve o
registro completo, então não precisa de `ConsultarOS` nenhum. Uma vez só.

## Cuidado com o padrão do RF

`\b62\d{8,12}\b` **casa CNPJ** (`62002498000189` apareceu como falso positivo em
`cCodIntOS`). O padrão correto exige exatos 10 dígitos:

```js
/(?<!\d)62\d{8}(?!\d)/
```

## Nós

| Nó | Função |
|---|---|
| `Config` | chaves, `DRY_RUN`, `PAGINA_INICIAL`, `POR_PAGINA` |
| `Varre_OS_Omie` | `ListarOS` paginado com `apenas_importado_api:"S"`; extrai o RF das 3 fontes e confere se concordam |
| `Montar_SQL` | lotes de 400. Em dry-run gera **SELECT de diagnóstico**; em gravação gera `INSERT IGNORE … SELECT … JOIN NF` |
| `Dry_run?` | decide qual dos dois roda |
| `Diagnostico` → `Relatorio_DryRun` | mostra o que *aconteceria*, sem gravar |
| `Gravar_Vinculos` → `Resumo_Gravacao` | grava e resume (`detailedOutput` já ligado) |

## Ordem de uso

1. Preencher as chaves no `Config`. `DRY_RUN` já vem `true`.
2. Executar → ler o `Relatorio_DryRun`. **Nada é gravado.**
3. Conferir principalmente:
   - `varredura` = `COMPLETA` (se vier `PARCIAL`, completar antes de gravar)
   - `rf_divergente_entre_campos` = 0
   - `sem_nota_correspondente` — OSs com RF sem nota na `NF`
   - **`RF_INVISIVEIS_HOJE`** — RFs com nota que **não** estão em `rfs_faturados`
4. Virar `DRY_RUN = false` e executar.
5. Conferir: `SELECT origem, COUNT(*) FROM kvm4_db.rf_nota GROUP BY origem;`

## Segurança da gravação (verificado no SQL gerado)

- `INSERT IGNORE` — idempotente pela PK `(rf, nIdNf)`; rodar duas vezes não duplica.
- `JOIN` na `NF` — só grava vínculo de OS que **tem** nota; as sem nota são ignoradas
  e contadas no diagnóstico.
- `origem = 'BACKFILL'` — separa do que a esteira gravar (`ESTEIRA`).
- Nenhum `UPDATE`, `DELETE`, `DROP`, `TRUNCATE` ou `ALTER` no SQL gerado.
- Nenhum `$` no SQL (escapa do bug do nó MySQL com cifrão).

## O buraco que isso fecha — medido, não suposto

Na amostra da sondagem, **6 de 6** RFs achados nas OSs de junho **não estavam em
`rfs_faturados`**. O rastreio de RF só começou em **13/07/2026**: existem **2.412** notas
Vale anteriores a essa data. Esses RFs hoje passam batido no verificador e podem ser
refaturados sem ninguém perceber. O `RF_INVISIVEIS_HOJE` do relatório mede exatamente isso.

## Testes já realizados (10/08/2026)

- Sintaxe dos 4 nós Code validada com Node.
- `Varre_OS_Omie` rodado contra a **resposta real** da Omie (página salva na sondagem):
  20 OSs lidas → 6 com RF, 14 sem (não-Vale), **0 divergentes**, as 3 fontes concordando
  em todas, `cNumOs` no formato de 15 dígitos da `NF`, `status_nota = FATURADA` vindo da OS.
- Corrente RF → OS → nota conferida no banco: **6/6** com `nIdNf` e `cNumNFSe`.
- SQL de gravação auditado: `INSERT IGNORE`, `origem='BACKFILL'`, `JOIN` na `NF`,
  sem comando destrutivo, sem `$`.

---

# 9. Agendamento (10/08/2026) — para o retrato parar de envelhecer

## O problema que isso resolve

Depois do backfill a `rf_nota` ficou correta **naquele instante**. Mas nada mantinha ela viva:

- RF faturado hoje entra na `rfs_faturados` (o `Gravar_RFs` faz isso) → vira **legado**,
  só avisa. **Não** entra na `rf_nota` → **não bloqueia**.
- Nota cancelada amanhã → a `rf_nota` continua dizendo `FATURADA`.

Os dois fluxos novos tinham **gatilho manual**. Ninguém rodava, nada se atualizava, e a
fatia não coberta pelo bloqueio crescia todo dia.

## O que ficou agendado

| Fluxo | Horário | Custo/dia | O que faz |
|---|---|---|---|
| `VALE_Backfill_RF_Nota` | **05:00** | ~4 chamadas | cria o vínculo dos RFs novos |
| `VALE_Sync_Status_RF_Nota` | **05:30** | ~40 chamadas | atualiza o status (pega cancelamento) |

A ordem importa: o backfill roda primeiro e cria as linhas; meia hora depois o sync
atualiza o status **inclusive das linhas que acabaram de nascer**.

Os dois mantiveram também o **gatilho manual**, então dá para rodar na mão sem esperar.
E os dois vêm com `DRY_RUN = false` — um dry-run automático não serviria de nada.

## MODO INCREMENTAL: 4 chamadas em vez de 75

O `ListarOS` devolve as OS em ordem **crescente** de número, então as novas estão nas
**últimas** páginas. O incremental lê a página 1 (só para descobrir `total_de_paginas`) e
depois as N últimas:

```
MODO=INCREMENTAL, 75 páginas → lê 1, 73, 74, 75   = 4 chamadas  (95% de economia)
MODO=COMPLETO,    75 páginas → lê 1 até 75        = 75 chamadas
```

`PAGINAS_DO_FIM = 3` a 50/página = as **150 OS mais recentes**. Isso é de propósito uma
**janela móvel**, não "só as de ontem":

> A OS pode ser criada **antes** de a nota existir na `NF`, e o `JOIN` do backfill ignora
> OS sem nota. Reler os últimos dias garante que o vínculo apareça quando a nota chegar.
> Com ~20 OS/dia, 150 cobre cerca de uma semana de atraso.

**Rode `MODO=COMPLETO` uma vez por mês** (ou se desconfiar de buraco). O `INSERT IGNORE`
torna reprocessar inofensivo — não duplica nada.

## Testes do incremental (10/08/2026)

| Cenário | Páginas pedidas | Resultado |
|---|---|---|
| INCREMENTAL, 75 páginas | `1,73,74,75` | 4 chamadas |
| COMPLETO, 5 páginas | `1,2,3,4,5` | lê todas |
| INCREMENTAL, 1 página | `1` | não repete a página 1 |
| INCREMENTAL, 2 páginas | `1,2` | não repete a página 1 |
| `PAGINAS_DO_FIM=10`, 75 páginas | `1,66..75` | 11 chamadas |
| `MODO` vazio no Config | `1,73,74,75` | cai em INCREMENTAL |

## O que o agendamento NÃO resolve

O vínculo do RF novo só aparece **no dia seguinte**. Enquanto isso, o RF faturado hoje
fica como *legado* (avisa, permite reenvio) em vez de *bloqueado*.

A solução definitiva é a **esteira VALE gravar o vínculo na hora** que gera a OS — ela já
tem o RF e o `nIdNf` na mão, custo **zero** de API:

```sql
INSERT IGNORE INTO kvm4_db.rf_nota
  (rf, nIdNf, cNumNFSe, cNumOs, emp, origem)
VALUES ('<rf>', <nIdNf>, '<cNumNFSe>', '<cNumOs>', 'sillion', 'ESTEIRA');
```

O agendado continua valendo como **rede de segurança**: pega o que a esteira perder por
falha. O `INSERT IGNORE` faz os dois conviverem, e a coluna `origem` mostra quem gravou o quê.

---

# 10. Medição real do backfill (10/08/2026) — números de referência

Execução `MODO=COMPLETO`, `DRY_RUN=true`, **75 chamadas**:

| Campo | Valor | Leitura |
|---|---|---|
| `os_lidas` | 3.734 | todas as OSs da conta |
| `os_sem_rf` | 562 | OSs que não são da Vale |
| `os_com_rf` | 3.172 | |
| `rf_divergente_entre_campos` | **0** | as 3 fontes do RF concordaram em **todas** |
| `vinculos_que_seriam_criados` | 0 | o backfill anterior já cobriu tudo |
| `ja_existentes_na_rf_nota` | 3.169 | |
| `sem_nota_correspondente` | **3** | 0,09% — ver abaixo |
| `RF_INVISIVEIS_HOJE` | **2.369** | 75% dos RFs vinculados não estavam em `rfs_faturados` |

Estado da `rf_nota` depois do sync: **3.169 linhas, 3.169 com `status_em`** (o UPDATE casou
por `nIdNf` em todas), sendo 3.168 `FATURADA` e 1 `CANCELADA`.

## As 3 OSs sem nota — e por que NÃO viramos o schema

O backfill usa `JOIN NF` para achar o `nIdNf`. OS sem linha na `NF` é descartada em
silêncio. Como as notas **canceladas nunca entram na `NF`** (o fluxo diário descarta
`cStatusNFSe === 'C'`), existe em teoria um caso onde o RF de uma nota cancelada cedo
ficaria sem vínculo — e portanto liberado.

**Medido: são 3 casos em 3.172 (0,09%).** Tornar o `nIdNf` opcional exigiria trocar a
PRIMARY KEY de uma tabela com 3.169 linhas em produção. **Não compensa.**

E boa parte desses 3 provavelmente está **correta**: se a OS nunca foi faturada
(`cFaturada = 'N'`), não existe nota, nada foi cobrado, e o RF **deve** seguir liberado.

Por isso o relatório agora **nomeia** os casos em `quais_sem_nota` (formato `RF@OSxxx`) em
vez de só contá-los. Ao rodar o `COMPLETO` mensal, confira o `cFaturada` de cada um:
`N` = correto, ignore; `S` sem nota na `NF` = investigar, o RF está desprotegido.

## Por que "1 cancelada" e não 63

O sync encontra 63 notas canceladas na Omie, mas só 1 virou `CANCELADA` na `rf_nota`.
Não é erro: das 3.734 OSs, **562 não têm RF** — a maioria das canceladas é de OS não-Vale.
Como só 3 OSs *com* RF ficaram sem nota, no máximo 3 daquelas 63 poderiam ser da Vale.
A única que apareceu foi cancelada **depois** de o fluxo diário já ter gravado a nota.

> `marcados_como_cancelada: 4` (pelo `cCancelada` da **OS**) × 1 `CANCELADA` na `rf_nota`
> (pelo `cStatusNFSe` da **nota**) não é conflito: são entidades diferentes. Para a regra
> do CFO vale a **nota** — o sync sobrescrever o backfill é o desenho funcionando.
