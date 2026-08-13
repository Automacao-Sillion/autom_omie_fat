-- ============================================================
-- rf_os: o RF e a OS, gravados PELA ESTEIRA no instante da criacao.
-- BANCO: kvm4_db
-- ============================================================
-- POR QUE ESTA TABELA EXISTE
--
-- A esteira VALE cria a OS a partir do arquivo de medicao da Vale. Naquele
-- instante ela tem o RF (veio da planilha) e recebe o cNumOS de volta da
-- Omie -- mas a NOTA ainda nao existe: o faturamento e' um passo separado
-- (FaturarLoteOS), e esse metodo devolve so' o status, nenhum id de nota.
--
-- Confirmado na doc da Omie: o IncluirOS retorna
--   { cCodIntOS, nCodOS, cNumOS, cCodStatus, cDescStatus }
-- e o cNumOS ja' vem com 15 digitos e zeros a esquerda ("000000000000018"),
-- EXATAMENTE o formato que NF.cNumOs guarda. Nao precisa converter nada.
--
-- Entao o vinculo e' montado em duas etapas:
--   1) esteira grava (rf, cNumOs) aqui, na hora, sem custo de API
--   2) o fluxo VALE_Promove_RF_OS promove para rf_nota quando a nota
--      aparece na NF -- em SQL PURO, ZERO chamada de API
--
-- Ganho: a varredura da Omie (VALE_Backfill_RF_Nota) deixa de ser
-- necessidade de hora em hora e vira auditoria mensal. E o registro de que
-- aquele RF foi usado passa a existir no INSTANTE do envio, mesmo que a
-- nota nunca chegue na NF (caso da nota cancelada cedo).
-- ============================================================
USE kvm4_db;

CREATE TABLE IF NOT EXISTS rf_os (
  rf           VARCHAR(32) NOT NULL              COMMENT 'RF da Vale, normalizado (sem espaco, sem .0)',
  cNumOs       VARCHAR(20) NOT NULL              COMMENT 'cNumOS do retorno do IncluirOS (15 digitos, com zeros)',
  criado_em    DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'instante em que a esteira gravou',
  promovido_em DATETIME    NULL                  COMMENT 'quando virou vinculo em rf_nota (NULL = ainda sem nota)',
  PRIMARY KEY (rf, cNumOs),
  KEY ix_rf_os_pendente (promovido_em, criado_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='RF -> OS gravado pela esteira na hora. Ponte para rf_nota.';

-- PK (rf, cNumOs): o mesmo RF poderia, em teoria, aparecer em duas OS.
-- promovido_em limita o trabalho do fluxo de promocao: ele so' olha o que
-- ainda esta NULL, entao o custo nao cresce com o historico.

-- ---------- conferencia ----------
SHOW CREATE TABLE rf_os;
SELECT COUNT(*) AS linhas, SUM(promovido_em IS NULL) AS pendentes FROM rf_os;
