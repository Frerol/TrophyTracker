# RetroCheevos — Handoff de sessão

Estado do projecto para retomar numa sessão nova sem contexto prévio.
Última actualização: fim do Bloco 10.

---

## 0. Contexto rápido para quem chega agora

App de desktop (Python 3.14 + PySide6) que acompanha uma conta
RetroAchievements: catálogo pesquisável, jogos instalados localmente,
progresso, eventos e lançamento em emulador.

- **Correr:** `.venv/Scripts/python.exe -m retrocheevos.main` (ou `src/retrocheevos/main.py`)
- **BD:** `database/retrocheevos.db` (SQLite), migrações em `src/retrocheevos/database/migrations.py` — **versão actual: 14**
- **Camadas:** `gui/` → `services/` → `core/` → `database/` + `api/`. A GUI nunca fala com `api/` directamente.
- **Testes:** só existem em `tests/library/`, e **não há `pytest` instalado no venv**. A verificação tem sido feita com `py_compile`, import da app inteira, e scripts pontuais contra a BD real e a API ao vivo.
- **Nota:** os documentos em `docs/` (UI.md, Architecture.md, Database.md, DevelopmentRoadmap.md) descrevem parcialmente estados já ultrapassados. Este ficheiro é a fonte mais actual.

---

## 1. Onde estamos: Bloco 10 (concluído)

O trabalho está organizado em blocos numerados. Os blocos 1 a 9 estão
feitos. O **Bloco 10** (correcções e ajustes de UI) está concluído.

### Feito e verificado no Bloco 10

| # | Item | Estado |
|---|---|---|
| 1 | Barra de sync sempre visível (não colapsa com a pesquisa) | ✅ |
| 2 | Continue Playing a 6 colunas + barra lateral mais larga | ✅ |
| 3 | Secção de badges removida da Home | ✅ |
| 4+8 | Dropdown de consolas removido; `sync_median_times` global | ✅ |
| 5 | Ícone da app com 7 resoluções pré-escaladas (16→256) | ⚠️ ver §4 |
| 6 | Barras de progresso em escala fixa 0-100 com percentagem | ✅ |
| 7 | Opção "All" no filtro Type, com exclusão mútua | ✅ |
| 9 | Botão "Beaten Games Leaderboard" (abre no browser) | ✅ |

### Segunda ronda de correcções do Bloco 10

| # | Item | Estado |
|---|---|---|
| 1 | Larguras trocadas (barra lateral espalmada) | ✅ era `setMaximumWidth` sem `setMinimumWidth` |
| 2 | Faltava o 6º jogo no Continue Playing | ✅ era o Diablo a 100%, excluído por regra |
| 3 | Botão "Leaderboards" fora da navegação | ✅ página apagada |
| 4 | Formato "1.5h (n=33)" | ✅ agora "1h 30m" |
| 5 | Botão Download ainda visível | ✅ removido a sério (sinal, handler, pintura) |
| 6 | Falta barra de progresso visual no Continue Playing | ✅ voltou a ser `QProgressBar` |
| 7 | Estatísticas diferentes do site | ✅ ver §2 |

---

## 2. O que falta — leitura honesta do estado

> **Atenção:** o pedido que originou este ficheiro listava três pontos como
> "por corrigir". Dois deles **já estão resolvidos e confirmados**; o
> terceiro tem um limite externo que não consigo contornar. O detalhe está
> abaixo, com evidência, para a próxima sessão não repetir trabalho feito.

### 2.1 Estatísticas (Beaten/Mastered/Completion) — ✅ RESOLVIDO E CONFIRMADO

Eram duas causas encadeadas, ambas corrigidas:

1. **A API estava paginada e só líamos a 1ª página.**
   `API_GetUserCompletionProgress.php` devolve no máximo 100 jogos e reporta
   o real em `Total` (confirmado ao vivo: 100 devolvidos, `Total` = 147).
   Todas as estatísticas saíam de dois terços da conta.
   → `api/profile.py::get_user_completion_progress` passou a seguir as páginas.

2. **Jogos *mastered* não contavam como *beaten*.**
   `highest_award_kind` guarda só o prémio **mais alto**, por isso os 46
   masterizados não entravam no total de batidos.
   → `BEATEN_AWARD_KINDS` passou a incluir `completed` e `mastered`.

3. **A correcção não chegava ao ecrã** — a razão pela qual parecia não ter
   funcionado. `profile_stats` é uma cache validada **só por idade**
   (`PROFILE_SYNC_STALE_AFTER = 6h`); a linha tinha 22 minutos, logo era
   considerada fresca e o sync era saltado. Uma cache que só pergunta "que
   idade tem isto?" não detecta uma mudança de *fórmula*.
   → **Migração v14** acrescenta `profile_stats.stats_revision`, comparada
   com `sync_service.PROFILE_STATS_REVISION` (actualmente `1`). Revisão
   diferente ⇒ re-sync forçado, independentemente da idade.

**Evidência de que está resolvido** — estado actual da BD:
```
stored stats: beaten=98 mastered=56 completion=42.21 revision=1
```
(eram 28 / 46 / 63,12 % com revisão 0)

#### Completion% — ✅ RESOLVIDO, bate exactamente (2026-08-06)

O site tem um campo "Average completion" = **56,75 %**. Nenhuma das duas
fórmulas anteriores batia, e os dois erros puxavam em sentidos opostos:

| Fórmula | Valor |
|---|---|
| Média não ponderada, só a 1ª página (original) | 63,12 % |
| `sum(obtidas) / sum(disponíveis)` (ponderada, revisão 1) | 42,21 % |
| Média não ponderada, todos os 147 jogos | 56,37 % |
| **Média não ponderada, todos menos subsets** | **56,75 %** ✅ |

Ou seja: **a média não ponderada estava certa desde o início**. O que a fazia
ler alto era a paginação em falta; trocá-la por um rácio ponderado substituiu
um erro por outro maior. A diferença final de 0,38 pp era uma única linha —
`Dragon Ball Z: Budokai [Subset - Martial Arts Tournament]` a 1,43 %.
Excluída, dá 56,7470 → **56,75 %**, e é coerente com o `_BROWSABLE_GAME_CLAUSES`
que já ignora subsets em todo o lado.

Verificado pelo caminho real do código:
```
games_beaten          : 98      (site: 98)
games_mastered        : 56      (site: 56)
completion_percentage : 56.7470 (site: 56,75 %)
```

**`PROFILE_STATS_REVISION` foi para 2** — sem isso a correcção não chegava ao
ecrã.

**Duas coisas que esta conta não consegue distinguir** (ficam como nota, não
como palpite aplicado): tem 0 pontos softcore, logo `NumAwarded` e
`NumAwardedHardcore` são idênticos em todas as linhas e qualquer um podia ser
o campo que a RA usa; e não tem jogos de evento/standalone (consola 101/102),
logo não dá para saber se a RA também os exclui. Só a exclusão de subsets tem
prova, e só essa foi aplicada.

### 2.2 Recent Activity — ✅ RESOLVIDO E ENCERRADO

Investiguei e **não encontrei avaria**: o `QTimer` arranca no `showEvent`,
pára no `hideEvent` (confirmado por teste headless com `QStackedWidget`), e
o fetch demora ~5,7 s contra a API real, portanto cabe folgadamente no
intervalo.

Melhorias aplicadas mesmo assim:
- Intervalo 60 s → **30 s**
- Refresh **imediato** ao mostrar a página (antes esperava um intervalo
  inteiro se voltasses à janela sem navegar)
- **Bug real corrigido:** uma chamada durante um fetch em curso limpava
  `_activity_entries` sem arrancar worker novo, deixando o ecrã
  dessincronizado do que estava a carregar. Agora sai cedo, antes de tocar
  no estado.

#### Segunda investigação — agora do lado dos **dados** (2026-08-06)

O utilizador reportou que a entrada do Theodoro mostrava `2026-08-06 00:45`
com 74/88, quando antes tinha mostrado `2026-08-06 10:53` com 75/88 — ou
seja, actividade **mais antiga e com menos progresso** do que já aparecera.
Foram verificados ao vivo os três suspeitos apontados:

| Suspeito | Resultado medido |
|---|---|
| Ordenação | `API_GetUserRecentAchievements.php` devolve **estritamente decrescente** (84 linhas verificadas, `dates == sorted(dates, reverse=True)`) |
| Paginação | Não há. Com `m=10080` vêm as 84 linhas da janela; a mais recente está no índice 0 |
| Cache | Duas chamadas seguidas a `API_GetGameInfoAndUserProgress.php` devolvem o mesmo valor; `requests.Session` não cacheia e o serviço não persiste nada |

**A API concorda com o que o ecrã mostra.** O último unlock do Theodoro é
mesmo `2026-08-06 00:45:40` (Jak 3) e o progresso é mesmo `NumAwardedToUser
= 74` de 88. Não existe nenhum unlock às 10:53 nem nenhum 75/88 em lado
nenhum dos dados dele — o único outro jogo na janela de 7 dias é
Metal Gear Solid: Ghost Babel, que está a 13/106, portanto não é confusão
de jogo.

**Explicação mais provável do 75/88 anterior:** a RA revogou/repôs um
unlock. 74 + 1 = 75 e de volta a 74, com o unlock das 10:53 a desaparecer,
é internamente consistente e não é detectável pela API. A app estava certa
das duas vezes.

#### Bug real encontrado nesta ronda: fuso horário

`API_GetUserRecentAchievements.php` devolve `Date` **em UTC**, sem offset —
provado por cruzamento: o award `2026-08-05T10:11:40+00:00` (jogo 757,
`API_GetUserAwards.php`, offset explícito) é o mesmo evento que este
endpoint reporta como `2026-08-05 10:11:40`. O `ActivityEntryCard` imprimia
esse valor em bruto, logo mostrava **menos uma hora** do que o relógio local
(UTC+1) — que é exactamente o aspecto de "dados velhos".

> **Nota:** o `_as_utc()`/`_format_local()` descritos aqui foram
> **revertidos** mais abaixo, por decisão do utilizador — hoje mostra-se UTC
> em bruto. O facto de os timestamps serem UTC continua verdadeiro e provado.

Correcções aplicadas (parcialmente revertidas — ver acima):
- `api/profile.py` — `_as_utc()` marcava os timestamps naive como UTC.
- `widgets/activity_entry_card.py` — `_format_local()` convertia para o fuso
  da máquina antes de imprimir.
- `services/activity_feed_service.py` — `_latest_unlock()` escolhe o unlock
  mais recente **por timestamp**, já não por `[0]`. A ordenação da RA está
  certa hoje mas não é documentada, e confiar na posição era precisamente o
  que produziria o sintoma reportado.

#### Quarta ronda — o card passou a girar à volta do **jogo**, não do unlock

Pedido: tirar a linha "Last unlock" e pôr o último/actual jogo por baixo do
"Last seen". Isso mudou a *fonte* dos dados, não só a ordem:

- O jogo vinha de `API_GetUserRecentAchievements.php` — era o jogo do
  **último unlock**. Passou a vir do `LastGame` do `API_GetUserSummary.php`,
  que é o jogo que a pessoa esteve mesmo a jogar. Não são a mesma coisa: uma
  sessão pode durar horas sem desbloquear nada.
- Isso tornou a chamada a `get_recent_achievements` desnecessária no feed, e
  com ela o campo `last_achievement_at` e o `_latest_unlock`. **Passou de 3
  para 2 chamadas por utilizador** — com ~31 utilizadores e 0,3 s de
  intervalo, é cerca de um terço menos de tempo por refresh.
- `RawUserSummary` ganhou `last_game_title` / `last_game_console` /
  `last_game_icon_path`. A ordenação (`core/activity_feed.py`) já era por
  `last_seen_at` e deixou de ter fallback para o unlock.

O card ficou: utilizador → "Last seen" → jogo (ícone, título, consola) →
progresso → rich presence. Verificado com o payload real do summary:

```
Theodoro
    Last seen: 2026-08-06 18:09
    Jak 3 — PlayStation 2
    75/88 achievements | Played 19h31m
    Story Missions: 60/60 | Orbs: 449
```

#### Menu "+" marca as listas onde o jogo já está

`ActionsDelegate.set_membership_provider(fn)` — `fn(game_id) -> set[list_id]`,
fornecido pela `ExplorerPage`. **Callback e não um dicionário empurrado**: a
tabela tem milhares de linhas e pré-calcular a pertença de todas para
responder a um menu seria trabalho deitado fora; assim só corre quando o
menu abre, que já era construído tardiamente.

As entradas não marcadas levam um ` ` (figure space) em vez de nada,
senão as marcadas deslocam-se para a direita e o menu fica desalinhado. Não
se usaram acções *checkable* do Qt de propósito: clicar **adiciona** à lista,
e uma caixa de visto lê-se como um interruptor que também tiraria.

#### Terceira ronda — a causa real: **"Last seen" ≠ "último unlock"**

O utilizador comparou lado a lado: site dizia `Last seen 06 Aug 2026, 17:21`,
a app dizia `Last activity: 2026-08-06 01:45`. 16 horas de diferença.

**Não era cache nem filtro nem ordenação — eram dois relógios diferentes.**
A app mostrava a hora do último *unlock*; o site mostra a hora em que a
pessoa esteve pela última vez a *jogar*. O Theodoro estava em sessão há
horas sem desbloquear nada, por isso os dois números divergiram muito.

`API_GetUserProfile.php` **não tem** campo de "last seen" nenhum — foi por
isso que o feed acabou a usar o unlock. `API_GetUserSummary.php` tem:

```
RichPresenceMsgDate          = 2026-08-06 17:31:50   <- é este
RecentlyPlayed[0].LastPlayed = 2026-08-06 17:31:50   <- concorda
LastActivity.lastupdate      = None                  <- beco sem saída
```

Cuidado com o `LastActivity`: parece o candidato óbvio e **todas as chaves
vêm a null**. Usa-se `RichPresenceMsgDate` por ser um campo simples, em vez
do primeiro elemento de uma lista que vem vazia para quem nunca jogou.

Correcções:
- `api/profile.py` — `get_user_summary()` + `RawUserSummary`
- `models/activity_feed.py` — campo `last_seen_at` a par de `last_achievement_at`
- `services/activity_feed_service.py` — usa o summary em vez do profile
  (mesmo número de chamadas: 3 por utilizador)
- `core/activity_feed.py` — ordena por `last_seen_at`, como a página Following
- `widgets/activity_entry_card.py` — duas linhas, "Last seen" e "Last unlock"

Verificado ponta a ponta contra a API ao vivo:
```
Theodoro   seen=2026-08-06 18:36  unlock=2026-08-06 18:36  75/88  Jak 3
Gmendes    seen=2026-08-06 08:23  unlock=2026-08-05 11:11  1/31   DBZ: Taiketsu
Zynlar     seen=2026-07-30 02:14  unlock=-
```
(a linha do Gmendes mostra bem a diferença entre os dois relógios)

#### Fusos horários — decidido: **mostrar UTC em bruto, sem converter**

**Decisão final do utilizador (2026-08-06), depois de todo o percurso abaixo:
o Recent Activity mostra o valor exactamente como a API o devolve, sem
qualquer conversão de fuso.** A conversão UTC→local foi removida:

- `api/profile.py` — o helper `_as_utc` foi **apagado**; `get_user_summary` e
  `get_recent_achievements` devolvem datas naive, tal como a RA as manda.
- `widgets/activity_entry_card.py` — `_format_local` deu lugar a
  `_format_timestamp`, que imprime sem `astimezone()`.
- `core/activity_feed.py` — a ordenação deixou de usar `datetime.timestamp()`
  (que lê datas naive como hora *local*) e passa a subtrair `_SORT_EPOCH`, para
  a ordem não depender do fuso da máquina.

Verificado ao vivo: `API raw = 2026-08-06 18:41:51` → `card shows =
2026-08-06 18:41`, idêntico.

**Consequência assumida:** a app fica uma hora atrás do relógio local em
UTC+1 — quem foi visto há um minuto aparece como "há uma hora". Isto é
intencional; o critério escolhido foi **bater certo com o site**, não com o
relógio de parede. Não voltar a introduzir `astimezone()` aqui.

##### Percurso até esta decisão (para não se repetir a investigação)

Houve três rondas a reportar a app como "1 h adiantada" face ao site. O
diagnóstico técnico dessas rondas mantém-se válido e é o que justifica os
comentários no código:

**O site mostra as horas em UTC, em formato absoluto, igual ao valor cru da
API** — confirmado pelo utilizador com o print da página Following. Quando a
app convertia para local, ambas estavam correctas, cada uma no seu fuso; a
diferença de uma hora era esperada, não um bug. A decisão acima elimina a
divergência escolhendo o fuso do site.

**A API devolve sempre UTC, independentemente do Locale da conta RA** —
testado com a preferência antes e depois de mudada para Lisboa, o output não
mexeu.

##### Como provar isto sem cair em raciocínio circular

O primeiro argumento usado aqui **não servia**: "o campo está a segundos do
`utc now`, logo é UTC" pressupõe que a pessoa estava a jogar naquele
instante, e essa premissa vinha de assumir que o campo era UTC. Com "esteve
online há 1 hora" as duas leituras encaixam igualmente bem. Os dois
argumentos abaixo são independentes disso.

**1. O campo avança em tempo real.** Três leituras do mesmo `RichPresenceMsgDate`:

| Medição (UTC) | Valor lido | Distância |
|---|---|---|
| 17:54:00 | 17:53:51 | 9 s |
| 18:07:42 | 18:05:51 | 1m51s |
| 18:11:40 | 18:09:51 | 1m49s |

Subiu 4m00s enquanto passavam 3m58s de relógio. Um "last seen" de há uma hora
é um evento passado e fixo — **não avança**. Este está colado ao presente.

**2. Cruzamento com um unlock cujo fuso já está provado.** Entre a 1ª e a 2ª
medição apareceu uma conquista nova, a `264251` às `17:58:29` — mesmo campo
`Date` que se provou ser UTC contra o `API_GetUserAwards` (offset `+00:00`
explícito). O `LastPlayed` do mesmo jogo 3065 marcava `18:09:51`. Se esse
campo fosse hora de Lisboa, valeria `17:09:51` em UTC, ou seja **49 minutos
antes de um unlock nesse mesmo jogo** — impossível.

**Regra prática:** nunca inferir o fuso a partir da diferença app-vs-site.
Ancorar sempre num evento cujo fuso já está provado (um unlock), ou medir o
campo duas vezes e ver se avança.

Se voltar a parecer desactualizado, resta olhar para
`RECENT_ACHIEVEMENTS_WINDOW_MINUTES = 7 dias` e `FOLLOWED_USERS_LIMIT = 30`
em `activity_feed_service.py`.

### 2.3 Sync de tempos médios — ⚠️ LIMITE EXTERNO, não contornável

**Isto não foi entregue como pedido, e é importante que a próxima sessão não
volte a tentar as mesmas abordagens.** Foram testadas ao vivo:

| Estratégia | Resultado medido |
|---|---|
| Sequencial 0,30 s | ~3,3 jogos/s — estável |
| Sequencial 0,25 s | **8 de 60 com HTTP 429** |
| Sequencial 0,10 s | **429 ao fim de ~9 chamadas** |
| 4 threads em paralelo, 0,30 s cada | **26 de 40 com 429** |

O limitador da RetroAchievements é sobre a **taxa total**, não por ligação —
paralelizar piora. O tecto real é ~3 pedidos/segundo, logo ~11.800 jogos
≈ 1 hora. Acelerar mais implica arriscar bloqueio da conta.

**Mitigação aplicada:** `GameRepository.list_ids_missing_median_time()`
passou a ordenar por relevância — (1) jogos instalados, (2) jogos de
consolas de que há ROMs, (3) o resto. Os 6 jogos instalados ficam prontos em
~2 s, tornando o filtro útil para a biblioteca real quase de imediato,
mesmo com o resto ainda a decorrer. Também aguenta 429 com recuo
exponencial (1 s, 2 s, 4 s) em vez de abortar a corrida inteira.

**Alternativa por decidir com o utilizador:** limitar o backfill às consolas
de que ele tem ROMs, em vez do catálogo inteiro — passaria de ~11.800 para
algumas centenas de jogos. Foi proposto e ainda não teve resposta.

---

## 3. Ficheiros tocados nestas últimas correcções

**Estatísticas (§2.1):**
- `src/retrocheevos/api/profile.py` — paginação + `COMPLETION_PROGRESS_PAGE_SIZE`
- `src/retrocheevos/core/profile_stats.py` — `BEATEN_AWARD_KINDS`, completion ponderada
- `src/retrocheevos/database/schema.py` — `ALTER_TABLES_V14`
- `src/retrocheevos/database/migrations.py` — registo da v14
- `src/retrocheevos/models/profile.py` — campo `stats_revision`
- `src/retrocheevos/database/repositories/profile_repository.py` — persistir/ler a coluna
- `src/retrocheevos/services/sync_service.py` — `PROFILE_STATS_REVISION` + invalidação

**Recent Activity (§2.2):**
- `src/retrocheevos/gui/pages/home_page.py` — intervalo, `showEvent`, guarda de reentrância
- `src/retrocheevos/api/profile.py` — `get_user_summary`, `RawUserSummary`, datas naive
- `src/retrocheevos/services/activity_feed_service.py` — `_latest_unlock`, usa o summary
- `src/retrocheevos/models/activity_feed.py` — campo `last_seen_at`
- `src/retrocheevos/core/activity_feed.py` — ordena por `last_seen_at`, `_SORT_EPOCH`
- `src/retrocheevos/widgets/activity_entry_card.py` — `_format_timestamp`, "Last seen"/"Last unlock"

**Tempos médios (§2.3):**
- `src/retrocheevos/database/repositories/game_repository.py` — ordenação por prioridade
- `src/retrocheevos/services/sync_service.py` — `_fetch_median_time_with_retry`, backoff

**Bloco 11 (§5):**
- `src/retrocheevos/gui/pages/rom_location_page.py` — **novo** (substitui `library_page.py`)
- `src/retrocheevos/services/library_service.py` — `scan_rom_folder`, `_hash_in_place`
- `src/retrocheevos/models/library.py` — `RomFolderScanResult` (substitui os `WatchFolder*`)
- `src/retrocheevos/gui/pages/settings_page.py` — 2 secções removidas
- `src/retrocheevos/gui/main_window.py` + `gui/pages/home_page.py` — chave `rom_location`
- `src/retrocheevos/library/console_detection.py`, `gui/dialogs/match_rom_dialog.py` — docstrings

**Restantes correcções do Bloco 10:**
- `src/retrocheevos/gui/main_window.py` — `NAV_ITEMS = ["Home"]`
- `src/retrocheevos/gui/pages/leaderboards_page.py` — **apagado**
- `src/retrocheevos/gui/pages/explorer_page.py` — Download removido, barra sempre visível
- `src/retrocheevos/gui/delegates/explorer_delegates.py` — sem `download_requested`
- `src/retrocheevos/gui/models/explorer_table_model.py` — formato "1h 30m"
- `src/retrocheevos/widgets/continue_playing_game_row.py` — `QProgressBar` de volta
- `src/retrocheevos/core/dashboard.py` — deixa de excluir jogos a 100%
- `src/retrocheevos/main.py` — ícone multi-resolução

---

## 4. Decisões e descobertas importantes (não repetir investigação)

- **Paginação da API** — `API_GetUserCompletionProgress.php` corta aos 100 e
  reporta `Total`. Se outro endpoint parecer truncado, verificar
  `Count`/`Total` antes de assumir que os dados estão errados.
- **`API_GetUserSummary.php` é o endpoint rico.** Numa só chamada traz
  `UserPic`, `RichPresenceMsg`, `RichPresenceMsgDate` ("last seen"),
  `LastGame` (título/consola/ícone), `Awarded` (obtidas/totais do último
  jogo) e `RecentAchievements`. Cobre tudo o que o feed precisa **menos o
  playtime**, que continua a obrigar a `API_GetGameInfoAndUserProgress.php`.
  Optimização por fazer, se algum dia interessar: 3 chamadas/utilizador → 2.
- **Timestamps naive da RA são UTC.** Provado por cruzamento entre
  `API_GetUserAwards.php` (offset explícito `+00:00`) e
  `API_GetUserRecentAchievements.php` (naive) para o mesmo evento. Qualquer
  campo novo de data que venha sem offset deve ser tratado como UTC e
  convertido só na camada de apresentação.
- **Rate limit** — ~3 pedidos/segundo é o tecto. `CATALOG_SYNC_CALL_DELAY_SECONDS
  = 0.3` está perto do mínimo viável. Não paralelizar.
- **Qualquer chamada nova à API tem de passar por `_with_rate_limit_retry`.**
  O espaçamento sozinho não chega: reduz a probabilidade de 429, não a
  elimina. Só o sync de tempos médios tinha recuo exponencial; `sync_consoles`,
  `sync_games_for_console`, `sync_profile` (3 chamadas seguidas sem pausa
  nenhuma) e o progresso de eventos não tinham, e um único 429 abortava um
  "Sync Everything" inteiro. Pior no sítio pior: uma conta nova faz a maior
  sincronização de todas (~84 + 3 + ~237 pedidos), portanto é a mais provável
  de disparar o limitador e a que menos pode perder a corrida.
  Duas políticas distintas ao esgotar as tentativas, de propósito:
  `_with_rate_limit_retry` **relança** (um console em falta é um buraco no
  catálogo que ninguém repara nem repara depois), `_fetch_median_time_with_retry`
  devolve `None` (uma célula vazia que a próxima corrida volta a oferecer).
- **`API_GetGameProgression.php` existe** e devolve `MedianTimeToBeatHardcore`
  (confirmado ao vivo, ex.: Diablo → 326 s). Um pedido por jogo.
- **`achievements` / `user_achievements` estão sempre vazias.** `sync_game_details`
  e `sync_account_progress` **não têm chamadores em lado nenhum**. Por isso
  `AchievementRepository.get_mastered_game_ids()` devolve sempre `set()` — está
  documentado no próprio método. Qualquer filtro de mastery deve usar
  `GameCompletionRepository.get_finished_game_ids()`, que lê `highest_award_kind`.
- **Contagem do catálogo** — 12.041 sincronizados vs 11.307 no site. A diferença
  são 237 Events (consola 101) + 13 Standalone (102) + 498 subsets
  (`[Subset - …]`). Excluídos os três: 11.304. As exclusões vivem em
  `_BROWSABLE_GAME_CLAUSES` (`game_repository.py`), partilhadas por
  `search()` e `count_all()` para os dois números não divergirem.
- **Eventos são jogos** na consola 101, com `retroachievements_url` já
  correcto — por isso a secção Events não precisou de API nova.
- **Ícone da taskbar (item 5)** — o utilizador reportou como regressão, mas
  **não foi encontrada nenhuma**: `main.py` estava intocado face ao commit,
  `icon.png` carrega (889×889, `QIcon.isNull()` False), `AppUserModelID`
  definido. Foi acrescentado um ícone multi-resolução como melhoria
  plausível, **mas o problema nunca foi reproduzido** e pode não estar
  resolvido. Próximo passo, se persistir: limpar a cache de ícones do Windows
  (fora do código).
- **Continue Playing vs Library** — decidido que coexistem: Continue Playing
  é o atalho rápido na Home (cards pequenos, por recência); a lista "Library"
  (Bloco 13) é a vista completa em frames grandes.

---

## 5. Blocos que faltam

### Bloco 11 — ROM Location — ✅ CONCLUÍDO (2026-08-06)

A página "Library" passou a **"ROM Location"** e deixou de organizar
ficheiros: só aponta para pastas que o utilizador já organizou e deteta o
que lá está.

**Renomeado:** `library_page.py` → `rom_location_page.py`, `LibraryPage` →
`RomLocationPage`, chave `"library"` → `"rom_location"` em
`main_window.py::_menu_pages` e em `home_page.py::USER_MENU_DESTINATIONS`
(o `USER_MENU_DESTINATIONS` está em `home_page.py`, não em `main_window.py`
como o plano dizia).

**Apagados:** `gui/dialogs/watch_folder_scan_dialog.py`,
`library/organizer.py`, `models/rom_destination.py`,
`database/repositories/rom_destination_repository.py`,
`library/quick_link_suggestions.py`, `models/quick_link.py`,
`database/repositories/quick_link_repository.py`,
`tests/library/test_organizer.py`.

> **Desvio deliberado ao plano:** o `tests/library/test_zip_extraction.py`
> **não** foi apagado. O plano mandava apagá-lo, mas o `zip_extraction`
> continua a ser usado — `find_single_rom_member` pelo `console_detection` e
> `extract_member` pelo `_hash_in_place` novo. Apagar o teste tirava
> cobertura a código vivo.

**Limpo:** `library_service.py` perdeu `preview_watch_folder_scan`,
`apply_watch_folder_scan`, `ALREADY_EXTRACTED_DIRNAME`,
`RomDestinationNotConfiguredError` e as 7 funções de destinations/quick
links (o `RomFolderNotFoundError` **ficou** — a varredura nova usa-o).
`models/library.py` perdeu os 3 dataclasses `WatchFolder*`.
`settings_page.py` perdeu as secções "ROM Destinations" e "Quick Links".

**Novo:** `library_service.scan_rom_folder(rom_folder_id, progress_callback)`
+ `RomFolderScanResult` em `models/library.py`. Percorre com `rglob`, salta o
já registado, deteta consola, faz hash e regista **sem mover, renomear ou
apagar nada**. Só regista deteções confiantes; ambíguos e não reconhecidos
voltam no resultado para a página os mostrar, em vez de serem adivinhados.

- **Zips:** `_hash_in_place` extrai o membro único para uma pasta temporária,
  faz o hash **desse** membro (é o que a RA faz) e deita fora a cópia. O
  `file_path` registado continua a ser o zip, que é o que está em disco e o
  que o emulador recebe.
- **Sem diálogo de revisão:** o antigo existia porque o passo seguinte movia
  ficheiros e precisava de aprovação. Já não move nada, logo não há nada a
  aprovar — a varredura corre directa.

**Não mexido:** as tabelas `rom_destinations` e `console_quick_links`
continuam em `schema.py`. Ficam órfãs mas inertes; apagá-las exigia uma
migração destrutiva que o bloco não pedia.

**Verificado** com BD temporária e ficheiros reais (nunca contra
`database/retrocheevos.db`): 3 ROMs registadas de 5 ficheiros, `.iso`
ambíguo e `.txt` reportados sem serem adivinhados, subpastas percorridas,
hash do zip igual ao do membro interno e diferente do zip, **os 5 ficheiros
intactos no disco**, e a segunda passagem a registar 0 e a saltar 3. Os 24
testes existentes passam (`PYTHONPATH=src python -m unittest discover -s
tests -t .` — sem isso falham por não encontrarem o pacote).

### Blocos 12 + 13 — Listas — ✅ CONCLUÍDOS (2026-08-06)

Feitos juntos, a pedido do utilizador, antes de testar o Bloco 11 a fundo.

**Migração v15** (`CREATE_TABLES_V15`): tabela `user_list_definitions
(id, account_id, name, slug, is_predefined, created_at)` com índice único
`(account_id, name)`, coluna `user_lists.list_id`, e conversão dos dados
existentes — cada `list_type` que já tinha linhas vira uma definição e as
linhas são apontadas para ela. **Nada se perde.** O índice único v2
`(account_id, game_id, list_type)` foi deixado em paz; o novo é parcial,
`... (account_id, game_id, list_id) WHERE list_id IS NOT NULL`.

> ⚠️ **Índice parcial ⇒ `ON CONFLICT` tem de repetir o predicado.** Este foi
> apanhado ao correr o teste, não à vista: `ON CONFLICT(account_id, game_id,
> list_id) DO NOTHING` rebenta com *"ON CONFLICT clause does not match any
> PRIMARY KEY or UNIQUE constraint"*. Tem de ser
> `ON CONFLICT(...) WHERE list_id IS NOT NULL DO NOTHING`.

**`slug` é o que separa os dois tipos de lista.** As predefinidas levam um
valor de `ListType` porque há código que raciocina sobre elas (Explorer
esconde as bloqueadas, Library resolve-se a partir das ROMs). As que o
utilizador cria têm `slug = NULL` e nenhum código ramifica nelas. O
`ListType` ganhou `LIBRARY`.

**A armadilha do handoff antigo está resolvida:** o
`get_list_types_for_game` fazia `ListType(row["list_type"])` e rebentava com
qualquer nome fora do enum — ou seja, assim que o utilizador criasse uma
lista. Foi substituído por `get_list_ids_for_game`. O `_row_to_definition`
também é tolerante a slugs desconhecidos em vez de levantar.

**Library** (Bloco 13) é **calculada**, não guardada: o conteúdo é o que tem
ROM local *neste momento*. Guardar linhas obrigaria cada varredura a
adicioná-las e removê-las para se manter verdadeira. `add_to_list` recusa-a
com um `ValueError` explicativo. Widget novo `widgets/installed_game_frame.py`
— capa grande, **imagem inteira clicável** a lançar (`mousePressEvent`),
sem botão por baixo; o botão direito fica livre para um menu futuro.

**Blocked** é uma lista como as outras, com botão "−" nos cards
(`GameCard(show_remove=True)`). **Saiu das Settings** — geri-la em dois
sítios seria duas implementações da mesma coisa. O "Block" do Explorer
resolve-se **por slug**, num sinal `block_requested` próprio, para continuar
a funcionar se o utilizador renomear a lista Blocked.

**Sobreposição confirmada e evitada:** o "path por consola" pedido para a
Library **já existia** — `rom_folders` tem coluna `console_id` desde sempre
(schema.py), só a UI não a expunha. A secção sob a grelha da Library escreve
nessa tabela, não numa nova; uma pasta lá adicionada fica logo varrível pelo
ROM Location. As `rom_destinations` do Bloco 11 **não** foram ressuscitadas.

**Os 4 mapas `LIST_ACTION_LABELS` duplicados** reduziram-se: `game_card.py` e
`explorer_delegates.py` recebem agora as opções de fora
(`list_options` / `set_list_options`), e o do `lists_page.py` desapareceu. Só
resta o do `explorer_filter_bar.py`, que filtra por slug e é outra coisa.

**Erros de validação são levantados fora do `get_connection`** — lá dentro,
o `except` registava cada recusa normal ("já tens uma lista com esse nome")
como *"Database operation failed, rolled back"* com traceback, o que é falso
e enterraria falhas a sério nos `logs/`.

**Verificado** com BD temporária construída em v14 com dados legados e depois
migrada: 0 linhas sem `list_id`, jogo bloqueado escondido das outras listas e
de volta ao ser desbloqueado, Library a passar de vazia a `['Delta']` ao
inserir uma ROM, adição manual à Library recusada, nomes duplicados
(insensível a maiúsculas) e vazios recusados, apagar predefinida recusada, e
uma lista chamada "blocked list" a **não** se fundir com a Blocked real. Os
24 testes existentes passam.

#### Ronda de ajustes de UI (2026-08-06, depois de Library e Blocked a funcionar)

1. **Grelha da Library a 8 colunas** (era 3). O `InstalledGameFrame.COVER_SIZE`
   desceu de 180 para 104 em conjunto — os dois números estão acoplados, se
   mexeres num mexe no outro ou a página passa a fazer scroll horizontal.
2. **Só Library e Blocked são especiais no topo.** Rename desativado nessas
   duas; Delete só para listas do utilizador. Botão ativo que dá sempre erro
   é pior do que botão desativado — o serviço já recusava, agora a UI não
   convida.
3. **Blocked e listas custom usam `widgets/list_entry_row.py`** (novo): capa,
   título, consola e "−". Sem Play e sem "...". As predefinidas restantes
   (Want to Play, Playing, Completed, Abandoned) continuam com `GameCard`.
4. **Settings perdeu ROM Folders.** Agora são por consola e vivem sob a
   Library, ao lado da grelha que enchem.
5. **A página ROM Location foi apagada** e a entrada saiu do menu. As duas
   metades dela estão na Library: a vista do que está instalado é a grelha,
   e a gestão de pastas + varredura + "Match to Game" é a secção por baixo.

> ⚠️ **O "Match to Game" e os ROMs não emparelhados tiveram de vir juntos.**
> Apagar a página sem os trazer teria deixado uma ROM cujo hash não bateu
> **invisível em todo o lado** — não aparece na grelha (que só lista jogos
> com match), logo não haveria forma de dizer à app o que ela é. A lista
> "Unmatched ROMs" sob a Library existe por isso.

6. **A lista de navegação primária foi removida.** Tinha só "Home" desde que
   Explorer/Profile/Leaderboards foram absorvidos, ou seja era uma coluna de
   160px que só navegava para a página já no ecrã. O layout passou de
   horizontal a vertical (barra de histórico em cima, páginas por baixo)
   para a largura libertada ir para o conteúdo. Isto também **retira** o
   perigo documentado do `currentRowChanged`/`itemClicked` que causou o
   crash de arranque por destruir um `QThread` vivo — sem lista, sem sinal.

**Verificado headless** (`QT_QPA_PLATFORM=offscreen`), com os 7 modos do
selector:

```
Blocked      widgets={ListEntryRow}       rename=False delete=False
Library      widgets={InstalledGameFrame} rename=False delete=False folders_shown=True
Playing      widgets={GameCard}           rename=True  delete=False
My Backlog   widgets={ListEntryRow}       rename=True  delete=True
user menu: [('lists', 'Lists'), ('settings', 'Settings')]
```

> **Lição de método, registada porque custou um crash ao utilizador:**
> `import` de um módulo **não** corre o `__init__` de um widget. Foi assim
> que um `ImageLoader(self)` — construtor que não aceita parent — chegou ao
> utilizador com a app a não abrir de todo. A verificação mínima para
> alterações de GUI é construir `MainWindow` e cada página offscreen e
> chamar-lhes `refresh()`. O script está em
> `scratchpad/verify_ui.py` do histórico desta sessão; vale a pena recriá-lo.
> (Nota: exige teardown explícito dos widgets antes do fim do processo,
> senão o Qt aborta no shutdown e mascara o resultado com um exit code
> enganador.)

### Overhaul visual — tema da RetroAchievements (2026-08-07)

**De onde vieram as cores.** O site tem Cloudflare à frente e devolve **HTTP
403** a qualquer pedido que não seja um browser — tanto `requests` como o
WebFetch. E as ferramentas de browser rebentam a app do Claude nesta máquina
(ver §4). A saída foi melhor do que raspar páginas: **o site é open source**
(`RetroAchievements/RAWeb`) e `resources/css/theme.css` define o esquema todo
em CSS custom properties. Nenhuma cor foi inferida de um screenshot.

Ficheiros úteis do repo, via `raw.githubusercontent.com` (não tem Cloudflare):
`resources/css/theme.css`, `typography.css`, `button.css`, `table.css`,
`progress.css`.

**`gui/styles.py`** passou de "folha de scrollbars" a módulo de tema: as
constantes têm o nome da variável CSS equivalente, para a correspondência
continuar verificável. Esquema **dark + acento gold**, que é o que uma conta
por configurar vê.

```
--bg-color              #1a1a1a      --link-color (gold)   #cc9900
--box-bg-color          #232323      --link-hover-color    #eeeeee
--embed-color           #161616      --text-color          #c8c8c8
--embed-highlight-color #2a2a2a      --heading-color       #d2d2d2
--divider-color         #5a5a5a      --text-color-muted    #4b4b4b
```
Tipografia: Verdana/Arial, CSS `small`. Botões: raio 4px, fundo *embed*, texto
no acento, borda *embed-highlight*; hover troca para *embed-highlight* +
`link-hover`. Tabelas: linhas ímpares `rgba(50,50,50,.3)`, hover
`rgba(128,128,128,.2)`, células 4/8px. Progresso: 6px, hardcore gold
`#cc9900`, softcore azul `#0b71c1`.

**Duas divergências deliberadas**, porque o Qt não é um browser:
`--text-color-muted` (#4b4b4b) é quase invisível em painéis planos do Qt, por
isso existe um `TEXT_DIM` para texto secundário e o *muted* fica só para
desativado; e `FONT_SIZE_PT` substitui o `small` do CSS, que é relativo à
raiz do browser.

**Todas as cores inventadas desapareceram** dos widgets — o roxo `#8a63d2`
do Recent Activity, os azuis `#4a90e2` da Home e dos eventos, os cinzentos
`#b0b0b0`. Um `grep` por hex literais fora do `styles.py` não devolve nada.

> ⚠️ **Em Qt, `QLabel` herda de `QFrame`.** A regra de painel
> (`QFrame { border: ... }`) aplicava-se a *todas* as etiquetas e a UI
> renderizava como uma grelha de rectângulos vazios à volta do texto. Não
> basta escrever a regra `QLabel { border: none }`: com igual especificidade
> o **QSS resolve por ordem no ficheiro, ganha a última**, por isso ela tem
> de vir *depois* do bloco `QFrame` ou é ignorada em silêncio. Ambos os
> erros foram cometidos e ambos só se viram na imagem. O mesmo vale para
> `QLineEdit`/`QListWidget`/`QScrollArea`, todos subclasses de `QFrame`.

> **Verificação de trabalho visual: renderizar e olhar.** "Compila" e
> "constrói headless" não dizem nada sobre uma folha de estilos — o QSS falha
> em silêncio. O método que funcionou: `page.grab().save(...)` e ler o PNG.
> **Não usar o plugin `offscreen` para isto** — não desenha glifos nenhuns e
> todas as imagens saem cheias de quadrados (*tofu*), o que parece um
> problema de fontes e não é. O plugin normal do Windows consegue `grab()` de
> um widget que nunca foi mostrado.

Também corrigido pela imagem: a grelha de capas estava espremida a uma fila
e meia porque as duas `QListWidget` da secção de pastas reclamavam o seu
`sizeHint` inteiro — agora têm `setMaximumHeight`.

#### Setas de navegação removidas (2026-08-07, décima segunda)

Saíram os botões `‹ ›` **e todo o código que os servia**: `_history`,
`_history_index`, `_on_back`, `_on_forward`, `_update_history_buttons`, o
parâmetro `record_history` do `_show_page` e as constantes
`HISTORY_BUTTON_*`. Com quatro destinos, todos a um hover no menu da foto
(que agora inclui Home), um histórico de browser era mais cromo do que a
navegação que descrevia. O `_show_page` voltou a ser uma troca de página.

O topo encolheu junto: `WINDOW_MARGIN = 0` e `setSpacing(0)` no layout
central, com um `HEADER_GAP` de 4px antes da página. O cabeçalho já traz as
suas margens laterais e a página as dela, portanto o resto era espaço morto.

Medido: 0 botões de seta, cabeçalho em `y=0` com 99px, página a começar em
`y=103`.

#### ⚠️ O QSS global anulava todos os `setFont()` (2026-08-07, décima primeira)

Encontrado ao medir por que razão o "Retrocheevos" não crescia: **em Qt uma
declaração `font-size` num stylesheet sobrepõe-se a `setFont()`**. Como
`gui/styles.py` põe `font-size` em `QWidget`, *todo* o dimensionamento de
fonte feito por código nesta app estava a ser descartado em silêncio —
`APP_NAME_FONT_DELTA`, `POINTS_FONT_SIZE`, `TRUE_POINTS_FONT_SIZE`. Medido:
o nome da app renderizava a 15px quando a fonte pedia ~33px, e os pontos
estavam no tamanho do texto corrido apesar de `POINTS_FONT_SIZE = 32`.

Corrigido pondo o tamanho no `setStyleSheet` dessas etiquetas. **Cuidado ao
medir depois:** o `setFixedHeight(metrics.ascent())` dos pontos passou a
precisar de `ensurePolished()` antes do `QFontMetrics`, senão media a fonte
antiga e cortava o topo dos dígitos — a mesma armadilha das legendas dos
cartões.

Estado medido (janela 1200px, conta com stats):
```
logo(RC)      101x64  x=11   bottom=71
Retrocheevos  267x42  x=112  bottom=71   <- mesma linha de base do logo
12,132        169x43  x=930
24,325         82x24  x=1017 bottom=71
header height = 87px (inalterada)
```

#### Cartões todos do mesmo tamanho (2026-08-07, décima)

A caixa da legenda era dimensionada com `lineSpacing() * len(lines)` — ou
seja, pelas linhas que **aquele** título produziu. Um título de uma linha
dava um cartão mais baixo que um de duas, e a grelha saía irregular. Passou
a reservar sempre o pior caso (`CAPTION_LINES = MAX_TITLE_LINES + 1`), igual
para todos: um título curto deixa a última linha em branco, e como o texto
é alinhado ao topo, ele fica no sítio e é a linha da consola que desce nos
cartões que precisam de duas.

> **O teste ganhou a verificação que lhe faltava.** Só media cortes, que era
> por isso que a irregularidade lhe passou ao lado. Agora também compara o
> `sizeHint()` de vários títulos com o mesmo tamanho de capa e falha se não
> forem todos iguais — 3 tamanhos na Library, 3 no Continue Playing.

#### Quebra de linha antes de elidir (2026-08-07, nona)

`widgets/text_layout.py::wrap_lines` — quebra o título por palavras até um
máximo de linhas e **só elide se ainda assim não couber**. Elidir à primeira
deitava fora palavras que cabiam perfeitamente numa segunda linha.

A caixa é dimensionada a partir das linhas **efectivamente produzidas**
(`lineSpacing() * len(lines)`), não de um número decidido à partida — é isso
que torna o corte impossível por construção, em vez de improvável.

```
 94px  Shadow of the Colossus  -> ['Shadow of the', 'Colossus']
154px  Castlevania: Symphony…  -> ['Castlevania: Symphony', 'of the Night']
 94px  Supercalifragilistic…   -> ['Supercalifrag…']   (uma palavra só: elide)
```

Título até 2 linhas, consola sempre na sua. Varrimento dos 24 tamanhos:
zero cortes.

#### O corte de texto, a sério desta vez (2026-08-07, oitava)

> ⚠️ **O teste que "provava" que não havia cortes não verificava nada.**
> `scratchpad/verify_noclip.py` saltava etiquetas com
> `if label.pixmap() is not None` — no PySide6 `.pixmap()` devolve um
> `QPixmap` **vazio**, nunca `None`, portanto a condição era sempre
> verdadeira e o varrimento inteiro passava sem medir uma única etiqueta.
> Reportou "zero cortes" com 31 cortes reais lá dentro. A verificação certa
> é `not label.pixmap().isNull()`.
>
> **A causa real do corte:** a elisão era calculada com
> `QFontMetrics(label.font())` **antes de o widget ser polido**. Até
> `ensurePolished()`, `font()` devolve a fonte *por omissão*, não a que o
> stylesheet impõe — media-se contra uma fonte pequena e desenhava-se com
> uma maior, por isso o texto transbordava mesmo estando "elidido". A ordem
> correcta é `ensurePolished()` → medir → elidir → dimensionar. Também se
> passou a usar `lineSpacing()` em vez de `height()` para a altura, e a
> elidir contra `edge - 6px`, porque o layout do QLabel arredonda.
>
> Confirmado no varrimento real: 13 tamanhos na Library, 11 no Continue
> Playing, com um título longo — **zero**.

**Consolas abreviadas** — `library/console_names.py`: "PlayStation Portable"
→ PSP, "Game Boy Advance" → GBA, "SNES/Super Famicom" → SNES. Só na legenda
dos cartões; o tooltip mantém o nome completo. Um nome desconhecido passa
inalterado, portanto uma consola nova custa apenas uma legenda mais longa.

**Cabeçalho** — avatar 54→64 e margens laterais de 11px no
`header_widget`, para o logo arrancar na mesma linha vertical que a barra de
pesquisa e a foto não ficar colada à borda da janela. O cabeçalho vive na
`MainWindow`, fora do layout da página, por isso não herdava essas margens.

#### Legendas elididas e cabeçalho compacto (2026-08-07, sétima)

> ⚠️ **Texto cortado nos cartões: parem de ajustar a altura, mudem a
> estratégia.** A legenda foi por três iterações — rácio da capa (0,36),
> depois três linhas derivadas da fonte — e **cortava sempre nalgum
> tamanho**. Tinha de cortar: quantas linhas um título precisa depende do
> título *e* da largura, portanto qualquer altura escolhida à partida está
> errada para alguma combinação. A correcção não é outro número, é deixar de
> **quebrar** linhas e passar a **elidir**: `QFontMetrics.elidedText`
> garante que uma linha cabe na largura, logo duas linhas cabem sempre em
> duas alturas de linha, em todos os tamanhos e para todos os títulos.
>
> Verificado por varrimento de toda a gama dos dois sliders com um título
> propositadamente longo (`scratchpad/verify_noclip.py`): 13 tamanhos na
> Library, 11 no Continue Playing, **zero cortes**.

**Mínimos dos sliders** — Continue Playing **75px**, Library **100px**. O
mínimo era uma constante do módulo; passou a parâmetro por instância.

**Cabeçalho** — pontos 26→32, true points 17→18, e a banda ficou **mais
baixa**: a altura era ditada pelo botão do avatar (72→54, com moldura de
12→8) e o logo baixou de 52 para 42. O `header_layout` passou a
`setSpacing(0)`, que era onde estava a maior parte da folga. Tudo
`AlignBottom`, portanto logo, nome, pontos e foto assentam na mesma linha —
e como o cabeçalho vive na `MainWindow`, isso aplica-se a todas as secções.

#### Cartões proporcionais ao slider e cabeçalho maior (2026-08-07, sexta)

> ⚠️ **O cartão tem de encolher, não só a imagem.** Depois de as colunas
> passarem a sair da largura, o slider ainda parecia não funcionar: a caixa
> da legenda tinha **altura fixa** (54px na Library, 42px no Continue
> Playing) e as margens eram constantes, portanto uma capa de 40px continuava
> num cartão dimensionado para uma de 150px — texto cortado pela sua própria
> caixa e um chão que o cartão nunca conseguia furar. Agora legenda, margens
> e espaçamento saem todos de rácios sobre a capa, e **abaixo de 90px a
> legenda cai** (o tooltip diz o nome): duas linhas legíveis não cabem na
> largura de uma miniatura.
>
> Medido — um cartão que escala mantém o rácio aproximadamente constante;
> com caixa fixa ele disparava à medida que a capa encolhia:
>
> ```
> capa    Library        Continue Playing
>   40    46x46  1.15x     46x62  1.55x
>  160   174x238 1.49x    174x258 1.61x
> ```
>
> **Segundo detalhe, do mesmo sintoma:** o `ContinuePlayingGameRow` tinha
> política horizontal `Preferred`, por isso um cartão sozinho absorvia a
> coluna inteira do grid — uma imagem minúscula numa caixa larguíssima, que
> se lê exactamente como "o slider não faz nada". Passou a `Fixed` nos dois
> eixos, como o `InstalledGameFrame` já era.

**Cabeçalho maior** — logo 32→52, avatar 48→72, pontos 13→20, true points
11→14, nome da app +8, stats +2. Só o cabeçalho: a altura da banda já era
ditada pelo botão do avatar, portanto crescer o resto não empurra nada.

#### Correcções do slider e do Recent Activity (2026-08-07, quinta)

> ⚠️ **O slider "não redimensionava" porque as colunas não vinham da
> largura.** No Continue Playing a contagem era
> `6 * COVER_SIZE_BASELINE // cover_size` — uma proporção contra um baseline
> fixo, que a 40px devolve sempre **exactamente 6**. As colunas do
> `QGridLayout` esticam então para encher a linha, e o resultado eram seis
> caixas quase vazias em vez das muitas pequenas que o slider pedia.
> Substituído por `_continue_playing_columns()`, que mede o viewport. Medido:
>
> ```
> Continue Playing (viewport 920)     Library (viewport 1360)
>   40px -> 13 colunas                  40px -> 20 colunas
>  125px ->  5                         160px ->  7
> ```

**Library a meia largura** — o `_grid_columns` já media o viewport, mas o
`refresh()` corre a partir de `MainWindow._show_page` **antes de a página
estar disposta**, quando o viewport ainda reporta um tamanho de
substituição. A contagem estreita ficava se nenhum resize acontecesse a
seguir. Resolvido com `showEvent`, que reavalia quando a página aparece de
facto, e com o `refresh()` a actualizar `_last_grid_columns`.

> ⚠️ **Recent Activity lento a voltar à Home: mesmo caminho do glitch
> anterior.** O `refresh()` limpava a secção e forçava `show_loading=True`,
> ou seja deitava fora entradas correctas para esperar ~6 s por outras
> iguais, em **cada** navegação de volta. Agora há um `_activity_cache` com
> o último feed completo: ao voltar, ele é pintado de imediato e o refresh
> corre por trás em silêncio. O "Loading…" só aparece num arranque frio. O
> cache é limpo quando não há conta activa, senão a conta seguinte via
> brevemente o feed da anterior.

#### Ronda de ajustes visuais (2026-08-07, quarta)

> ⚠️ **Bug real no Recent Activity: o "piscar" era o refresh silencioso.**
> `_refresh_activity_feed(show_loading=False)` deixava a lista antiga no ecrã
> de propósito — mas a **primeira** entrada nova a chegar disparava um
> re-render que limpava a secção e deixava **um** cartão, que depois crescia
> um a um. De 30 em 30 segundos, isso lê-se como o conteúdo a desaparecer e
> a voltar. O streaming passou a acontecer só na carga inicial
> (`_stream_activity_entries`); um refresh de fundo renderiza uma vez, com a
> lista completa. O `_render_activity_entries` também suprime repaints
> durante o teardown/rebuild, que valia um flash de um frame.

- **Slider** agora em `valueChanged` (tempo real). O `STEP = 10` é o que
  torna isso viável: o valor só assenta em múltiplos de 10, logo um arrasto
  completo reconstrói a grelha uma dúzia de vezes e não centenas. Largura
  fixa (160px) com `addStretch` a seguir — esticado ao ecrã lia-se como o
  controlo principal da secção. Máximos: **125px** na Home, **160px** na
  Library.
- **Continue Playing na vertical** — capa em cima, título por baixo, barra de
  progresso por baixo dessa, como a Library. Era uma faixa horizontal, que
  deixou de fazer sentido quando a capa passou a ser o botão e ficou
  redimensionável.
- **Grelha da Library sem tecto fixo** — as colunas saem da largura real do
  viewport, não de `GRID_TARGET_WIDTH = 980`, que limitava a fila a 4 capas
  e deixava o lado direito vazio num ecrã largo. `resizeEvent` refaz a
  grelha **só quando a contagem de colunas muda** — um resize dispara
  continuamente e o rebuild é caro demais para correr a essa cadência.
- **Setas de navegação acima do logo**, com espaçamento (`HISTORY_BAR_GAP`,
  `HEADER_GAP`). Por baixo do cabeçalho liam-se como parte da página aberta.
- **"Home" no menu da foto**, em primeiro. Não está em `_menu_pages` — é a
  página raiz, tratada como caso especial em `_on_menu_navigate`; duplicá-la
  ali daria duas instâncias de `HomePage` e dois timers de Recent Activity.
  **Clique na foto vai directo à Home**; o menu abre-se no *hover*. Antes os
  dois gestos faziam o mesmo, o que desperdiçava o mais deliberado deles.

#### Cabeçalho partilhado, slider de capas e afins (2026-08-07)

**Cabeçalho em todas as páginas** — o header (logo, nome, pontos, stats,
avatar) foi empacotado como `HomePage.header_widget` e é montado pela
`MainWindow` **acima do `QStackedWidget`**, não copiado para cada página.
Uma instância em vez de quatro, cada uma com o seu fetch de perfil e a sua
ligação de sinais. `refresh_header()` é separado do `refresh()` de propósito:
este último arranca a busca do Recent Activity, vários segundos de chamadas
à API, que não tem nada que correr por se abrir as Settings.

**Slider de tamanho de capas** (`widgets/cover_size_slider.py`) na Library e
no Continue Playing. Liga em `sliderReleased`, não em `valueChanged` — a
grelha é reconstruída de raiz a cada mudança, e fazê-lo por cada pixel de um
arrasto engasga a janela numa biblioteca grande; o número ao lado acompanha
o arrasto na mesma. **Não é persistido**: não há tabela de preferências de
vista, e inventar uma (com migração) para um slider que se reajusta com um
arrasto não se justifica — se aparecerem mais preferências, é aí que se cria
armazenamento para todas de uma vez.

Na Library o número de colunas passou a **derivar** do tamanho da capa em vez
de ser uma constante que tinha de ser mantida em sincronia à mão — foi
precisamente esse par dessincronizado que fez a página deslizar na
horizontal antes.

**Cabeçalho "Events"** — QLabel com `styles.SECTION_HEADER_STYLESHEET`
(mesma caixa/dourado do botão acima), centrado. Não é um `QPushButton`
desativado de propósito: esse ficaria cinzento e leria como "ainda não podes
fazer isto" em vez de "isto é um título".

**Ícone da barra de tarefas** — a `MainWindow` definia um `QIcon` de tamanho
único que o `main.py` depois substituía pelo multi-resolução. Dois ícones a
competir pela mesma janela é exactamente a forma de um bug "às vezes
aparece"; ficou só um. O `_build_app_icon` passou a registar em `logs/` o
ficheiro, as dimensões e o AUMID — os dois relatos anteriores não foram
reproduzíveis e sem esse rasto o próximo também não seria. **Nota:** o
Windows guarda o ícone da barra de tarefas por AUMID, e o AUMID mudou nesta
sessão (`RetroCheevos.App` → `Retrocheevos.App`), o que por si só faz o
Windows tratar a app como nova até a cache actualizar.

> ⚠️ **Espaçamento no Explorer: aumentar a constante não resolvia.** Os
> botões eram dispostos da esquerda para a direita a partir da margem, por
> isso sempre que a coluna Actions era mais larga que o `sizeHint()` (quase
> sempre) a largura sobrante acumulava-se **à direita, sem uso**, e "Play" e
> "+" ficavam encostados um ao outro. `_button_rects` passou a **distribuir**
> os botões pela célula, com `_BUTTON_SPACING` a servir de mínimo. Dois
> ajustes da constante falharam antes disto.

#### Ajustes visuais pós-tema (2026-08-07)

1. **Events com mais espaço** — `SIDEBAR_MIN_WIDTH` 300 → 400, `MAX` 380 →
   480, `EVENTS_MIN_HEIGHT` 260 → 320. É o *mínimo* que faz efeito: a barra
   lateral está a `stretch=0`, logo nunca pede mais do que o conteúdo.
2. **Pontos a azul outra vez** — `styles.POINTS_BLUE` (#4a90e2). O dourado
   fica reservado ao que é clicável (botões, links); usá-lo num número só de
   leitura fazia o ecrã inteiro parecer coberto de controlos.
3. **App renomeada para "Retrocheevos"** — título da janela, cabeçalho,
   `APP_USER_MODEL_ID`, logs. ⚠️ Um *replace* global de `RetroCheevos` →
   `Retrocheevos` **parte todos os imports**, porque o pacote é
   `retrocheevos` em minúsculas: só as strings visíveis devem mudar.
4. **Continue Playing e Recent Activity esticam na vertical** — o
   `_center_column_filler` (widget vazio com `stretch=1`) era exactamente o
   espaço morto, e foi removido. Os dois grupos levam `stretch=1` cada. O
   explorer continua a funcionar sem ele: `_expand_explorer` esconde os dois
   grupos, e um widget escondido não contribui stretch nenhum.
5. **Continue Playing sem botão "Continue"** — a capa é o botão, como na
   Library (`mousePressEvent`). A barra de progresso mantém-se.
6. **Espaçamento no Explorer** — `_BUTTON_SPACING` 4 → 14, `_BUTTON_MARGIN`
   4 → 8, para "Play" e "+" deixarem de se ler como um só controlo.

> **Duas armadilhas de layout, ambas só visíveis na imagem.** Dar `stretch=1`
> a um grupo faz o *conteúdo* dele inchar também: um único cartão do Continue
> Playing passou a ocupar o painel inteiro à volta de uma capa de 40px.
> `setAlignment(AlignTop)` no layout **não chega** — o widget tem de recusar
> a altura extra, com `setSizePolicy(..., QSizePolicy.Policy.Fixed)` na
> vertical. Foram precisas as duas coisas.

### Reestruturação Library/Lists (2026-08-06, segunda ronda de ajustes)

**Library saiu das Lists e é uma página própria** —
`gui/pages/library_page.py`, no menu da foto: **Library, Lists, Settings**.
Nunca se comportou como lista: não guarda linhas, não aceita adições
manuais, e desenha uma grelha que mais nada usa. A `ListType.LIBRARY` deixou
de ser usada como lista; a regra "bloqueado não aparece" vive em
`core/lists.py::get_installed_games`, ao lado das regras das listas, para
não haver duas cópias dela.

**Só a Blocked é predefinida.** `PREDEFINED_LISTS` reduziu-se a uma entrada.
As quatro fixas (Want to Play, Playing, Completed, Abandoned) foram
**apagadas** — decisão do utilizador, confirmou que estavam vazias e preferiu
criar as suas de raiz.

**Migração v16** apaga essas definições e as linhas delas.
**Migração v17** larga o índice v2 `(account_id, game_id, list_type)`.

> ⚠️ **O índice v2 não era redundante — a v15 errou ao deixá-lo.** Todas as
> listas do utilizador escrevem o mesmo `CUSTOM_LIST_TYPE_MARKER` em
> `list_type`, por isso aquele índice significava na prática **"um jogo pode
> estar no máximo numa lista tua, para sempre"**. Pôr o mesmo jogo em duas
> listas próprias dava `UNIQUE constraint failed`. Foi o teste que o
> apanhou, não a leitura do código. Está numa versão própria (17) e não
> acrescentado à 16, porque uma BD que já tivesse corrido a 16 nunca mais o
> veria.

**Consequência no Explorer, tratada:** a pill "Lists" filtrava por Want to
Play/Playing e tinha toggles Completed/Abandoned. Com essas listas apagadas
ficaria inerte. Passou a construir-se das listas reais da conta
(`ExplorerFilterBar.set_list_options`), e `ExplorerFilters.list_types_any_of`
deu lugar a `list_ids_any_of`. Os toggles Completed/Abandoned foram
removidos — **nada se perde na pesquisa**, porque os jogos já terminados
continuam excluídos incondicionalmente a partir de `game_completion`, que é
o registo da própria RA e não uma lista mantida à mão. Isto elimina também
o último dos 4 mapas `LIST_ACTION_LABELS` duplicados.

**Ajustes visuais:**
- `InstalledGameFrame`: capa 104 → **150**, grelha 8 → **6 colunas** (os dois
  números andam sempre juntos). O texto sobrepunha a imagem porque a label
  crescia livremente; agora tem `setFixedSize` e alinhamento ao topo, numa
  caixa reservada por baixo da capa (`TEXT_HEIGHT`).
- `ListEntryRow`: passou por três iterações e a terceira é a boa. Empilhado
  em `QVBoxLayout` (painéis gigantes) → capa 32 px em faixa de 40 px
  (esticada e vazia) → **capa 64 px em faixa de 76 px**, que preenche a
  linha sem voltar a ser um card. A consola deixou de ser uma label própria
  alinhada à direita — está **entre parênteses a seguir ao título**, numa só
  label (`"Beta (Game Boy Advance)"`), porque a label separada deixava um
  vazio entre o nome e ela em todos os títulos curtos. O título leva todo o
  `stretch`, portanto o "−" fica encostado à direita e o espaço do meio
  pertence ao nome.

**Verificado headless:**
```
predefined lists shipped: ['Blocked']
user menu: [('library','Library'), ('lists','Lists'), ('settings','Settings')]
Lists dropdown: ['Blocked', 'My Backlog']        <- sem Library
Blocked      widgets={ListEntryRow}  rename=False delete=False
My Backlog   widgets={ListEntryRow}  rename=True  delete=True
LibraryPage grid: ['InstalledGameFrame']  cover=(150,150) frame=(164,222)
Explorer Lists pill: ['My Backlog']
```
Mais, na camada de dados: v14 → v17 numa BD com dados legados, só a Blocked
sobrevive com as suas linhas, jogo bloqueado escondido de uma lista do
utilizador e da grelha da Library, e **o mesmo jogo em duas listas próprias**.

### Bloco 12 (plano original, agora histórico) — Listas criadas pelo utilizador (risco alto)

- **Migração v15** (a v14 já foi usada): tabela
  `user_list_definitions(id, account_id, name, is_predefined, created_at)`
  com índice único `(account_id, name)`; coluna `list_id INTEGER` em
  `user_lists`; índice único novo `(account_id, game_id, list_id)`.
- **Porquê tabela nova:** guardar o nome em `list_type` faria uma lista
  chamada "blocked" fundir-se com a predefinida, e não haveria onde guardar
  metadados. O índice único v2 `(account_id, game_id, list_type)` já está
  entregue e não se mexe.
- **Migração de dados na mesma versão:** converter Want to Play / Playing /
  Completed / Abandoned / Blocked em definições e preencher `list_id`.
  Decidido com o utilizador: **nada se perde**.
- **Cuidado:** `ListRepository.get_list_types_for_game` faz
  `ListType(row["list_type"])` e rebenta com qualquer nome fora do enum.
- **`ListType` reduz-se** a marcador das predefinidas (`BLOCKED`, e `LIBRARY`
  no Bloco 13). Os filtros em `core/explorer.py` e `core/dashboard.py` passam
  a usar `list_id`.
- **UI:** `lists_page.py` ganha criar/renomear/apagar. O menu "+"
  (`explorer_delegates.py`) e o do `GameCard` passam a construir-se a partir
  das definições — hoje há **4 mapas `LIST_ACTION_LABELS` duplicados**
  (game_card, explorer_delegates, lists_page, explorer_filter_bar). O sinal
  `list_action_requested = Signal(int, object)` já passa o 2º argumento como
  `object`, logo aceita um id sem mudar assinatura.
- **Blocked sai das Settings** (3 blocos de widgets + 2 métodos, isolados).

### Bloco 13 — Playlist "Library" (risco baixo, depende do 12)

Segunda lista predefinida, **automática**: não guarda linhas em `user_lists`,
é resolvida na hora a partir de `library_repository.get_installed_game_ids()`.

- **Novo** `widgets/installed_game_frame.py` — frame grande, capa a
  preencher, título por baixo, **imagem inteira clicável** a lançar o jogo
  (`mousePressEvent` → `play_requested`; nenhum widget actual faz isto, todos
  usam botão explícito). Reaproveita o `ImageLoader` com filtro por `game_id`,
  como o `ContinuePlayingGameRow`.
- `lists_page.py` ganha um `ImageLoader` próprio (hoje não tem) e um ramo no
  `refresh()` para a Library. `_clear_grid()` não muda, é agnóstico ao tipo.
- O nome "Library" só fica livre depois do Bloco 11 renomear a página.

---

## 5b. Verificação de atualizações (só aviso)

`version.py::APP_VERSION` é a **única** fonte de verdade da versão — nada mais
deve fixar um número. Ao arrancar, `services/update_service.py` consulta
`releases/latest` do GitHub numa `ServiceWorker` (nunca na thread da UI: uma
chamada de rede no arranque congelaria a janela no pior momento possível) e,
se houver versão mais recente, `widgets/update_banner.py` aparece por cima do
header.

Regras que não devem ser quebradas:

- **Nunca autenticar este pedido.** O endpoint é público e a chave que a app
  guarda é da RetroAchievements — não tem nada que fazer num pedido ao
  GitHub. Há um teste que falha se alguém acrescentar um header `Authorization`
  ou `params`.
- **Todo o tipo de "não" devolve `None`**, incluindo estar offline. Um aviso
  de erro no arranque porque o wifi está desligado é um bug. O motivo vai
  para o log.
- **Comparação numérica, nunca de strings.** `"1.10.0" < "1.9.0"` é verdade
  para strings — um compare lexical deixaria de reportar updates exactamente
  no décimo lançamento, sem sintoma nenhum. Coberto por teste.
- **Tag ilegível lê-se como "sem update"**, nunca ao contrário: um banner
  levantado por uma tag que ninguém consegue interpretar não desaparecia nem
  actualizando.
- **O "×" guarda a versão dispensada** em
  `preferences_service.KEY_DISMISSED_UPDATE_VERSION` — a *versão*, não um
  booleano, para que um release posterior volte a avisar sozinho em vez de
  depender de alguém se lembrar de limpar uma flag.
  `update_service.should_notify` tem o **viés oposto** ao de `is_newer`, de
  propósito: aqui "não consigo interpretar" significa **mostrar**, porque uma
  dispensa corrompida a silenciar todos os updates futuros teria como sintoma
  não acontecer nada — o tipo de falha que nunca se dá por ela.
- **Limitação conhecida:** `set_str` é no-op sem conta ativa, portanto uma
  dispensa feita antes de iniciar sessão vale só para essa sessão. Não foi
  contornado: as preferências são todas por conta, e inventar um segundo
  armazenamento sem conta só para este valor era uma mudança maior do que o
  incómodo justifica. Resolve-se sozinho assim que a pessoa entra.

Para lançar: subir `APP_VERSION`, criar a tag `v<APP_VERSION>` e **publicar um
release** contra ela. O check lê *releases*, não tags — uma tag sem release é
invisível de propósito, para a tag poder existir antes do build estar pronto.

## 5c. Ronda de segurança e limpeza final

**A chave da API ia parar ao log, em texto simples.** `client.py` fazia
`logger.exception` no `except requests.RequestException`, e a mensagem do
urllib3 dentro do traceback é `Max retries exceeded with url:
/API/X.php?z=user&y=<chave>`. Bastava estar offline, um DNS lento ou um
timeout. Ficava em `logs/retrocheevos.log` — precisamente o ficheiro que uma
pessoa envia a outra a pedir ajuda. O docstring da classe prometia
"Credentials are never logged"; era falso.

Duas vias, ambas fechadas:
1. A directa: `logger.warning` com `redact_credentials(str(error), key)`.
2. A indirecta: `raise ... from error` guardava o original em `__cause__`, e
   `main.py::_log_uncaught_exception` regista com `exc_info` — o que imprime
   também o traceback da causa, com o URL. Passou a `from None`, com o
   diagnóstico útil preservado (já redigido) na mensagem nova.

**Regra a manter:** nada derivado de um erro de request pode ser escrito sem
passar por `redact_credentials`. Coberto por `tests/api/`.

**Os quatro caches de imagens escreviam para dentro do bundle.**
`game_images`, `user_pics`, `local_covers` e `activity_icons` derivavam o
directório de `__file__`, sem tratar `sys.frozen` — ao contrário do
`connection.py`, que resolvia exactamente isto. Invisível a correr da fonte.
No .exe: escrita ao lado do executável (falha silenciosa em Program Files),
descartada a cada arranque num build one-file, e — o pior — **por instalação
em vez de por utilizador**, ou seja dois utilizadores do Windows a partilhar
fotos de perfil em cache. O `local_covers` era o mais grave por não ser
re-descarregável: são capas escolhidas à mão. Agora tudo passa por
`retrocheevos/paths.py`, que é o único sítio onde a decisão se toma.

**Órfãos removidos** (3 passagens até convergir — remover a primeira camada
expõe a seguinte): ficheiros `core/cache_policy.py`,
`database/repositories/leaderboard_repository.py`, `models/leaderboard.py`;
18 funções/classes; 8 imports. Restam só `rowCount`/`headerData`, que são
overrides do Qt chamados pela framework.

**Migração v22 — tabelas órfãs apagadas.** `notification_settings` e
`leaderboard_cache` (atenção ao nome: **não** é `leaderboards`, que não
existe — confirmar sempre o nome real no schema antes de escrever um DROP).
Ambas verificadas vazias nas duas bases de dados antes de apagar. A base
existente migrou de 21→22 sem perder nada: `notifications`, `accounts`,
`games` (12042) e `user_lists` com as contagens intactas, `integrity_check`
ok, `foreign_key_check` limpo.

Os `CREATE TABLE` históricos ficam de propósito, tal como no v20: uma base
nova cria-as e o v22 apaga-as logo a seguir. Editar uma migração antiga
dessincroniza todas as bases que já a aplicaram — o custo de as criar por um
instante é muito menor que esse risco.

**Fica por decidir (não mexido de propósito):**
- A chave da API está em texto simples no SQLite. É o normal em apps desktop
  sem integração com o cofre do SO, mas convém ser dito em vez de assumido.
- 14 ficheiros `.py` têm BOM UTF-8. O Python importa-os bem; ferramentas de
  análise não (partiu o scanner de código morto até usar `utf-8-sig`).

## 6. Verificação sugerida ao retomar

1. Abrir a app e confirmar que a Home mostra **98 / 56 / 56,75 %**. A revisão
   subiu para 2, portanto o primeiro arranque re-sincroniza sozinho — a linha
   em cache com a revisão 1 é invalidada independentemente da idade.
2. Recent Activity está encerrado (§2.2) — as horas aparecem em **UTC em
   bruto**, iguais às do site e uma hora atrás do relógio local. É
   intencional. Não abrir isto outra vez sem ler o §2.2 primeiro.
3. Confirmar as 6 colunas do Continue Playing e a barra lateral mais larga.
4. Abrir Lists → Library, adicionar uma pasta real por consola e correr
   "Scan Folder". Isto cobre de uma vez o que faltava do Bloco 11 (validado
   só com ficheiros sintéticos) e a secção de pastas nova.
5. Na mesma página: confirmar as 8 capas por fila, o clique na imagem a
   lançar, o "−" na Blocked e numa lista própria, e criar/renomear/apagar.
6. Decidir a alternativa do §2.3 (backfill só das consolas com ROMs).
7. Os blocos numerados acabaram aqui — o que vier a seguir é novo.
