# Fut Manager API

## Banco de dados

O projeto usa PostgreSQL e SQLAlchemy assíncrono. Para iniciar localmente:

```bash
docker compose up --build
```

O `lifespan` da API cria o esquema em um banco vazio. Isto facilita o início do
projeto; quando houver dados reais, a evolução do esquema deve passar a ser feita
por migrations versionadas, nunca por `create_all`.

As configurações são validadas por Pydantic ao iniciar. Copie `.env.example` para
`.env` em execução local e use as variáveis `FUT_MANAGER_*`; o Docker Compose já
fornece explicitamente todas as variáveis necessárias para comunicação entre os
containers. As configurações de banco são obrigatórias: uma variável ausente
impede a API de iniciar.

Para a conexão PostgreSQL, configure separadamente `FUT_MANAGER_DATABASE_HOST`,
`PORT`, `NAME`, `USER` e `PASSWORD`. A URL assíncrona é montada internamente pela
aplicação, sem precisar existir no arquivo de ambiente.

### Ciclo de vida do evento

Um evento aberto é identificado por `pelada_events.status = in_progress` e seu
início/fim é registrado em `started_at` e `finished_at`. A fila atual é mantida em
`event_team_queue_entries`; cada time do evento ocupa uma posição única. Uma
partida pertence ao evento e pode apontar para `previous_match_id`, formando a
cadeia de confrontos. Ao encerrá-la, `advancing_team_id` registra o time que segue
na fila, inclusive quando o avanço foi escolhido após empate.

Para bancos já criados antes dessa estrutura, aplique as migrations aditivas em
`src/databases/scripts/migrations/` na ordem numérica. Bancos novos recebem as
tabelas e colunas diretamente na inicialização da API.

### Confirmações e lista de espera

Cada evento tem `min_confirmed_players` e `max_confirmed_players`. A confirmação
é mantida em `event_presences`; ao atingir o máximo, novas confirmações passam
automaticamente a `waitlist`, com `waitlist_position`. Cancelar ou remover uma
presença promove a primeira pessoa da espera e renumera a fila. O banco impede que
um evento entre em andamento sem o mínimo de pessoas confirmadas.

### Credenciais de perfil

O app usa `POST /auth/login` com `{ "email": "...", "password": "..." }`.
A resposta contém `access_token` e `profile`. Envie `Authorization: Bearer <token>`
em `GET /auth/me/groups` para listar grupos criados pelo usuário ou com vínculo
ativo. O servidor obtém o usuário pela sessão, sem aceitar um ID de perfil do cliente.
`POST /auth/logout` revoga a sessão.

Nesta versão local, as sessões ficam em memória, expiram em oito horas e são
invalidadas quando a API reinicia. Execute com um único worker. Antes de usar
múltiplos workers/réplicas, substitua esse armazenamento por sessões compartilhadas.
Os endpoints CRUD existentes continuam com suas permissões anteriores; a proteção
adicionada aqui cobre os novos endpoints de conta, não todo o CRUD da aplicação.

O CORS permite o Expo Web em localhost. Para outros hosts, configure
`FUT_MANAGER_CORS_ORIGINS` como uma lista JSON de origens permitidas.
Os testes em `tests/test_auth.py` usam o PostgreSQL configurado e revertem todos
os registros criados em cada teste. Execute `python -m unittest discover -s tests -v`.

Perfis usam e-mail e senha; telefone não é armazenado. A API recebe `password`
somente na criação/alteração do perfil e persiste um hash `scrypt` com salt
aleatório em `password_hash`. Esse campo não é incluído nos schemas de resposta.
Perfis legados recebem o marcador `RESET_REQUIRED` na migration 003 e precisam
definir uma nova senha antes de poderem autenticar.

### Modelo do domínio

```text
Profile ──< GroupMember >── PeladaGroup ──< PeladaEvent
   │                                  │             │
   │                                  │             ├──< EventPresence
   │                                  │             ├──< EventTeam ──< EventTeamPlayer
   │                                  │             └──< Match ──< MatchTeam
   │                                  │                          ├──< MatchLineup
   └────────────────────────────────────────────────└──< GameAction
```

- `profiles`: a conta/jogador. Um perfil pode ser membro de vários grupos.
- `group_members`: vínculo entre perfil e pelada, com papel `owner`, `admin` ou
  `member`. É o limite de acesso e de separação dos dados de cada pelada.
- `pelada_events`: uma data de jogo de um grupo. Tem limite de jogadores, período
  de inscrições, duração prevista de partidas e ciclo de vida da sessão.
- `event_presences`: inscrição, confirmação, fila de espera, cancelamento ou falta
  de cada jogador em um evento.
- `event_teams` e `event_team_players`: o sorteio/manual dos times de um evento e
  a posição de jogador ou goleiro.
- `matches` e `match_teams`: cada confronto entre dois times e o placar/resultado
  de cada lado. Vitórias, derrotas e empates vêm daqui.
- `match_lineups`: quem de fato jogou cada confronto. É a fonte correta para dar
  vitória/derrota a jogadores e calcular gols sofridos por goleiro.
- `game_actions`: gols, gols contra, assistências e cartões de cada jogador.

### Área autenticada do grupo

As rotas `/my-groups/{group_id}` exigem a sessão Bearer do login e validam
que a conta é criadora do grupo ou membro ativo:

- `GET /my-groups/{group_id}`: dados do grupo e próximo evento futuro com
  inscrições abertas/encerradas, quantidade de confirmados e presença da conta.
- `POST /my-groups/{group_id}/events/{event_id}/confirm`: confirma o usuário da
  sessão. Exige vínculo ativo, prazo aberto e evento futuro; lotação esgotada
  gera espera. Repetir a chamada mantém a mesma presença. O evento é bloqueado
  durante a transação para serializar confirmações.
- `GET /my-groups/{group_id}/events/{event_id}/confirmed`: nomes confirmados,
  incluindo convidados, sem misturar a lista de espera.
- `GET /my-groups/{group_id}/history`: somente eventos finalizados/cancelados,
  em ordem decrescente de data. Eventos abertos com horário passado continuam
  na área do evento atual, e não no histórico.
- `GET /my-groups/{group_id}/members`: membros ativos e organizador, sem e-mails.
- `GET /my-groups/{group_id}/rankings`: estatísticas de partidas finalizadas do
  grupo, excluindo eventos cancelados e separando perfis de convidados.

As datas são enviadas com fuso e exibidas no horário local do aparelho.
Testes adicionais: `tests/test_groups.py`, com rollback dos dados de cada caso.

### Cálculo dos rankings

Os rankings não são armazenados como contadores em `profiles`: são agregados por
grupo a partir dos jogos finalizados, sem duplicar totais. Correções de lances
ficam disponíveis durante a partida. Após encerrar o evento, seus registros são
somente para consulta, inclusive pelas rotas CRUD genéricas.

| Ranking | Fonte |
| --- | --- |
| Artilharia | `game_actions` do tipo `goal` |
| Gols contra | `game_actions` do tipo `own_goal` |
| Assistências | `game_actions` do tipo `assist` |
| Cartões | `game_actions` dos tipos `yellow_card` e `red_card` |
| Vitórias/derrotas | `match_lineups` unido a `match_teams.result` |
| Gols sofridos | goleiros em `match_lineups` e gols do adversário em `match_teams.goals` |

As rotas/serviços deverão validar as regras que atravessam tabelas: somente membro
ativo do grupo pode se inscrever; só inscrito confirmado pode ser escalado; um
jogador não pode entrar em dois times no mesmo evento; e os dois times de uma
partida devem pertencer ao próprio evento.

## Convidados

`group_guests` permite que um membro ativo do grupo registre um convidado apenas
com nome. Para incluí-lo em um evento, crie uma `event_presence` com `guest_id`.
O banco ordena a espera com perfis antes de convidados: um convidado sempre fica
no fim, e uma nova confirmação de perfil passa à frente dele.

## Ciclo do evento

A área `/my-groups/{group_id}/events/{event_id}/lifecycle` retorna times, jogadores,
partida atual, fila e partidas finalizadas. Somente organizadores/administradores
podem executar as ações abaixo; membros ativos podem consultar.

- `POST /teams`: sorteio balanceado ou montagem manual de 3 ou 4 times, com todos
  os confirmados exatamente uma vez. Administradores e donos podem ajustar antes de iniciar o evento. O início exige a formação completa salva.
- `POST /start`: inicia com o mínimo configurado de confirmados e encerra inscrições.
- `POST /kickoff`: sorteia ou escolhe os dois times iniciais; os demais ficam na fila.
- `POST /matches/{match_id}/timer`: recebe `action: play` ou `action: pause`.
  O cronômetro persiste no banco, começa em zero e pausado em cada partida e
  preserva o tempo acumulado ao continuar. Finalizar a partida congela seu tempo.
  Em bancos existentes, aplique `src/databases/scripts/migrations/005_match_timer.sql`.
- `POST /matches/{match_id}/actions`: registra gol, assistência, cartões ou gol contra.
  Um UUID por lançamento evita duplicidade em repetição da mesma operação.
- `POST /matches/{match_id}/actions/{action_id}/remove`: corrige um lance e o placar
  enquanto a partida está em andamento.
- `POST /matches/{match_id}/finish`: valida o vencedor pelo placar; em empate,
  escolhe/sorteia quem avança, preservando o resultado de empate nos rankings.
  O vencedor permanece, o primeiro da fila entra e o perdedor vai para o fim.
  A próxima partida é criada na mesma transação. `continue_cycle=false` encerra
  o evento ao concluir a partida.
- `POST /finish`: encerra um evento iniciado que não tem partida em andamento.

Todas as mutações do ciclo bloqueiam a linha do evento durante a transação.
Eventos finalizados/cancelados recusam escritas com HTTP 409, inclusive inclusões
em lote, alterações e exclusões pelo CRUD dos eventos e registros relacionados.
As telas abertas pelo histórico são sempre de consulta.

## Modalidades e posições do perfil

`GET /auth/modalities` fornece o catálogo de Futebol de Campo, Futsal e Fut7.
`POST /auth/register` cria uma conta; o CRUD `/profiles` usa a mesma validação
do campo obrigatório `positions`, por exemplo:
`{"campo":["volante","meia"],"futsal":["fixo","pivo"]}`.
Cada modalidade informada exige uma ou mais posições válidas, sem repetição.
O PATCH permite omitir o campo, mas não apagá-lo com `null` ou `{}`.
O login devolve as posições cadastradas. Para bancos existentes, aplique a
migration `006_profile_positions.sql`; perfis antigos permanecem com `{}` até
informarem suas preferências, sem atribuição automática de posições.

Referências do catálogo (funções táticas, cujos nomes podem variar por equipe):
- Campo: https://www.santosfc.com.br/masculino/
- Futsal: https://cdn.conmebol.com/wp-content/uploads/2024/02/Manual-Futsal-Port-Web.pdf
- Fut7: https://www.cbf7.com.br/federacao/FUT7SE/equipes/bola-de-ouro-esporte-clube

## Organização da API

- `routers/`: caminhos, métodos HTTP, schemas de entrada/saída e injeção de
  dependências; encaminham as chamadas para controllers.
- `controllers/`: validações manuais, autorização, decisões de negócio,
  alterações nas entidades e coordenação das transações.
- `services/`: classes responsáveis exclusivamente pelas consultas e operações
  de persistência usando a sessão recebida. Não produzem respostas HTTP.
- `helpers/`: funções auxiliares sem consultas, como cálculo de tempo,
  verificação da janela de inscrição e leitura de identificadores.
- `schemas/`: arquivos por contexto (perfis, grupos, membros, convidados,
  eventos, presenças, times, filas, partidas, escalações, ações e autenticação).
  `crud.py` permanece apenas como fachada de imports para compatibilidade.

Os endpoints, os bloqueios transacionais e os contratos existentes foram
preservados; `code` foi acrescentado às respostas de grupos. O CRUD gerado pela
biblioteca continua usando seus controllers/services e os schemas do projeto.

## Código único dos grupos

A migration `007_group_alpha_numeric_code.sql` usa a tabela `pelada_groups` e
uma única coluna `code`. Nomes podem se repetir; códigos não.

O PostgreSQL gera seis caracteres `A-Z`/`0-9` por `DEFAULT generate_group_code()`.
Uma sequência sem ciclo, combinada com uma permutação em base 36, evita colisões
entre criações simultâneas. Há `NOT NULL`, `UNIQUE` e validação de formato.
Não é um sorteio aleatório: a sequência garante códigos distintos sem depender
de tentativas concorrentes. Os clientes não precisam enviar o campo.

A migration preenche códigos ausentes e pode ser reaplicada sem trocar códigos
existentes. A inicialização de bancos novos também instala essa geração após
`create_all`. Em bancos existentes, aplique em transação:

```powershell
Get-Content -Raw src/databases/scripts/migrations/007_group_alpha_numeric_code.sql | docker compose exec -T db psql -U fut_manager -d fut_manager -v ON_ERROR_STOP=1 --single-transaction
```

## Dados fictícios para teste

`scripts/seed_demo.py` popula um grupo existente de forma idempotente. A senha é
lida de `FUT_MANAGER_DEMO_PASSWORD`; não é necessário editar o script.
Use `--group-id UUID --saturday 2026-09-26 --start-now` para criar três eventos
históricos e um evento atual com seis confirmados. O script preserva registros
existentes e não reinicia um evento que o usuário já começou a testar.
