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
containers. Nenhuma configuração tem valor padrão: uma variável ausente impede a
API de iniciar.

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

### Rankings

Os rankings não são armazenados como contadores em `profiles`: são agregados por
grupo a partir dos jogos finalizados. Assim, uma correção em uma súmula sempre se
reflete no ranking, sem risco de totais duplicados.

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
