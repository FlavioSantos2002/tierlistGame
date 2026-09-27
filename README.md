# Tier List em grupo

Jogo para jogar com amigos, cada um no próprio celular. A cada rodada aparece um item (por
exemplo, um Pokémon) e cada jogador vota em qual faixa ele fica (S, A, B, C, D...). Quando a
rodada fecha, todos veem a tier list do grupo atualizada. Sem pontuação e sem cronômetro.

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

---

## 1. Estrutura do projeto

| Arquivo / pasta | Para que serve |
| --- | --- |
| `app.py` | Cria o app Flask, confere as variáveis de ambiente (o gunicorn usa `app:app`) |
| `banco.py` | SQLite: tabelas, uma conexão por requisição, transações `BEGIN IMMEDIATE` |
| `jogo.py` | Regras do jogo: fechamento da rodada, cálculo da faixa, presença online |
| `rotas_admin.py` | Painel do admin: login, partidas, nova partida, controle ao vivo |
| `rotas_jogador.py` | Link do jogador e a API (estado, votar, pular, continuar) |
| `temas.py` | Leitura e validação do `temas.json` |
| `endereco.py` | Descobre o endereço público do túnel para montar os links |
| `templates/`, `static/` | HTML, CSS e JavaScript (sem frameworks) |
| `temas.json` | Temas e itens do jogo (seção 8) |
| `iniciar.sh` | Sobe (ou reinicia) tudo no Termux |
| `parar.sh` | Para o app e o túnel com segurança (também usado pelo `iniciar.sh`) |
| `tests/` | Testes automáticos (só no PC) |

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
nenhum dos dois, eles são pulados.

---

## 3. Enviar para o celular

Do PowerShell do PC (troque o usuário e o IP se forem outros):

```powershell
cd C:\Users\Legion\Documents\f\teste\tierlist
ssh -p 8022 u0_a123@192.168.100.3 "mkdir -p ~/tierlist"
scp -P 8022 -r app.py banco.py endereco.py jogo.py rotas_admin.py rotas_jogador.py temas.py temas.json requirements.txt iniciar.sh parar.sh .env.example templates static u0_a123@192.168.100.3:tierlist/
```

- **Não** envie `.venv`, `tests`, `__pycache__` nem o `.env` do PC. O `.env` do celular é criado lá (seção 4).
- **Cuidado com o `temas.json`**: se você editou esse arquivo no celular, reenviar o do PC apaga a edição.
- Todos os arquivos precisam ter final de linha **LF**. O projeto já está assim (`.gitattributes` e
  `.editorconfig`). Se editar no Windows, use um editor que respeite o `.editorconfig`
  (o VS Code respeita), nunca o Bloco de Notas.

Para **atualizar** o app depois de mudar o código: rode o mesmo `scp` e depois `bash iniciar.sh` no celular.

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
2. **Nova partida**: escolha o tema (a prévia mostra as imagens; as que não carregarem ficam em
   vermelho), o número de rodadas, as faixas e os nomes dos jogadores (um por linha).
3. Na tela da partida, copie o link de cada jogador e mande para ele. Cada link é pessoal.
4. Quando o pessoal tiver entrado (bolinha verde), clique em **Iniciar partida**.
5. A rodada fecha sozinha quando todos votaram, ou quando todos os que estão **online** votaram
   ou pularam. Quem fechou a página fica offline em uns 15 segundos e não trava o jogo.
   No resultado, todos apertam **Continuar**.
6. Se alguém ficar parado com a página aberta, use **Forçar avanço**.

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
| `O banco ... foi criado por uma versão antiga do app` | O formato do banco mudou numa atualização. Se for só teste: `bash parar.sh`, depois `rm -f tierlist.db tierlist.db-wal tierlist.db-shm` e `bash iniciar.sh` (**perde todas as partidas**). Se quiser manter os dados: **não apague**; faça backup (seção 7) e peça uma migração |
| `ERRO: a porta 5001 continua respondendo depois de parar` | Algum processo antigo ficou rodando. `tmux ls` mostra as sessões; se o `parar.sh` não resolver, reinicie o Termux e rode `bash iniciar.sh` |
| `ERRO: o app (PID ...) não parou em 20 s` | `tmux attach -t tl-app` para ver o que ele está fazendo. Não restaure backup enquanto isso não se resolver |
| Os jogadores dizem que o link não abre | O túnel reiniciou e o endereço mudou: copie os links de novo na tela da partida |
| O painel diz "Não consegui descobrir o endereço público" | O túnel ainda não subiu ou caiu: `tmux attach -t tl-tunel`. Depois recarregue a página |
| Um jogador aparece offline com a página aberta | O celular dele pode ter desligado a tela ou perdido a rede. Ao voltar, ele reaparece sozinho |
