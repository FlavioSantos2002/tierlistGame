-- Esquema EXATO da versão 1 (o do tierlist.db que já está no celular).
-- Usado só pelos testes de migração: não altere.
CREATE TABLE IF NOT EXISTS partidas (
    -- AUTOINCREMENT: o id de uma partida apagada nunca é reaproveitado.
    -- Sem isso, uma aba antiga com "/partida/1/apagar" poderia apagar
    -- uma partida nova que recebeu o mesmo id 1.
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tema_nome     TEXT    NOT NULL,
    estado        TEXT    NOT NULL DEFAULT 'espera'
                  CHECK (estado IN ('espera', 'votacao', 'resultado', 'encerrada')),
    rodada_atual  INTEGER NOT NULL DEFAULT 0,   -- 0 enquanto está em espera
    total_rodadas INTEGER NOT NULL,
    versao        INTEGER NOT NULL DEFAULT 1,   -- sobe a cada mudança
    criada_em     REAL    NOT NULL              -- horário Unix (time.time())
);

CREATE TABLE IF NOT EXISTS faixas (
    id         INTEGER PRIMARY KEY,
    partida_id INTEGER NOT NULL REFERENCES partidas (id) ON DELETE CASCADE,
    indice     INTEGER NOT NULL,                -- 0 = melhor faixa
    rotulo     TEXT    NOT NULL,
    descricao  TEXT    NOT NULL DEFAULT '',
    cor        TEXT    NOT NULL,
    UNIQUE (partida_id, indice)
);

CREATE TABLE IF NOT EXISTS jogadores (
    id         INTEGER PRIMARY KEY,
    partida_id INTEGER NOT NULL REFERENCES partidas (id) ON DELETE CASCADE,
    nome       TEXT    NOT NULL,
    codigo     TEXT    NOT NULL UNIQUE,
    visto_em   REAL,                            -- NULL = nunca entrou
    UNIQUE (partida_id, nome)
);

CREATE TABLE IF NOT EXISTS itens (
    id           INTEGER PRIMARY KEY,
    partida_id   INTEGER NOT NULL REFERENCES partidas (id) ON DELETE CASCADE,
    rodada       INTEGER NOT NULL,              -- rodada em que o item aparece (1..T)
    nome         TEXT    NOT NULL,
    imagem       TEXT    NOT NULL,
    situacao     TEXT    NOT NULL DEFAULT 'pendente'
                 CHECK (situacao IN ('pendente', 'classificado', 'pulado')),
    faixa_indice INTEGER,                       -- preenchido quando classificado
    UNIQUE (partida_id, rodada)
);

CREATE TABLE IF NOT EXISTS votos (
    item_id      INTEGER NOT NULL REFERENCES itens (id) ON DELETE CASCADE,
    jogador_id   INTEGER NOT NULL REFERENCES jogadores (id) ON DELETE CASCADE,
    faixa_indice INTEGER,                       -- NULL = absteve-se ("Pular")
    votado_em    REAL    NOT NULL,
    -- Quantas vezes o voto/abstenção deste jogador neste item foi aceito.
    -- O jogador manda a revisão que estava vendo; um pedido antigo (que chegou
    -- atrasado ao servidor) é recusado em vez de desfazer uma escolha mais nova.
    revisao      INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (item_id, jogador_id)
);

CREATE TABLE IF NOT EXISTS continuar (
    item_id    INTEGER NOT NULL REFERENCES itens (id) ON DELETE CASCADE,
    jogador_id INTEGER NOT NULL REFERENCES jogadores (id) ON DELETE CASCADE,
    PRIMARY KEY (item_id, jogador_id)
);
