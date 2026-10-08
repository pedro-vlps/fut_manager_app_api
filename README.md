# Fut Manager API

## Campeonatos sazonais

Campeonatos são edições independentes dos grupos de pelada e das temporadas de
rankings. `POST /championships` recebe nome, temporada, descrição opcional,
`capacity` (4, 8 ou 16) e `format` (`groups_knockout`, `knockout` ou `cascade`).
Todas as rotas exigem login. `GET /championships` permite descobrir as edições;
`GET /championships/{id}` mostra inscritos, elencos, partidas e classificação.

O jogador cria um time permanente em `POST /clubs`. O criador convida contas
existentes por e-mail em `POST /clubs/{id}/invitations`; o destinatário consulta
`GET /club-invitations` e aceita/recusa com `POST /club-invitations/{id}` e
`{"accept": true/false}`. Os convites ficam no app, sem envio de e-mail.

Somente o criador do time pode inscrevê-lo em
`POST /championships/{id}/entries` (`club_id`). O elenco precisa ter pelo menos
dois jogadores ativos e confirmados, incluindo o criador. O elenco é congelado
na inscrição; um jogador não pode representar dois times na mesma edição.
Antes do início, `POST /championships/{id}/entries/{club_id}/withdraw` permite
retirar e reinscrever o time para atualizar seu elenco. Convites aceitos depois
da inscrição não alteram retroativamente o elenco inscrito.

Somente o organizador inicia (`POST /championships/{id}/start`) e registra
resultados (`POST /championships/{id}/matches/{match_id}/score`). É necessário
preencher todas as vagas. O chaveamento segue a ordem de inscrição. Grupos de
quatro jogam todos contra todos em turno único, classificando dois por grupo;
com quatro times, os dois primeiros disputam a final. A classificação usa
pontos (3/1/0), saldo, gols marcados e ordem de inscrição. Grupos adjacentes
cruzam primeiro contra segundo. Empates no mata-mata exigem `winner_id` junto
de `home_score` e `away_score`. Resultados confirmados são definitivos e geram
a rodada seguinte automaticamente; a final define o campeão e encerra a edição.

Cascata aceita somente **4 times**, com seeds 1 × 4 e 2 × 3. São seis partidas em ordem obrigatória: duas semifinais dos vencedores, final dos vencedores, semifinal dos perdedores, final dos perdedores e final geral única (sem reset). Quem perde a final dos vencedores entra diretamente na final dos perdedores, descansando durante a semifinal dessa chave. Quem perde na chave dos perdedores é eliminado.

A migration aditiva `017_championships.sql` cria as seis tabelas, sem modificar
os grupos existentes. Em bancos novos, elas são criadas pelo `create_schema`.
Os modelos não são expostos pelo CRUD genérico. Inscrições/início/resultados
usam lock da edição; convites e inscrição também usam lock do time.

O app usa `POST /my-groups` para criar grupos com o usuário autenticado como
organizador, sem aceitar um criador arbitrário no payload.

## Banco de dados

O projeto usa PostgreSQL e SQLAlchemy assíncrono. Para iniciar localmente:

```bash
docker volume create fut_manager_app_api_postgres_data
docker compose up --build
```

O comando `docker volume create` prepara o armazenamento na primeira execução;
se o volume já existe, ele é reutilizado sem apagar os dados. Nesta máquina, o
volume existente continua sendo usado, sem necessidade de migrar o banco.

O PostgreSQL usa o volume externo `fut_manager_app_api_postgres_data`, com nome
fixo e independente do nome da pasta/projeto Compose. Por ser externo, ele não é
removido por `docker compose down -v`. Para desligar e subir novamente mantendo
todos os registros do banco:

```bash
docker compose down -v
docker compose up --build
```

A remoção manual desse volume ou dos dados do Docker ainda apaga o banco; a
persistência não substitui um backup. As sessões de login da API ficam em memória
e exigem novo login após reiniciar, mas contas e demais registros permanecem.

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

Com a opção **Separar vagas de goleiros**, `min_confirmed_players` e
`max_confirmed_players` contam apenas jogadores de linha. Configure também
`min_confirmed_goalkeepers` e `max_confirmed_goalkeepers` (por exemplo, 18/18
jogadores e 2/2 goleiros). Limites máximos nulos deixam as vagas sem limite;
`min_confirmed_goalkeepers = null` mantém a capacidade conjunta dos eventos antigos.
A migration `014_goalkeeper_confirmations.sql` adiciona essas colunas e adapta a
fila do banco: uma vaga liberada só promove alguém da mesma função.

O agendamento aceita esses campos. Antes do início, organizadores podem alterá-los
em `POST /my-groups/{group_id}/events/{event_id}/confirmation-settings`; salvar
invalida a formação anterior e atualiza a lista de espera. A configuração é
preservada nos eventos recorrentes. A confirmação aceita `{ "role": "player" }`
ou `{ "role": "goalkeeper" }`; repetir a mesma função é idempotente e alterá-la,
enquanto as inscrições estiverem abertas, submete a pessoa às vagas da nova função.

O sorteio separa jogadores de linha e goleiros. Com exatamente dois goleiros,
18 jogadores formam três times de seis jogadores de linha. Os goleiros são
sorteados entre os dois times do primeiro confronto; nas partidas seguintes,
o goleiro do time que sai assume o time que entra, inclusive após desempate.
A escalação de cada partida fica preservada para histórico e estatísticas.
Com três ou quatro goleiros, cada um permanece no time em que foi escalado;
há no máximo um goleiro por time. Eventos antigos mantêm o sorteio anterior até
que a separação seja ativada.

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

`GET /my-groups/{group_id}/events/{event_id}/rankings` retorna as mesmas categorias
do ranking do grupo, limitadas às partidas finalizadas daquele evento. Está
disponível para membros do grupo também após o encerramento, independentemente
do calendário de temporadas. O app oferece acesso pela tela do evento e pelo histórico.

As trocas temporárias usam `POST /my-groups/{group_id}/events/{event_id}/matches/{match_id}/temporary-players`
com `team_id`, `presence_id` (quem entra de um time da fila) e
`outgoing_presence_id` (quem sai do time em campo). A função deve ser a mesma.
A migration `015_temporary_substitutions.sql` preserva a escalação e marca quem
sai com `is_active=false`: ele não recebe vitória, derrota, participação ou gols
sofridos daquela partida. Seus lances anteriores permanecem na súmula e nos
rankings, mas novos lances exigem um jogador ativo. A troca é idempotente,
mantém a quantidade de jogadores ativos e não altera a formação do evento;
na próxima partida a escalação original volta. Registros anteriores à migration
permanecem ativos, pois não há informação histórica de quem ficou fora.

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

## Avaliações privadas e parâmetros de sorteio

Owners e administradores avaliam os jogadores em cada grupo, de **0 a 10**,
com até **uma casa decimal**, incluindo a própria avaliação. Jogadores comuns
não podem consultar ou alterar nenhuma nota. As notas são privadas, independentes
por grupo e não aparecem nos perfis públicos, rankings ou CRUD genérico.
Nas listas dos times, somente responsáveis veem as notas atuais dos
jogadores, incluindo a própria avaliação.
`GET /my-groups/{group_id}/events/{event_id}/team-ratings` retorna as avaliações
autorizadas do elenco; jogadores comuns recebem um mapa vazio. O endpoint de
ciclo de partidas continua sem notas. Ausência de avaliação aparece como
"Sem avaliação", sem confundir com o valor neutro usado no cálculo.

- `GET/POST /my-groups/{group_id}/members/{profile_id}/rating`: consulta ou salva
  `{ "rating": 7.5 }`; `null` remove a avaliação. Exige responsável pelo grupo e
  jogador pertencente ao grupo. Alterações são permitidas mesmo durante eventos.
- `GET/POST /my-groups/{group_id}/draw-settings`: configura `use_positions`,
  `use_ratings` e `use_wins`. Apenas responsáveis podem salvar. Todos os critérios
  começam desligados; nesse caso, o sorteio continua aleatório.

O sorteio considera os critérios ativos na ordem **posição → nota → vitórias**.
Usa posições da modalidade do evento (preferências múltiplas contribuem igualmente),
avaliações atuais do grupo e vitórias em partidas finalizadas desse grupo, incluindo
todas as temporadas. Eventos cancelados e jogadores que ficaram fora da partida
não contam para vitórias. Sem avaliação, o cálculo usa 5,0; sem histórico, zero
vitórias. Convidados recebem os mesmos valores neutros e suas vitórias existentes.

O algoritmo distribui os jogadores e melhora a formação por trocas que reduzem a
diferença entre times. A comparação respeita a prioridade: um critério posterior
nunca piora um anterior para melhorar sua pontuação. Quantidade de jogadores e
vagas separadas de goleiros são preservadas; empates têm desempate aleatório.
O balanceamento é heurístico, não uma garantia de encontrar a formação ótima.
Com dois goleiros, o rodízio existente entre as partidas continua funcionando.
Mudanças de notas ou parâmetros valem para o próximo sorteio, sem alterar times
já montados. A seleção e as trocas manuais continuam disponíveis.

Migration aditiva: `016_draw_settings_and_ratings.sql`. Ela também é aplicada na
inicialização de desenvolvimento. Testes: `tests/test_draw.py` e
`tests/test_team_balance.py`, além das regressões de ciclo e goleiros.

## Dados fictícios para teste

`scripts/seed_demo.py` popula um grupo existente de forma idempotente. A senha é
lida de `FUT_MANAGER_DEMO_PASSWORD`; não é necessário editar o script.
O seed também cria ou atualiza a conta de demonstração `email@email.com`, com
senha `senha123`, e garante seu vínculo ativo como `owner` em todos os grupos
existentes. Ao repetir o seed, essa senha é restaurada se tiver sido alterada;
as senhas das demais contas e os criadores originais dos grupos são preservados.
Use `--group-id UUID --saturday 2026-09-26 --start-now` para criar três eventos
históricos e um evento atual com seis confirmados. O script preserva registros
existentes e não reinicia um evento que o usuário já começou a testar.

Acrescente `--seasons` para preparar temporadas semanais: três encerradas e uma
atual com uma partida finalizada, além do evento disponível para testar o ciclo.
Configurações de temporadas já existentes são preservadas ao repetir o seed.

## Temporadas opcionais

A migration `009_group_seasons.sql` adiciona configurações ao grupo e períodos
com rankings arquivados. Por padrão, temporadas ficam desativadas e o ranking
continua acumulando todas as partidas. Owners e administradores podem ativar a
opção em `POST /my-groups/{group_id}/settings`, usando
`{"enabled": true, "duration_days": 30}`. Durações válidas: 1 a 3650 dias.

O primeiro período começa ao ativar. Alterar a duração afeta a próxima temporada;
desativar encerra a atual, preserva seu histórico e restaura o ranking geral.
Reativar inicia um novo período, sem reabrir ou alterar os anteriores.

As partidas são contabilizadas pela finalização (`ended_at`), no intervalo
`starts_at <= ended_at < ends_at`. Partidas antigas sem esse campo usam a data
de início ou, na ausência dela, a data do evento. Não há exclusão de estatísticas.
A virada é reconciliada automaticamente na consulta de configurações, rankings
ou temporadas, sob lock do grupo, inclusive após vários períodos sem acesso.
Rankings de períodos encerrados são persistidos como snapshots somente de leitura.

- `GET /my-groups/{group_id}/settings`: configuração e temporada atual.
- `GET /my-groups/{group_id}/season-rankings`: período atual e seu ranking; sem
  temporadas, retorna o ranking geral.
- `GET /my-groups/{group_id}/seasons`: temporadas encerradas.
- `GET /my-groups/{group_id}/seasons/{season_id}/rankings`: registros arquivados.

O endpoint existente `/rankings` mantém o formato de lista e considera apenas a
temporada atual quando a opção está ativada. Todas essas consultas exigem acesso
ao grupo. Pedidos de entrada continuam visíveis e gerenciáveis exclusivamente
por owners e administradores.

## Troféus de temporadas

A migration `010_season_trophies.sql` persiste os troféus de cada perfil. Quando
uma temporada é arquivada, todos os empatados no primeiro lugar de cada categoria
recebem a premiação. Categorias com contagem zero não premiam ninguém, exceto
goleiros que atuaram e terminaram com zero gols sofridos (menor total vence).
Convidados continuam no ranking, mas não recebem troféus por não terem perfil;
o segundo colocado não é promovido quando o líder é convidado.

`GET /auth/me/trophies` retorna o total, as quantidades por categoria e a lista
completa do usuário autenticado. O perfil também reconcilia temporadas vencidas
dos grupos em que o jogador participou. Não há endpoints de edição de troféus.
Uma chave única por temporada, perfil e categoria impede duplicatas. Os títulos
preservam o nome do grupo no momento da premiação.

O seed com `--seasons` inclui as premiações. Para premiar temporadas anteriormente
arquivadas sem alterar seus rankings:

```powershell
Get-Content -Raw scripts/backfill_trophies.py | docker compose exec -T api python -
```

Na base de demonstração, `carlos.teste@futmanager.test` possui troféus de artilharia
e outras categorias. Contas que não disputaram partidas exibem a coleção vazia.

### Troféus exclusivos dos campeonatos

A final concede campeão e vice-campeão a todos os jogadores dos elencos inscritos,
e artilheiro/líder de assistências a todos os empatados na maior marca positiva.
As quatro categorias são exclusivas dos campeonatos, separadas dos rankings de
pelada, e aparecem na edição e na coleção do perfil. A premiação é transacional e
idempotente; títulos preservam o nome e a edição do campeonato.

O resultado aceita `statistics: [{profile_id, goals, assists, own_goals}]`.
Só jogadores inscritos nos dois times podem receber estatísticas. Gols próprios
mais gols contra adversários devem bater exatamente com o placar. Assistências
não podem exceder gols do time nem incluir assistência para o próprio gol.
Disputas de pênaltis não contam para artilharia. O app envia as estatísticas ao
confirmar o resultado. Clientes antigos podem omiti-las, mas uma edição com
partidas sem atribuição completa dos gols não distribui troféus individuais.

A migration `018_cascade_trophies.sql` adiciona estatísticas e troféus e limita
novas cascatas a quatro times. Edições legadas de cascata com 8/16 vagas são
preservadas, mas não podem iniciar; é necessário criar uma edição de quatro.
Com `create_schema_on_startup`, a migration 018 também roda na inicialização.
### Código de convite do campeonato

Cada campeonato recebe um código único de seis caracteres A–Z/0–9, gerado pelo
banco. A migration `019_championship_codes.sql` preenche códigos das edições
existentes e instala o gerador para novas edições; também roda na inicialização
com `create_schema_on_startup`. Reaplicar preserva os códigos já atribuídos.
`GET /championship-discovery/search?code=AACO7E` exige login, aceita minúsculas e
retorna a edição. A inscrição continua usando `/championships/{id}/entries`, com
as mesmas validações de responsável, elenco, vagas e situação do campeonato.

### Súmula dos campeonatos

A migration `020_championship_actions.sql` adiciona a súmula persistente às partidas existentes, preservando os resultados anteriores. Aplique-a antes de atualizar a API em ambientes sem criação automática de esquema.

O organizador registra ou remove gols, assistências, gols contra e cartões em `/championships/{id}/matches/{match_id}/actions` e `/actions/{action_id}/remove`. Cada lance usa um UUID para evitar duplicação em tentativas repetidas. A finalização envia `action_ids` na ordem da súmula, calcula as estatísticas a partir dos lances salvos e rejeita uma súmula desatualizada. Resultados antigos continuam disponíveis; seus lances não são reconstruídos a partir dos totais.

## Criar um banco novo com SQL

O arquivo `src/databases/scripts/create_database.sql` contém o esquema completo para PostgreSQL 17: 26 tabelas, enums, índices, chaves, funções, sequências e gatilhos, incluindo campeonatos e súmulas. Não inclui contas, senhas nem dados de demonstração.

1. Crie um banco vazio no provedor ou execute `CREATE DATABASE fut_manager WITH ENCODING 'UTF8';` conectado ao banco administrativo `postgres`, fora de uma transação.
2. Conecte-se ao banco novo e execute o arquivo inteiro no editor SQL, ou use:

```bash
psql -h HOST -U USUARIO -d fut_manager -v ON_ERROR_STOP=1 -f src/databases/scripts/create_database.sql
```

3. Configure as variáveis `FUT_MANAGER_DATABASE_*` da API para esse banco. Em produção, use `FUT_MANAGER_CREATE_SCHEMA_ON_STARTUP=false` e aplique futuras migrações versionadas.

O script é transacional e destinado apenas à primeira criação: não o reaplique em um banco existente. IDs e valores definidos como defaults Python são preenchidos pela API. Para atualizar o arquivo após mudanças nos modelos/bootstrap, execute `python -m scripts.export_database_schema` no ambiente configurado da API; a geração não lê dados do banco.

## Documentação da API no deploy

Configure `FUT_MANAGER_DOCS_ENABLED=false` em produção para desativar `/docs`, `/redoc`, `/openapi.json` e o redirecionamento OAuth do Swagger. As rotas normais da API continuam disponíveis. A configuração é independente de `FUT_MANAGER_DEBUG` e, sem a variável, o padrão da aplicação é `false`.

Para desenvolvimento, use `FUT_MANAGER_DOCS_ENABLED=true`. O Docker Compose local usa `true` por padrão e permite sobrescrever pela variável de ambiente ou pelo `.env`. Reinicie a API após alterar a configuração; no Compose, recrie o serviço com `docker compose up -d --force-recreate api`.
