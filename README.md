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
