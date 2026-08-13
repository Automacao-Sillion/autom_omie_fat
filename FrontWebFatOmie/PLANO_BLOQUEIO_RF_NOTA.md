# Plano — Bloqueio de RF vinculada a nota (upgrade pedido pelo CFO)

> Data: 10/08/2026 · Willian Ramos + Claude
> Estado: **desenho fechado; nada aplicado em produção.**
> Aguardando: arquivo do Willian que mostra onde o RF é gravado na Omie (§3).
> Continua o trabalho descrito em `CONTEXTO_CONFERENCIA_RF.md`.

## 1. O pedido

Hoje o app **faturar** responde *"esse RF já foi enviado?"* e, se já foi, deixa o usuário
marcar **Reenviar**. O CFO pediu outra coisa: se o RF já estiver **vinculado a uma nota**
faturada, cancelada ou substituída, **bloquear** o envio daquele RF.

### Decisões travadas com o Willian (10/08/2026)

| Decisão | Escolha |
|---|---|
| Abrangência do bloqueio | **Total nos 3 status.** Faturada, cancelada e substituída bloqueiam. O checkbox "Reenviar" **sai** do fluxo VALE — liberar exige mexer no banco. |
| Como popular o vínculo | **Um fluxo único** que varre todas as notas na Omie, traz status + RF e grava os dois **como coluna na própria `NF`**. Substitui sync + backfill separados. |
| Cardinalidade | **1 nota = 1 RF.** Substituição é o mesmo RF em **2 notas** (original + substituta). → **não precisa de tabela de vínculo.** |

## 2. Diagnóstico do que existe hoje (verificado no banco em 10/08/2026)

| Objeto | Estado real |
|---|---|
| `kvm4_db.rfs_faturados` | `rf VARCHAR(32) PK` + `enviado_em DATETIME`. **758 RFs.** Lista chapada de "já enviado" — sem nota, sem status, sem OS. |
| `kvm4_db.NF` | 3.977 notas. **Sem coluna de status** (nada de `cStatusNFSe`) e **sem coluna de RF**. |
| Vínculo RF↔nota | **Não existe.** A única coluna com "rf" no nome em todo o servidor é `rfs_faturados.rf`. |
| `NF.cNumOs` | OS de 15 dígitos (`000000000005577`). **Não é o RF** (10 dígitos, `6203185520`): `JOIN NF.cNumOs = rfs_faturados.rf` → **0 de 758**. |
| `Titulos` | Tem `status` + `data_cancelamento` por `nIdNf`, mas é status do **título financeiro**, não da NFS-e. Não serve como proxy de nota cancelada. |

Três consequências que definem o trabalho:

1. **O RF só existe no histórico da nota na Omie** — é onde vocês gravam a pedido da Vale.
   Histórico da Omie não é replicado para o banco.
2. **O status da nota nunca chega ao banco, por construção.** O fluxo de download filtra
   `cStatusNFSe === 'C'` (cancelada) **na API da Omie** e grava só as emitidas. As
   canceladas são descartadas antes de tocar o banco.
3. Sinal frágil: 3.977 notas / 3.964 OS distintas = 13 OS com 2 notas.

**Conclusão:** faltam 2 informações no banco (RF na nota e status da nota). O front é a
menor parte do serviço.

## 3. Análise do fluxo "Popula tabela NF & boleto" (recebido 10/08/2026)

Arquivo: `Sillion Matriz_Popula tabela NF & boleto- Faturamento (Diário).json` — 63 nós.
**É o fluxo certo para receber a mudança de status.** O que ele revelou:

### ✅ Resolvido

| Achado | Consequência |
|---|---|
| `Lista_NFSEs_filtrado2` chama `ListarNFSEs` paginado (500/pág) e **já lê `nf.Cabecalho.cStatusNFSe`** | O status **já vem na chamada de lista**. Sync de status é barato — não precisa de fluxo novo nem de chamada extra. |
| O campo `cStatusNFSe` **já circula** no pipeline (é mapeado no retorno do nó) mas **não é gravado** no insert da `NF` | Gravar é acrescentar 1 coluna no mapeamento do nó `Insert rows in a table6`. |
| `APENAS_EMITIDAS = true` é **constante no código** do nó, e descarta `cStatusNFSe === 'C'` | Basta virar `false` para as canceladas passarem a entrar. |
| `Obter_Docs2` chama `ObterNFSe` (`/servicos/osdocs/`, `param:[{nIdNf}]`) — **1 chamada por nota, já hoje** | O "risco de volume" do §5 **já é realidade aceita** neste fluxo. Se o RF estiver no retorno do `ObterNFSe`, capturá-lo é **de graça**: a chamada já acontece. |

### ⚠️ Achado que atrapalha o backfill

O insert na `NF` usa `skipOnConflict: true`, e o **único** UPDATE existente
(`Update rows in a table2`) mexe só em `pdf_url`, casando por `cNumNFSe`.
→ **Rodar o fluxo de novo não atualiza as 3.977 linhas existentes.** O backfill de
`rf`/`status_nota` precisa de um caminho de UPDATE novo (match por `nIdNf`).

### ❌ NÃO resolvido — o RF não está neste fluxo

Zero menções a `RF`, `observação`, `histórico`, `ocorrência` ou `cObs` nos 63 nós.
Este fluxo **lê** notas da Omie; não é ele que **escreve** o RF.

**Ainda preciso de um destes dois:**

1. O export da **esteira VALE / TOT_&_VALE** — o fluxo que recebe o arquivo do front
   (`{email, empresa_select, filename, file_base64, mime_type, tipo_faturamento}`), gera as
   notas e escreve o RF no histórico. É lá que está o campo/formato.
2. Ou o ok para **uma chamada de leitura** à Omie (`ObterNFSe` numa nota da Vale, e
   `ConsultarOS` na OS dela) para eu ver no retorno onde o RF aparece.

Suspeita, a confirmar: como o faturamento é **por OS** e `NF.cNumOs` existe, o RF
provavelmente está na **Ordem de Serviço** (observação / `cObsOS`), gravado pela esteira ao
criar a OS — não na NFS-e.

### ✅ Status: RESOLVIDO em 10/08/2026 pelo dry-run real

O fluxo `n8n/VALE_Sync_Status_RF_Nota.json` rodou em produção em modo dry-run:

```
3.919 notas lidas em 40 chamadas → vocabulario: { "C": 63, "F": 3856 }
```

- **Só existem 2 códigos:** `F` = FATURADA (3.856) e `C` = CANCELADA (63).
- **Não existe código para SUBSTITUÍDA.** Na Omie a substituição é cancelamento + nota
  nova → detecta-se pelo **mesmo `rf` em duas linhas de `rf_nota`** (é por isso que a PK
  é `(rf, nIdNf)`). Como os dois códigos bloqueiam, o status é o **motivo exibido**, não
  a decisão: RF com nota = bloqueado, ponto.
- **Custo real: 40 chamadas, não ~8** — a Omie limita a página a ~100 registros mesmo
  pedindo 500.

### ✅ Uma empresa só — Sitrack não usa RF

Confirmado com o Willian em 10/08/2026: **a Sitrack não usa RF.** RF é controle da Vale,
faturada pela Sillion. Então o fluxo roda com **uma app_key só** e não há pendência de
chave da Sitrack. (Contagem no banco: sillion 3.871, sitrack 154.)

### 📌 Por que a Omie tem mais notas que a `NF` — e por que isso valida o Nível 2

Omie (uma conta, todos os status): **3.919**. Banco `NF`, emp sillion: **3.871**.
A diferença são as **canceladas**: o fluxo diário descarta `cStatusNFSe === 'C'` antes de
inserir, então boa parte das 63 canceladas **nunca entrou na `NF`**.

Consequência importante: **um bloqueio que dependesse da `NF` teria buraco** — justamente
nas canceladas, que são o caso que o CFO quer barrar. A `rf_nota` guarda `nIdNf` direto e
**não** depende de a `NF` ter a linha. Isso não foi sorte do Nível 2, é o motivo de ele ser
mais robusto que o Nível 3 aqui.

> Credenciais: `C:\Claude\omie_keys.json` está **malformado** (vários JSONs concatenados).
> O workflow recebido carrega as chaves no nó `Define_key_secret`.

## 4. Mudanças no banco (`kvm4_db`) — Nível 2

**Decisão do Willian: não mexer na estrutura que já existe.** Então:

- `NF` → **intacta**, nenhuma coluna nova
- `rfs_faturados` → **intacta**
- fluxo diário "Popula tabela NF & boleto" → **intacto**
- entra **uma tabela nova**: `rf_nota`

Script pronto: **`sql/01_cria_rf_nota.sql`** (só `CREATE TABLE`, nenhum `ALTER`, nenhum
`DROP`). Papel de cada tabela depois disso:

| Tabela | Responde |
|---|---|
| `rfs_faturados` (já existe) | "esse RF **já foi enviado**" |
| `rf_nota` (nova) | "esse RF **virou nota**, e qual o status dela" |

E os 3 casos do front caem por gravidade:

| Onde o RF está | Caso |
|---|---|
| em nenhuma das duas | **NOVO** → segue |
| em `rf_nota` | **BLOQUEADO** → mostra nota + status |
| só em `rfs_faturados` | **LEGADO** → enviado, mas não gerou nota |

Pontos de atenção:

- PK é **`(rf, nIdNf)`**, não só `rf`. Substituição = mesmo RF em 2 notas; com PK só em
  `rf` a segunda não entraria. Duas linhas com o mesmo `rf` **são** a assinatura de uma
  substituição — que é como se detecta substituição, já que a Omie não tem código para ela.
- `nIdNf` é `NOT NULL` de propósito: a tabela registra **vínculo**. RF sem nota não entra
  aqui — e é exatamente isso que separa LEGADO de BLOQUEADO.
- `rf_nota` **não** tem FK para `NF`, e isso é deliberado: parte das notas canceladas nunca
  entrou na `NF` (o fluxo diário as descarta). Uma FK inviabilizaria justamente o caso que
  o CFO quer bloquear.

## 5. O fluxo de varredura (decisão do Willian: um só)

Varre as notas na Omie, traz status + RF, grava nas colunas novas. Serve de backfill (notas
existentes) **e** de manutenção contínua (agendado).

**A questão de volume está resolvida** (§3): o fluxo já pagina a lista *e* já faz 1
`ObterNFSe` por nota. Não precisa de fluxo novo nem de job em lote separado — a mudança é
**dentro** do fluxo diário que já existe.

### Parte A — status (100% desbloqueado, dá para fazer já)

1. Nó `Lista_NFSEs_filtrado2`: `const APENAS_EMITIDAS = false;` — para as canceladas
   deixarem de ser descartadas. O `cStatusNFSe` **já** é mapeado na saída do nó.
2. Nó `Insert rows in a table6`: acrescentar ao mapeamento
   `cStatusNFSe = {{ $json.cStatusNFSe }}` e `status_nota` (derivado), `status_em`.
3. **Caminho de UPDATE novo** (o insert tem `skipOnConflict: true` e não atualiza nada):
   `UPDATE NF SET cStatusNFSe=…, status_nota=…, status_em=NOW() WHERE nIdNf=…`.
   É esse passo que preenche as 3.977 notas já existentes.
4. Mapear `cStatusNFSe` → `status_nota`; `'C'` = CANCELADA é conhecido, o resto falta confirmar.

### Parte B — RF (travado no §3)

Depende de saber o campo. Se estiver no retorno do `ObterNFSe`, entra no mesmo nó, sem
chamada extra. Se estiver na OS, precisa de um `ConsultarOS` por nota — aí o volume dobra e
vale medir antes.

Requisitos comuns:

- `UPDATE` idempotente por `nIdNf`, gravando `status_em = NOW()` e `rf_origem`.

### 5.0 Disciplina de consumo da API Omie (regra dura — risco de ban)

Exigência do Willian: **nada de consumo redundante.** A Omie limita/bane por volume, então o
desenho é obrigado a economizar chamada:

1. **Status pela LISTA, nunca por nota.** `ListarNFSEs` já traz `cStatusNFSe` a 500/página →
   as 3.977 notas custam **~8 chamadas**. Buscar status com `ObterNFSe` custaria 3.977. Nunca
   usar `ObterNFSe` para status.
2. **Backfill só no que falta.** A varredura processa apenas
   `WHERE rf IS NULL OR status_nota IS NULL` — nunca re-varre a tabela inteira. Cada nota
   preenchida sai da fila para sempre.
3. **O RF é imutável.** Capturado uma vez, nunca é buscado de novo. Logo o custo por nota é
   **único**, não recorrente.
4. **Melhor ainda: capturar na origem.** A esteira VALE (§5.1) já tem RF e nota na mão ao
   gerar — gravar ali custa **zero chamada de API**. Quanto antes isso entrar, menor a fila de
   backfill. O backfill é dívida do passado, não do futuro.
5. **Lotes com retomada.** Se o backfill morrer na nota 2.000, retoma da 2.000 — não do zero.
   Reprocessar do início é exatamente o consumo redundante a evitar.
6. **Throttle.** Manter o padrão que o fluxo já usa (`setTimeout(300ms)` entre páginas) e
   respeitar ~4 req/s. Nunca paralelizar chamadas à Omie.
7. **Dry-run não chama a API duas vezes.** O dry-run grava o retorno em CSV/tabela de
   staging; a carga real lê o staging, não a Omie de novo.
8. **Não mexer no consumo atual do fluxo diário.** Ele já faz 1 `ObterNFSe` por nota da
   janela de datas — esse é o baseline. As mudanças de status **não** acrescentam chamada
   (o campo já vem na lista).

> Nota de sessão: o SSH do servidor tem fail2ban agressivo — já me baniu 2× hoje por
> conexões em paralelo. Inspeção no banco = **uma** conexão com as queries em lote.
- **Relatório de sobra** (os casos que precisam de olho humano):
  - RF em `rfs_faturados` sem nota correspondente → envio que não gerou nota (ver §8);
  - RF achado na Omie que não está em `rfs_faturados` → faturado fora do fluxo;
  - nota cujo histórico traz 2+ RFs → derruba a premissa "1 nota = 1 RF".
- **Dry-run primeiro**: gerar CSV do que *seria* gravado, antes de escrever no banco.

### 5.1 Esteira VALE — gravar o RF na hora (complementar)

O `gravar-rf` atual **não serve** para isso: ele roda logo após o envio do arquivo, quando as
notas **ainda não existem**. O vínculo deve ser gravado na `rf_nota` no ponto da esteira em
que **cada nota é gerada** — o mesmo ponto onde vocês já escrevem o RF no histórico:

```sql
INSERT IGNORE INTO rf_nota (rf, nIdNf, cNumNFSe, cNumOs, emp, origem)
VALUES ('<rf>', <nIdNf>, '<cNumNFSe>', '<cNumOs>', 'sillion', 'ESTEIRA');
```

**Custo zero de API** — a esteira já tem RF e nota na mão nesse instante.

Sem isso o fluxo do §5 vira a única fonte, e o bloqueio fica com a defasagem do agendamento
(RF faturado hoje só bloqueia depois do próximo sync). Com isso, bloqueia na hora.

### 5.2 `consulta-rf` — devolver status e bloqueio

A `rf_nota` é autossuficiente (guarda `cNumNFSe`, `cNumOs`, `status_nota`), então **não
precisa de JOIN com `NF`** — o que também evita o buraco das canceladas ausentes:

```sql
SELECT rf, nIdNf, cNumNFSe, cNumOs, emp,
       COALESCE(status_nota, 'FATURADA') AS status_nota
FROM rf_nota
WHERE rf IN (:lista)
ORDER BY rf, criado_em;
```

Existe linha → **bloqueado**. Duas linhas para o mesmo RF → substituição (mostrar a mais
recente e sinalizar). Resposta (mantém `existentes` por retrocompatibilidade):

```jsonc
{
  "existentes": [
    { "rf": "6203185520", "bloqueado": true, "status_nota": "CANCELADA",
      "numero_nota": "0000000011671", "os": "000000000005577", "data_emissao": "2026-08-10" },
    { "rf": "6203136190", "bloqueado": false, "status_nota": null, "legado": true }
  ]
}
```

## 6. Mudanças no front (menor parte)

`conferencia_rf.py`:

- `consultar_rfs()` passa a devolver `{rf: {bloqueado, status_nota, numero_nota, os, ...}}`
  em vez de `{rf: referência}`;
- `conferir()` passa a devolver **3 baldes**: `novos`, `bloqueados`, `legado`;
- `gerar_arquivo_filtrado()` **não muda** — só recebe as linhas bloqueadas somadas.

`app.py`:

- **Bloqueados** → tabela somente leitura (sem checkbox), com nº da nota + status + motivo;
  linhas removidas do arquivo **à força**;
- **Legado** (em `rfs_faturados` sem nota) → mantém aviso; ver §8;
- Botão bloqueado se **todo** o arquivo cair em bloqueado;
- o `st.data_editor` com "Reenviar" **sai** do caminho dos bloqueados (decisão do CFO).

## 7. Assunção que precisa de aval (não bloqueia o início)

A regra "bloqueio total nos 3 status" fala de **notas**. Um RF enviado que **não gerou nota**
(falha na esteira) não cai em nenhum dos 3 status.

**Assumido:** esse RF **não** é bloqueado — segue com aviso, como hoje. Bloquear seria queimar
o RF em definitivo por uma falha técnica, exigindo mexer no banco para faturar algo que nunca
foi faturado.

## 8. Ordem de execução

| # | Passo | Depende de |
|---|---|---|
| 0 | Ler o arquivo do Willian → campo/formato do RF na Omie | — **bloqueia o resto** |
| 1 | Backup + `ALTER TABLE NF` (§4) | 0 |
| 2 | Fluxo de varredura em dry-run → conferir CSV | 0, 1 |
| 3 | Varredura real (preenche as 3.977 notas) | 2 |
| 4 | Esteira VALE grava `NF.rf` na geração (§5.1) | 0, 1 |
| 5 | `consulta-rf` novo (§5.2) | 1, 3 |
| 6 | Front 3 baldes (§6) | 5 |
| 7 | Teste ponta a ponta + deploy | tudo |

Deploy do front é nos **dois** lugares: container `sillion-apps` (`docker cp` +
`supervisorctl restart faturar`) e Streamlit Cloud (repo `Automacao-Sillion/autom_omie_fat`).

## 9. Pendências de verificação

- [ ] Valores distintos de `Titulos.status` — consulta cortada pelo fail2ban; irrelevante para
      a regra (é status de título), mas fecha o mapa do banco.
- [ ] Confirmar se `/dados` lê `NF` direto ou só a view (afeta se RF/status aparecem lá).
- [ ] Consertar `C:\Claude\omie_keys.json` (JSONs concatenados).
