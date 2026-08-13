-- ============================================================
-- Listinha RF -> Nota
-- BANCO: kvm4_db  (o mesmo de NF e rfs_faturados -- NAO e' o schema
--        "faturamento"; a credencial do n8n chamada "MySQL faturamento"
--        confunde, mas a tabela vive em kvm4_db).
-- Rodado em producao em 10/08/2026: tabela criada, 0 linhas.
-- ============================================================
USE kvm4_db;

-- ============================================================
-- Nivel 2 do plano: NADA existente e' alterado.
--   . NF                -> intacta (nenhuma coluna nova)
--   . rfs_faturados     -> intacta
--   . fluxo diario "Popula tabela NF & boleto" -> intacto
-- ============================================================
-- Papel de cada tabela depois desta mudanca:
--   rfs_faturados = "esse RF JA FOI ENVIADO"   (ja existe, 758 linhas)
--   rf_nota       = "esse RF VIROU NOTA"       (nova, comeca vazia)
--
-- Com as duas, os 3 casos do front caem por gravidade:
--   RF em nenhuma das duas          -> NOVO      (segue)
--   RF em rf_nota                   -> BLOQUEADO (mostra a nota + status)
--   RF so em rfs_faturados          -> LEGADO    (enviado, mas nao gerou nota)
-- ============================================================

CREATE TABLE IF NOT EXISTS rf_nota (
  rf          VARCHAR(32)  NOT NULL              COMMENT 'RF da Vale, normalizado (sem espaco, sem .0)',
  nIdNf       BIGINT       NOT NULL              COMMENT 'NF.nIdNf da nota gerada',
  cNumNFSe    VARCHAR(20)  NULL                  COMMENT 'numero da NFS-e, para exibir no front',
  cNumOs      VARCHAR(20)  NULL                  COMMENT 'NF.cNumOs (OS que gerou a nota)',
  emp         VARCHAR(45)  NULL                  COMMENT 'sillion | sitrack',
  cStatusNFSe VARCHAR(2)   NULL                  COMMENT 'codigo cru da Omie (C = cancelada)',
  status_nota VARCHAR(20)  NULL                  COMMENT 'FATURADA | CANCELADA | SUBSTITUIDA',
  origem      VARCHAR(20)  NOT NULL DEFAULT 'ESTEIRA' COMMENT 'ESTEIRA | BACKFILL',
  criado_em   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  status_em   DATETIME     NULL                  COMMENT 'ultima vez que o status foi sincronizado',
  PRIMARY KEY (rf, nIdNf),
  KEY ix_rf_nota_rf    (rf),
  KEY ix_rf_nota_nidnf (nIdNf)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Vinculo RF (Vale) -> nota fiscal. Bloqueio de refaturamento.';

-- Por que a PK e' (rf, nIdNf) e nao so' (rf):
--   substituicao = o MESMO RF em DUAS notas (a original e a substituta).
--   Com PK so' em rf, a segunda nota nao entraria. Duas linhas com o mesmo
--   rf sao, por si, a assinatura de uma substituicao.
--
-- Por que nIdNf e' NOT NULL:
--   a tabela existe para registrar VINCULO. RF sem nota nao entra aqui --
--   ele continua so' em rfs_faturados, e e' exatamente isso que distingue
--   o caso LEGADO do caso BLOQUEADO.

-- Nota do EXPLAIN (10/08/2026): a consulta de bloqueio
--   SELECT ... FROM rf_nota WHERE rf IN (...)
-- resolve por PRIMARY, porque rf ja' e' a primeira coluna da PK. Logo o
-- indice ix_rf_nota_rf e' REDUNDANTE -- pode ser dropado sem perda:
--   ALTER TABLE rf_nota DROP INDEX ix_rf_nota_rf;
-- Mantido por enquanto so' para nao mexer em tabela recem-criada.

-- ---------- conferencia ----------
SHOW CREATE TABLE rf_nota;
SELECT COUNT(*) AS linhas FROM rf_nota;

-- Validado com EXPLAIN em 10/08/2026 (sem alterar dado): o UPDATE em lote
-- do fluxo VALE_Sync_Status_RF_Nota e a consulta de bloqueio do consulta-rf
-- parseiam e usam indice nesta estrutura.
