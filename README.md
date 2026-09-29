# Tier List em grupo

Jogo para jogar com amigos, cada um no próprio celular. Os jogadores dizem em qual faixa
(S, A, B, C, D...) fica cada item (por exemplo, um Pokémon), e o jogo monta a tier list do grupo.
Sem pontuação e sem cronômetro. Há dois modos:

- **Ao vivo**: todos juntos, um item por rodada. Quando a rodada fecha, todos veem o resultado.
- **Cada um no seu ritmo**: cada jogador responde todos os itens quando quiser, numa ordem
  sorteada só para ele. Quem finaliza vê a tier list geral e a sua compatibilidade com ela.

Feito em Python/Flask, roda num celular Android antigo (Termux) e fica acessível pela internet
por um *quick tunnel* do Cloudflare.

## Sumário

1. [Estrutura do projeto](#1-estrutura-do-projeto)
2. [Rodar no PC](#2-rodar-no-pc)
3. [Enviar para o celular](#3-enviar-para-o-celular)
4. [Primeira instalação no Termux](#4-primeira-instalação-no-termux)
5. [Iniciar e parar](#5-iniciar-e-parar)
6. [Como jogar](#6-como-jogar)
7. [Backup do banco](#7-backup-do-banco)
8. [Formato do temas.json](#8-formato-do-temasjson)
9. [Problemas comuns](#9-problemas-comuns)
10. [Atualizar da versão 1 para a 2 sem perder o banco](#10-atualizar-da-versão-1-para-a-2-sem-perder-o-banco)

---

## 1. Estrutura do projeto

| Arquivo / pasta | Para que serve |
| --- | --- |
| `app.py` | Cria o app Flask, confere as variáveis de ambiente (o gunicorn usa `app:app`) |
| `banco.py` | SQLite: tabelas, migração automática do banco, uma conexão por requisição, transações `BEGIN IMMEDIATE` |
| `jogo.py` | Regras do modo ao vivo: fechamento da rodada, regra da maioria, presença online, remover jogador |
| `individual.py` | Regras do modo "cada um no seu ritmo": respostas, finalizar, tier list geral, compatibilidade |
| `rotas_admin.py` | Painel do admin: login, partidas, nova partida, controle da partida |
| `rotas_jogador.py` | Link do jogador e a API (estado, votar, pular, continuar, responder, finalizar) |
| `temas.py` | Leitura e validação do `temas.json` |
| `endereco.py` | Descobre o endereço público do túnel para montar os links |
| `templates/`, `static/` | HTML, CSS e JavaScript (sem frameworks) |
| `temas.json` | Temas e itens do jogo (seção 8) |
| `iniciar.sh` | Sobe (ou reinicia) tudo no Termux |
| `parar.sh` | Para o app e o túnel com segurança (também usado pelo `iniciar.sh`) |
| `tests/` | Testes automáticos (só no PC) |
| `ferramentas/` | `conferir_migracao.py`: ensaia a migração num backup do banco (só no PC, seção 10) |

Dependências de produção: só `flask` e `gunicorn` (`requirements.txt`).
Nos testes também entra o `pytest` (`requirements-dev.txt`).

---

## 2. Rodar no PC

No PowerShell, na pasta do projeto:

```powershell
cd C:\Users\Legion\Documents\f\teste\tierlist
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
```

Para subir o app (o gunicorn não roda no Windows, então no PC usamos o servidor do Flask):

```powershell
$env:ADMIN_TOKEN = "minha-senha-local"
$env:SECRET_KEY  = "chave-local-qualquer"
$env:BASE_URL    = "http://127.0.0.1:5001"   # para os links dos jogadores funcionarem no PC
.\.venv\Scripts\python app.py
```

Abra `http://127.0.0.1:5001`. Para fazer de conta que é um jogador, abra o link dele numa
**janela anônima** (ou em outro navegador). Para ver como fica no celular: F12 e depois Ctrl+Shift+M.

Para rodar os testes:

```powershell
.\.venv\Scripts\python -m pytest
```

Os testes de JavaScript (`tests/test_js.py`) usam o Edge ou o Chrome sem janela. Se não houver
nenhum dos dois, eles são pulados. Rode os testes pelo **PowerShell**: pelo Git Bash o Edge não
consegue abrir e os testes de JavaScript falham.

Para testar sem mexer no banco de sempre do PC, aponte o app para outro arquivo antes de subir:
`$env:DB_PATH = "./teste.db"`.

---

## 3. Enviar para o celular

Do PowerShell do PC (troque o usuário e o IP se forem outros):

```powershell
cd C:\Users\Legion\Documents\f\teste\tierlist
ssh -p 8022 u0_a123@192.168.100.3 "mkdir -p ~/tierlist"
scp -P 8022 -r app.py banco.py endereco.py jogo.py individual.py rotas_admin.py rotas_jogador.py temas.py temas.json requirements.txt iniciar.sh parar.sh .env.example templates static u0_a123@192.168.100.3:tierlist/
```

- **Não** envie `.venv`, `tests`, `ferramentas`, `__pycache__`, `backups`, nenhum `.db` nem o `.env`
  do PC. O `.env` do celular é criado lá (seção 4). O banco do celular (`tierlist.db`) não está na
  lista: o `scp` nunca mexe nele.
- **Cuidado com o `temas.json`**: se você editou esse arquivo no celular, reenviar o do PC apaga a edição.
- Todos os arquivos precisam ter final de linha **LF**. O projeto já está assim (`.gitattributes` e
  `.editorconfig`). Se editar no Windows, use um editor que respeite o `.editorconfig`
  (o VS Code respeita), nunca o Bloco de Notas.

Para **atualizar** o app depois de mudar o código: rode o mesmo `scp` e depois `bash iniciar.sh` no celular.
Se a atualização muda o formato do banco (como a da versão 1 para a 2), siga a **seção 10**.

---

## 4. Primeira instalação no Termux

Entre no celular pelo SSH:

```powershell
ssh -p 8022 u0_a123@192.168.100.3
```

E no Termux:

```bash
pkg install -y python tmux cloudflared      # o convite provavelmente já instalou; não faz mal repetir
cd ~/tierlist
pip install -r requirements.txt
python -c "import flask, gunicorn; print('dependências ok')"
```

Crie o `.env` a partir do exemplo, já com senha e chave aleatórias:

```bash
cd ~/tierlist
cp .env.example .env
sed -i "s|^ADMIN_TOKEN=.*|ADMIN_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(24))')|" .env
sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')|" .env
grep ADMIN_TOKEN .env      # anote esta senha: é com ela que você entra no painel
```

Se preferir editar à mão: `nano .env` (salvar: Ctrl+O e Enter; sair: Ctrl+X).
Formato `NOME=valor`, **sem espaços** ao redor do `=`.

Confira se o horário do Python bate com o do celular (é o que aparece em "Criada em" no painel):

```bash
date; python -c "import time; print(time.strftime('%d/%m/%Y %H:%M'))"
```

O `iniciar.sh` já passa o fuso do Android para o app. Se mesmo assim a hora sair errada, coloque o
fuso no `.env`, por exemplo `TZ=America/Sao_Paulo`.

---

## 5. Iniciar e parar

**Iniciar** (também serve para **reiniciar**):

```bash
cd ~/tierlist && bash iniciar.sh
```

O script:

1. confere se `tmux`, `cloudflared`, `gunicorn` e o `.env` estão ok, e se o `.env`, os `.py` e os `.sh` não têm CRLF;
2. roda `termux-wake-lock` (o Android não põe o Termux para dormir);
3. para o app e o túnel antigos com o `parar.sh` (só os deste projeto; o convite continua rodando)
   e confere que a porta 5001 ficou livre;
4. sobe o app (gunicorn, porta **5001**) e o túnel (métricas em **127.0.0.1:2001**) nas sessões
   tmux `tl-app` e `tl-tunel`;
5. espera os dois ficarem prontos e mostra o endereço público:

```
Tier List no ar!
  Endereço público: https://algumas-palavras.trycloudflare.com
  Painel do admin:  https://algumas-palavras.trycloudflare.com/admin
```

> **O endereço muda a cada reinício do túnel.** Links que você mandou antes param de funcionar.
> A tela da partida no painel sempre mostra os links com o endereço atual: é só copiar e mandar de novo.

**Ver o que está acontecendo** (mensagens e erros):

```bash
tmux ls                       # lista todas as sessões (as do convite aparecem também)
tmux attach -t tl-app         # entra na sessão do app; para sair sem parar: Ctrl+B e depois D
tmux attach -t tl-tunel       # idem, do túnel
```

**Parar** (só este projeto):

```bash
cd ~/tierlist && bash parar.sh
```

Use o `parar.sh` em vez de só fechar as sessões com `tmux kill-session`. Fechar a sessão manda
SIGHUP, e o gunicorn trata SIGHUP como "recarregar", não como "sair": ele poderia continuar
rodando escondido, com a porta 5001 e o banco abertos. O `parar.sh` manda o sinal de sair
(SIGTERM), **espera o processo terminar** e só então fecha as sessões `tl-app` e `tl-tunel`.
Ele só encerra processos que rodam na pasta `~/tierlist`, nunca os do convite.

Não rode `termux-wake-unlock`: o convite também depende do wake lock.

Depois de reiniciar o celular ou o Termux, rode o `bash iniciar.sh` de novo.

---

## 6. Como jogar

1. Abra `https://<endereço>/admin` e entre com o `ADMIN_TOKEN`.
2. **Nova partida**: escolha o **modo** ("Ao vivo" já vem marcado), o tema (a prévia mostra as
   imagens; as que não carregarem ficam em vermelho), o número de rodadas (no outro modo, o número
   de itens), as faixas e os nomes dos jogadores (um por linha). Não dá para adicionar jogadores depois.
3. Na tela da partida, copie o link de cada jogador e mande para ele. Cada link é pessoal.

**Como a faixa de um item é decidida (nos dois modos): regra da maioria.**

- O item vai para a faixa que recebeu mais votos.
- **Empate**: vai para a **pior** das faixas empatadas. Exemplo: 2 votos em A e 2 em B → B.
- Quem pulou não conta. Se ninguém classificou o item, ele vai para **Itens pulados**.

### Modo ao vivo

1. Quando o pessoal tiver entrado (bolinha verde), clique em **Iniciar partida**.
2. A rodada fecha sozinha quando todos votaram, ou quando todos os que estão **online** votaram
   ou pularam. Quem fechou a página fica offline em uns 15 segundos e não trava o jogo.
   No resultado, todos apertam **Continuar**.
3. Se alguém ficar parado com a página aberta, o botão de avançar diz o que vai acontecer
   (sempre com confirmação):
   - **Fechar a votação agora**: quem ainda não votou fica de fora. Se ninguém tiver votado, o
     item vai para os pulados;
   - **Ir para a próxima rodada**: sai do resultado e abre a votação seguinte;
   - **Encerrar a partida**: sai do resultado da última rodada.

### Modo "Cada um no seu ritmo"

Não há **Iniciar**: a partida já nasce **aberta** e cada um joga quando quiser.

1. **O jogador** vê um item por vez, com os botões das faixas, **Pular** e **Voltar**, e o progresso
   ("3 de 12"). Cada resposta é salva na hora: dá para fechar a página e continuar depois.
   - Tocar num item de "Sua tier list até agora" volta nele para trocar a resposta.
   - **Finalizar** só libera com todos os itens respondidos (pular também conta como resposta).
     Pede confirmação e, depois, as respostas não mudam mais.
2. **Antes de finalizar**, o jogador não vê nada dos outros.
3. **Depois de finalizar**, o jogador vê:
   - a sua **compatibilidade** com a tier list geral;
   - a tier list geral, feita só com quem já finalizou, e a sua;
   - a lista de cada um que já finalizou;
   - "Faltam: ..." com quem ainda não finalizou.

   A tela se atualiza sozinha a cada 5 segundos.
4. **Compatibilidade**: só entram os itens que o jogador e a tier list geral classificaram.
   - Para cada um desses itens, a nota é `1 - distância / (número de faixas - 1)`. Com 5 faixas,
     mesma faixa = 100%, uma faixa de diferença = 75%, e assim por diante.
   - O resultado é a média das notas, arredondada.
   - Sem nenhum item em comum, aparece "—".
5. **A partida encerra** sozinha quando todos os jogadores finalizaram, ou quando o admin clica em
   **Encerrar e revelar**.
   - Quem não tinha finalizado fica de fora do resultado.
   - Se ninguém finalizou, a confirmação avisa que o resultado ficará vazio.
6. **O admin** vê o progresso de cada jogador ("7 de 12", "finalizou") e a tier list geral.
   Também pode abrir a lista de cada jogador, inclusive as incompletas.

### Remover um jogador (nos dois modos)

Na tela da partida, cada jogador tem um botão **Remover**. Ele pede confirmação e **não tem volta**.

- O link do removido passa a mostrar "Você foi removido desta partida".
- A partida segue na hora sem ele: se ele era o único que faltava, a rodada fecha (ao vivo) ou a
  partida encerra (no outro modo).
- **Ao vivo**: o voto dele na votação em andamento é descartado. As rodadas já fechadas ficam como estão.
- **Cada um no seu ritmo**: as respostas dele deixam de entrar em todos os resultados.
- Não dá para remover o último jogador ativo, nem remover alguém depois que a partida terminou.

---

## 7. Backup do banco

O banco é o arquivo `~/tierlist/tierlist.db`, em modo WAL: parte dos dados recentes pode estar
no arquivo `tierlist.db-wal` ao lado. Por isso **não** faça backup com `cp tierlist.db`, porque a
cópia pode sair sem os dados recentes ou incompleta. Use a cópia do próprio SQLite, que funciona
**com o app rodando** e junta tudo num arquivo só (cole o bloco inteiro no Termux):

```bash
cd ~/tierlist && mkdir -p backups && python - <<'FIM'
import os, sqlite3, time
if not os.path.exists("tierlist.db"):
    raise SystemExit("ERRO: tierlist.db não encontrado. Rode este comando dentro de ~/tierlist.")
destino = time.strftime("backups/tierlist-%Y%m%d-%H%M%S.db")
origem = sqlite3.connect("tierlist.db")
copia = sqlite3.connect(destino)
origem.backup(copia)                      # cópia consistente, mesmo com o app rodando
resultado = copia.execute("PRAGMA integrity_check").fetchone()[0]
copia.close()
origem.close()
print("backup salvo em", destino, "| verificação:", resultado)   # o esperado é "ok"
FIM
```

Para trazer os backups para o PC (no PowerShell):

```powershell
mkdir backups -Force
scp -P 8022 "u0_a123@192.168.100.3:tierlist/backups/*" .\backups\
```

Para **restaurar** um backup (substitui o estado atual; se quiser guardá-lo, faça antes um backup
dele com o bloco acima):

```bash
cd ~/tierlist
bash parar.sh                                     # PRECISA terminar com "Tier List parado."
cp backups/tierlist-AAAAMMDD-HHMMSS.db tierlist.db
rm -f tierlist.db-wal tierlist.db-shm
bash iniciar.sh
```

A ordem importa: com o app ainda rodando, trocar o `tierlist.db` e apagar o `-wal` dele pode
corromper o banco. Por isso o `parar.sh` só termina depois que o app saiu de verdade. Se ele
mostrar `ERRO`, **não** siga para o `cp`.

---

## 8. Formato do temas.json

```json
{
  "temas": [
    {
      "nome": "Pokémon mais famosos",
      "itens": [
        { "nome": "Pikachu", "imagem": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/25.png" },
        { "nome": "Charizard", "imagem": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/6.png" }
      ]
    }
  ]
}
```

Regras de cada tema:

- `nome` não pode ser vazio nem repetir outro tema (maiúsculas e minúsculas contam como iguais);
- `itens` com pelo menos 2 itens;
- cada item com `nome` não vazio (sem repetir dentro do tema) e `imagem` começando com `https://` ou `http://`.

Como funciona:

- O arquivo é lido **toda vez que você abre a tela de nova partida**: dá para editar sem reiniciar.
- Se o JSON estiver quebrado, a tela mostra a linha e a coluna do erro.
- Temas com problema aparecem marcados, com o motivo, e não podem ser escolhidos.
- As imagens são carregadas pelos celulares dos jogadores direto da URL. O servidor nunca as baixa.
- Ao criar a partida, os itens são **copiados** para o banco: editar o `temas.json` depois não muda
  partidas já criadas.

Para editar no celular: `nano ~/tierlist/temas.json`. Para validar o JSON antes de abrir o painel:
`python -m json.tool ~/tierlist/temas.json > /dev/null && echo ok`.

---

## 9. Problemas comuns

| Sintoma | O que fazer |
| --- | --- |
| `ERRO: .env com final de linha do Windows (CRLF)` (ou outro arquivo) | `sed -i 's/\r$//' .env` (troque pelo nome do arquivo indicado) |
| `bash iniciar.sh` dá `$'\r': command not found` | O próprio script veio com CRLF: `sed -i 's/\r$//' iniciar.sh` |
| `ERRO: não achei 'tmux'` (ou outro programa) | Refaça a seção 4 (`pkg install ...` / `pip install ...`) |
| `ERRO: o app não respondeu` | `tmux attach -t tl-app` mostra o motivo. O mais comum: `ADMIN_TOKEN` ou `SECRET_KEY` vazio ou ainda com o valor de exemplo |
| `O banco ... foi criado por uma versão de teste antiga do app` | É um banco de antes da versão 1 final, que não tem migração automática. Se for só teste: `bash parar.sh`, depois `rm -f tierlist.db tierlist.db-wal tierlist.db-shm` e `bash iniciar.sh` (**perde todas as partidas**). Se quiser manter os dados: **não apague**; faça backup (seção 7) e peça uma migração |
| `O banco ... é da versão N do esquema, mais nova que este app` | Os arquivos do app no celular são mais antigos que o banco. Envie os arquivos atuais (seção 3) |
| `O backup ... saiu com problema ... Migração cancelada.` | A migração nem começou e o banco não mudou. Veja se há espaço livre (`df -h ~`) e rode `bash iniciar.sh` de novo |
| `ERRO: a porta 5001 continua respondendo depois de parar` | Algum processo antigo ficou rodando. `tmux ls` mostra as sessões; se o `parar.sh` não resolver, reinicie o Termux e rode `bash iniciar.sh` |
| `ERRO: o app (PID ...) não parou em 20 s` | `tmux attach -t tl-app` para ver o que ele está fazendo. Não restaure backup enquanto isso não se resolver |
| Os jogadores dizem que o link não abre | O túnel reiniciou e o endereço mudou: copie os links de novo na tela da partida |
| O painel diz "Não consegui descobrir o endereço público" | O túnel ainda não subiu ou caiu: `tmux attach -t tl-tunel`. Depois recarregue a página |
| Um jogador aparece offline com a página aberta | O celular dele pode ter desligado a tela ou perdido a rede. Ao voltar, ele reaparece sozinho |

---

## 10. Atualizar da versão 1 para a 2 sem perder o banco

A versão 2 muda o formato do banco. **A migração é automática**: quando o app sobe e encontra um
banco da versão 1, ele faz o seguinte sozinho.

1. Salva uma cópia de segurança em `backups/tierlist-antes-v2-AAAAMMDD-HHMMSS.db` e confere essa
   cópia. Se a cópia der problema, a migração nem começa.
2. Migra tudo numa transação só: se algo falhar no meio, o banco fica exatamente como estava.
3. Todas as partidas antigas ficam no modo **ao vivo**, com votos, faixas e resultados iguais.

Da segunda vez em diante, não faz nada.

### Passo 1 (recomendado): ensaiar no PC com uma cópia do banco real

No Termux, faça um backup com o bloco da seção 7 (pode ser com o app rodando). Anote o nome que
ele mostrar. Depois, no PowerShell do PC:

```powershell
cd C:\Users\Legion\Documents\f\teste\tierlist
mkdir teste-migracao -Force
scp -P 8022 "u0_a123@192.168.100.3:tierlist/backups/tierlist-AAAAMMDD-HHMMSS.db" .\teste-migracao\
.\.venv\Scripts\python ferramentas\conferir_migracao.py teste-migracao\tierlist-AAAAMMDD-HHMMSS.db
```

(Troque `AAAAMMDD-HHMMSS` pelo nome que o backup mostrou.)

O script não altera o arquivo informado. Ele migra uma cópia (`...-migrado.db`), compara todos os
dados antes e depois e roda a migração de novo para ver que ela não muda mais nada.

- **Todas as linhas com `ok`**: pode seguir.
- **Alguma linha com `FALHOU`**: **não** atualize o celular. Guarde a saída e peça ajuda.

### Passo 2: atualizar o celular

No Termux, pare o app (precisa terminar com "Tier List parado."):

```bash
cd ~/tierlist && bash parar.sh
```

No PowerShell do PC, envie os arquivos com o mesmo `scp` da seção 3. A lista já inclui o arquivo
novo `individual.py` e não inclui o banco.

No Termux, suba de novo. É aqui que a migração acontece:

```bash
cd ~/tierlist && bash iniciar.sh
```

### Passo 3: conferir

No Termux:

```bash
cd ~/tierlist
ls backups/                      # deve aparecer tierlist-antes-v2-...db
python -c "import sqlite3; c = sqlite3.connect('tierlist.db'); print(c.execute('PRAGMA user_version').fetchone()[0], c.execute('PRAGMA integrity_check').fetchone()[0])"
```

O esperado é `2 ok`. Abra o painel: as partidas antigas aparecem com o modo "Ao vivo".

Se o `iniciar.sh` mostrar `ERRO: o app não respondeu`, o motivo aparece em `tmux attach -t tl-app`.
Se foi a migração que falhou, o banco continua na versão 1, sem mudança nenhuma.

**Para voltar à versão 1** (só se precisar):

> **Atenção:** o banco volta a ser exatamente o do backup. Tudo o que foi feito depois da
> migração (partidas novas, votos, respostas) **se perde**. Se quiser guardar esse estado,
> faça antes um backup dele com o bloco da seção 7.

A ordem importa. **Não** rode `bash iniciar.sh` antes de enviar os arquivos da versão 1: com os
arquivos da versão 2 ainda no celular, o app migraria o banco restaurado de novo.

1. No Termux, pare o app (precisa terminar com "Tier List parado."):

   ```bash
   cd ~/tierlist && bash parar.sh
   ```

2. Ainda no Termux, restaure o backup de antes da migração **sem iniciar o app**. Troque
   `AAAAMMDD-HHMMSS` pelo nome que o `ls backups/` mostrar:

   ```bash
   cd ~/tierlist
   cp backups/tierlist-antes-v2-AAAAMMDD-HHMMSS.db tierlist.db
   rm -f tierlist.db-wal tierlist.db-shm
   ```

3. No PowerShell do PC, tire os arquivos da versão 1 do Git (commit `2102c04`) para uma pasta
   separada e envie de lá:

   ```powershell
   cd C:\Users\Legion\Documents\f\teste\tierlist
   git -c safe.directory='C:/Users/Legion/Documents/f/teste/tierlist' archive --format=zip -o ..\tierlist-v1.zip 2102c04
   Expand-Archive ..\tierlist-v1.zip -DestinationPath ..\tierlist-v1 -Force
   cd ..\tierlist-v1
   scp -P 8022 -r app.py banco.py endereco.py jogo.py rotas_admin.py rotas_jogador.py temas.py temas.json requirements.txt iniciar.sh parar.sh .env.example templates static u0_a123@192.168.100.3:tierlist/
   ```

   O `individual.py` e os arquivos novos de `static/` que ficam no celular não atrapalham: a
   versão 1 não os usa.

4. Só agora, no Termux, inicie:

   ```bash
   cd ~/tierlist && bash iniciar.sh
   ```
