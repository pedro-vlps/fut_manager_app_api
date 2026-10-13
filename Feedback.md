# Feedback dos testes do campeonato

Data: 13/10/2026. Alterações implementadas na API e no aplicativo, conforme os pontos levantados no teste e a confirmação sobre as duas modalidades de punição.

## 1. Punições: desclassificação e perda de pontos

Foi adicionado o menu **Punições** para o organizador. É possível selecionar um ou mais times, informar o motivo e revisar antes de confirmar. O registro guarda o tipo, a quantidade de pontos, o responsável e a data.

- **Perda de pontos:** desconta da tabela dos formatos liga e grupos + mata-mata; o time continua jogando. Descontos sucessivos são acumulados e podem produzir pontuação negativa.
- **Desclassificação:** vale apenas para esta edição. Resultados finalizados são preservados; jogos pendentes do time recebem WO para o adversário. Times desclassificados saem das vagas de avanço e das premiações individuais.
- **Dois times desclassificados na mesma partida:** o jogo fica sem vencedor; as vagas da próxima fase são preenchidas pelos próximos elegíveis na classificação, sem duplicar participantes já classificados. Se faltarem times para a chave original, a fase seguinte usa uma chave reduzida. Na cascata, essa situação pode transformar a continuidade em uma fase de eliminação simples. Com um único time elegível, ele encerra a edição como campeão.
- Não é permitido desclassificar todos os times ou alterar punições depois de encerrada a edição. Punições aplicadas não têm fluxo de reversão nesta versão.

**API:** `ChampionshipEntry` ganhou `disqualified`, `points_deducted` e `punishments`. A progressão das fases e os WOs automáticos ficam em `progress_championship`; o comando é `POST /championships/{id}/punishments`, protegido pelo organizador e pelo lock da edição.

**Aplicativo:** novo `src/components/championship-punishments.tsx`, integrado ao menu e à tela de histórico. A classificação mostra times desclassificados e penalizados.

## 2. Vitória por WO

Cada jogo pendente oferece a escolha do vencedor por WO. O servidor fixa o placar em **3 a 0**, mesmo que um cliente envie outro placar. Na liga e nos grupos, o vencedor recebe os pontos e +3 de saldo; em fases eliminatórias, avança normalmente.

Não são gerados gols, assistências, partidas individuais ou gols sofridos de goleiros. A súmula é considerada completa para a premiação. Um WO manual exige retirar lances e goleiros já informados. Em desclassificações, a limpeza da partida pendente é automática.

**API:** `Score.walkover` e `ChampionshipMatch.walkover`; classificação usa o placar oficial, enquanto os rankings individuais ignoram WO.

**Aplicativo:** `championship-match.tsx` oferece os botões de WO; os resultados e a súmula identificam o motivo do placar.

## 3. Sala de troféus dos times

Os títulos conquistados ficam em **Meus times** e também na página do time dentro do campeonato, incluindo conquistas de outras edições. São apresentados o campeonato e a temporada.

**API:** os títulos são consultados pelas edições finalizadas com `champion_id` correspondente. Essa abordagem inclui conquistas antigas sem duplicar uma tabela de títulos. `ClubView.trophies` e `GET /clubs/{id}/trophies` fornecem a sala.

**Aplicativo:** `clubs.tsx` e `championships/team.tsx` exibem as taças e as edições.

## 4. Troféus coletivos e individuais

Na edição, campeão e vice aparecem uma vez por time. Os troféus coletivos dos jogadores continuam no histórico pessoal dos integrantes do elenco inscrito.

Há um único vencedor de **artilharia**, **assistências** e **melhor goleiro**. A categoria decide a liderança e a colocação esportiva do time desempata: campeão primeiro, seguido dos times que chegaram mais longe e da classificação geral. O goleiro é o primeiro do ranking de menos gols sofridos entre quem atuou no gol; WO não cria atuações. Empates remanescentes dentro da mesma colocação usam o UUID do perfil, de modo que o ranking e a premiação tenham exatamente a mesma ordem. Categorias sem jogadores elegíveis não recebem prêmio.

**API:** `player_rankings` inclui `team_position`; `trophy_winners` entrega um vencedor por categoria. Foi adicionada `championship_goals_conceded`. `edition_awards` resume as conquistas coletivas na resposta. O script `scripts/reconcile_championship_awards.py` corrige as premiações individuais antigas, removendo os empatados que não venceram pelo novo desempate e incluindo o melhor goleiro.

**Aplicativo:** `ranking-tabs.tsx` usa a colocação do time e a mesma ordem de desempate da API; `championship-archive.tsx` apresenta os títulos coletivos pelo time. A categoria de goleiro ganhou símbolo próprio.

## 5. Sorteio dos grupos

A tela de grupos agora oferece **Sortear grupos aleatoriamente**, além das trocas manuais. O sorteio distribui todos os inscritos uma vez, respeitando grupos de quatro ou, para 12 times, quatro grupos de três.

**API:** `POST /championships/{id}/groups/draw` usa `SystemRandom` e reaproveita as validações da divisão manual. Apenas o organizador pode sortear, com todas as vagas preenchidas e antes de resultados, lances ou goleiros registrados.

**Aplicativo:** botão integrado em `championship-groups.tsx`, com atualização da divisão salva e descarte do rascunho anterior.

## 6. Súmula resumida em todos os registros

Ocorrências repetidas do mesmo jogador, time e tipo aparecem agrupadas: por exemplo, **2x Gols · Jogador** ou **3x Cartões amarelos · Jogador**. O banco continua guardando cada lance separadamente.

**API:** a súmula de peladas passou a incluir `person_id`, evitando misturar jogadores com o mesmo nome. Campeonatos já tinham o identificador no lance.

**Aplicativo:** o componente compartilhado `event-ui.tsx` resume gols, gols contra, assistências e cartões em todos os formatos que usam a súmula. **Remover 1** retira somente uma ocorrência; os detalhes do minuto permanecem quando há uma única ocorrência.

## 7. Proteção dos dados pessoais

Foi adicionada criptografia autenticada de campos com **Fernet/MultiFernet**, usando a dependência `cryptography`. Estão protegidos em repouso: nome e e-mail do perfil, URL de avatar, nome do convidado, súmulas de campeonato que contêm nomes e snapshots de rankings de temporadas.

A busca de e-mail usa um **índice HMAC-SHA256** (`email_lookup`), normalizado e único. Login e convites por e-mail foram adaptados. Históricos cifrados de temporadas são decifrados pela aplicação para localizar a participação, preservando a consulta de troféus antigos. Essa consulta atualmente percorre os snapshots arquivados; em bases grandes, um índice relacional de participantes será uma evolução útil.

Senhas permanecem como hashes irreversíveis com salt. O scrypt foi fortalecido para `N=131072`, `r=8`, `p=1`; hashes anteriores são aceitos e atualizados após um login válido. O CRUD público de `/profiles` foi retirado da aplicação principal para impedir exposição dos e-mails; cadastro e consulta própria usam `/auth/register` e `/auth/me`.

**Estrutura:** funções criptográficas em `src/helpers/privacy.py`; tipos de persistência em `src/models/privacy.py`; configuração em `settings.py`; novas variáveis `FUT_MANAGER_PERSONAL_DATA_KEYS` e `FUT_MANAGER_EMAIL_LOOKUP_KEY`. A aplicação exige chaves válidas para iniciar. Nenhuma chave de produção foi criada ou colocada no Git.

A lista de chaves Fernet permite rotação: a primeira cifra os novos dados e as demais leem dados antigos. Com a API parada, `scripts/encrypt_personal_data.py` recifra os registros com a chave atual e atualiza o índice de e-mail. Preserve as chaves necessárias para ler os backups antigos.

Referências: [Fernet](https://cryptography.io/en/latest/fernet/) e [armazenamento de senhas da OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

## 8. Convites privados e renováveis

Os códigos de grupo, time e campeonato são retornados somente a seus administradores/responsáveis. A restrição é aplicada na API, além da interface. O CRUD genérico dos grupos também oculta o código. A busca por convite não devolve o código ao visitante.

**API:** renovação em `POST /my-groups/{id}/code/rotate`, `/clubs/{id}/code/rotate` e `/championships/{id}/code/rotate`. A renovação invalida a busca pelo código anterior. Times ganharam código próprio, sequência geradora e o estado de membro `requested`; `POST /club-discovery/join` pede entrada e o responsável aprova ou recusa em `/clubs/{id}/members/{profile_id}/review`. Os convites por e-mail continuam funcionando.

**Aplicativo:** códigos e renovação aparecem nas áreas administrativas. **Meus times** permite pedir entrada por código e revisar os pedidos. A mudança não remove vínculos ou pedidos já existentes.

## 9. Feed de campeonatos

A lista de campeonatos passou a ser apresentada como **Feed de campeonatos**, com busca por nome/temporada e acesso às edições. Jogos, resultados, classificações, elencos e rankings podem ser consultados por usuários que não participam do campeonato.

**API:** `GET /championship-feed` mantém o contrato de listagem e os códigos privados; os detalhes continuam em `/championships/{id}`. **O feed exige uma conta autenticada**, mas não inscrição na edição. Escritas continuam protegidas pelas permissões de organizador ou responsável pelo time.

**Aplicativo:** atualização de `championships/index.tsx` e aproveitamento das telas de detalhes, resultados e rankings.

## 10. Liga com qualquer quantidade de times a partir de dois

Foi removida a restrição de 4/8/12/16 para ligas. A quantidade informada na criação é uma estimativa; as inscrições não têm teto fixo. Ao iniciar, o calendário usa a quantidade efetivamente inscrita, exigindo pelo menos dois times.

O algoritmo de rodízio foi ajustado para quantidades ímpares, usando folgas sem gerar jogos com participantes vazios. Turno único tem `n(n−1)/2` jogos; ida e volta tem `n(n−1)`. Cada time participa no máximo uma vez por rodada.

**API:** ajustes em `ChampionshipCreate`, constraints do modelo/banco, inscrição, início e `initial_fixtures`.

**Aplicativo:** entrada numérica no formulário da liga, inscrições sem bloqueio por capacidade estimada e cálculo correto das rodadas e dos turnos para quantidades ímpares. Os demais formatos mantêm suas capacidades e regras existentes.

## 11. READMEs para portfólio

Os dois READMEs foram reescritos para apresentar a proposta do projeto, funcionalidades, tecnologias, arquitetura e decisões de implementação, com instruções de execução e validação mais curtas.

A documentação técnica anterior foi preservada em **`docs/DEVELOPMENT.md`** de cada repositório. Ela recebe um aviso de que as regras atuais estão no README e neste feedback.

## Migração e ativação em um banco existente

**O banco usado no seu campeonato não foi alterado.** Os testes utilizaram um PostgreSQL descartável na porta 55439 e chaves geradas somente em memória.

Para ativar esta versão no banco atual:

1. Faça backup do banco e preserve as chaves privadas já utilizadas. Pare a API durante a atualização.
2. Instale as dependências com `poetry install` e configure, fora do Git, `FUT_MANAGER_PERSONAL_DATA_KEYS` como lista JSON de chaves Fernet válidas e `FUT_MANAGER_EMAIL_LOOKUP_KEY` como um segredo aleatório independente de pelo menos 32 caracteres. Não utilize a chave de cifragem como chave do índice.
3. Partindo do schema atualizado até a migration 024, execute **`poetry run python -m scripts.apply_feedback_migrations`**. O comando aplica 025, 026 e 027, cifra os dados existentes, preenche o índice de e-mail e reconcilia os prêmios de edições encerradas.
4. Inicie a API somente após o comando concluir com sucesso e disponibilize o novo aplicativo/PWA. No banco existente, prefira `FUT_MANAGER_CREATE_SCHEMA_ON_STARTUP=false` e migrations explícitas.

**025:** capacidades de liga, punições, WO, códigos dos times e pedidos de entrada. **026:** colunas de texto cifrado e índice cego de e-mail. O bootstrap `create_schema.py` e o arquivo `create_database.sql` foram atualizados para instalações novas.

O backfill é transacional e pode ser reexecutado com as mesmas chaves. A aplicação lê valores legados durante a migração, mas eles só ficam protegidos após o backfill. Não descarte as chaves: perder a chave impede recuperar os dados cifrados.

## Ajustes técnicos complementares

- Dependência de testes `httpx` declarada no grupo `dev` do Poetry.
- Dependência `tzdata` para calendários e temporadas também funcionarem no Windows.
- Consultas SQL existentes de sorteio/avaliação movidas de `controllers/draw.py` para `services/draw.py`, preservando os testes de arquitetura.
- `FUT_MANAGER_ENV_FILE` permite desativar a leitura do `.env` em testes isolados, evitando herdar configurações privadas.
- Scripts de validação isolada: `run_feedback_tests.py` e `verify_feedback_upgrade.py`; a fixture `tests/fixtures/pre_feedback_schema.sql` preserva o schema legado sem dados. Logs locais de testes ficam ignorados pelo Git.
- O arquivo preexistente não versionado `scripts/upgrade_championships_020_024.sql` foi preservado.

## Validação

- Suite ampla da API: **120 testes executados**; 119 passaram e o caso de atualização de hash legado revelou uma falha de refresh do perfil. A falha foi corrigida e a reexecução dos **20 testes afetados passou integralmente**.
- Migrations em banco legado com dados: **aprovadas**, incluindo segunda execução, decifragem e preservação dos valores.
- Instalação pelo SQL completo atual: **aprovada**, incluindo geração dos códigos, liga ímpar e escrita cifrada.
- Aplicativo: **TypeScript, lint sem cache, 8 testes de datas e build de produção da PWA aprovados**.
- Verificação de configurações privadas nos dois repositórios: **zero ocorrências**.
- Não foi feita validação visual manual em aparelho Android/iOS.

A validação inclui migração do schema legado com dados em texto, reexecução do backfill, login após decifragem, WO em todos os formatos, punição simultânea, perda de pontos, privacidade/renovação de convites e desempate de prêmios.


## 12. Complemento: segundo amarelo gera vermelho na mesma partida

A regra foi aplicada às súmulas de peladas e campeonatos: dois amarelos do mesmo jogador na mesma partida geram exatamente um vermelho automático. Os rankings registram **2 amarelos e 1 vermelho**. O critério vale também para convidados e é reiniciado em cada partida.

O reenvio do mesmo lance não duplica os cartões. Cartões adicionais são recusados para quem já recebeu vermelho. A remoção de qualquer um dos amarelos retira o vermelho automático; vermelhos diretos permanecem independentes. Para corrigir um vermelho automático, deve-se remover um amarelo: não é possível apagar apenas o vermelho e deixar os dois amarelos.

**API:** regra compartilhada em `src/helpers/cards.py`; sincronização nos controllers de peladas e campeonatos; consulta dos lances da pessoa em `LifecycleService.person_actions`. O identificador do vermelho automático é determinístico por pessoa e partida. Nas peladas, a origem automática usa o campo `GameAction.notes` já existente; nos campeonatos, usa `auto_generated` no JSON da súmula. As respostas passaram a incluir `auto_generated`. **Não é necessária nova migration para este complemento.** Os registros finalizados anteriores não foram modificados.

**Aplicativo:** `MatchLog` identifica o vermelho como **Automático · 2º amarelo**, permitindo corrigir os amarelos e mantendo o vermelho derivado protegido contra remoção isolada. O formulário de registro explica a regra ao selecionar amarelo; os contratos foram atualizados em `services/lifecycle.ts`.

**Validação:** 9 testes de integração/arquitetura/rankings aprovados, incluindo segundo amarelo de jogador cadastrado e convidado, reenvio, remoção/recriação, preservação de vermelho direto, rankings e nova partida. TypeScript e lint sem cache aprovados. A fixture compartilhada das peladas foi extraída para `LifecycleFixture`, sem duplicar os testes existentes.


## 13. Complemento: critérios para novas senhas

Novas senhas devem conter pelo menos **8 caracteres**, uma letra maiúscula, uma minúscula, um número e um caractere especial. O limite existente de 128 caracteres foi mantido. Espaços, quebras de linha e caracteres invisíveis não atendem ao critério de caractere especial; pontuação e símbolos atendem. Letras acentuadas são aceitas.

**API:** validação compartilhada em `src/helpers/password_policy.py`, aplicada a `ProfileCreateSchema` e `ProfileUpdateSchema`. Cadastros que descumprem qualquer critério recebem HTTP 422. Alterações de perfil sem envio de senha continuam possíveis; enviar senha nula é recusado. O contrato do login e a rotina de hash continuam aceitando senhas de contas antigas, inclusive ao fortalecer hashes legados: a política vale ao definir uma senha nova.

**Aplicativo:** `src/services/password-policy.ts` reproduz os critérios da API, com contagem de caracteres Unicode consistente. `src/app/login.tsx` mostra a lista dos critérios no cadastro, atualiza os indicadores durante a digitação, bloqueia o cadastro com senha incompleta e informa o motivo da validação. O modo de login não aplica a política às senhas existentes.

**Validação:** 14 testes da API aprovados (política, cadastro, atualização de schema, autenticação, posições e arquitetura); 12 testes do aplicativo aprovados (incluindo 4 novos casos da política), além de TypeScript e lint sem cache. Testados critérios ausentes, espaços/invisíveis, letras acentuadas, símbolos, limites de tamanho, cadastro válido e login de conta legada. Não é necessária nova migration.


## 14. Complemento: READMEs em inglês e português

Nos dois repositórios, `README.md` passou a usar inglês como idioma padrão. A versão em português foi preservada em `README.pt-BR.md`. Os arquivos têm um seletor de idioma no topo, com links relativos para alternar entre **English** e **Português (Brasil)** diretamente no GitHub.

Foram traduzidos os textos, títulos, tabelas e rótulos dos diagramas, mantendo os comandos, caminhos e informações técnicas equivalentes. Links na versão inglesa indicam quando a documentação complementar ainda está em português.


## 15. Complemento: goleiro titular e substituições nos campeonatos

O responsável pelo time pode definir o **goleiro titular padrão** em **Meus times**. Na inscrição, a edição captura esse titular se ele pertencer ao elenco inscrito. Os confrontos recebem os goleiros automaticamente, inclusive nas próximas fases, sem precisar indicá-los a cada jogo.

Na página do time e antes do início da partida, o responsável pode ajustar o titular daquela edição. A mudança atualiza os jogos que ainda não começaram e a geração de fases futuras. Escolhas específicas feitas pelo organizador para uma partida são preservadas. Mudar o padrão do clube também atualiza as edições abertas em que o novo goleiro já está inscrito; um jogador adicionado posteriormente ao clube não entra automaticamente em um elenco já registrado.

O organizador confirma **Iniciar partida com estes goleiros**. Durante o jogo, a tela passa a oferecer **Substituição de goleiro**, com seleção e confirmação da troca comunicada pelo time. Somente o organizador registra essa substituição; a mudança do titular pelo time não altera o jogo em andamento.

Conforme confirmado pelo usuário, cada gol sofrido é atribuído ao goleiro que estava no gol no momento do lance. Isso inclui gols contra. Quando dois goleiros atuam, ambos recebem uma partida como goleiro, mesmo se não sofrerem gols; se um goleiro sair e voltar, a participação é contada uma única vez. Remover um gol não transfere os demais para outro goleiro. O histórico de substituições permanece consultável na súmula.

WO pode ser registrado com titulares previamente definidos, desde que a partida ainda não tenha começado. Os titulares não recebem partidas, gols sofridos ou outros números individuais por WO. Placares legados sem lances continuam usando o goleiro único da partida; um placar positivo com múltiplos goleiros exige a súmula para evitar atribuição ambígua dos gols.

**API / estrutura:**

- `Club.starting_goalkeeper_id`: padrão do time permanente.
- `ChampionshipEntry.starting_goalkeeper_id`: titular do elenco inscrito na edição.
- `ChampionshipMatch.started_at`, `goalkeeper_history` e flags de escolha específica: início, atuações e preservação das escolhas por partida.
- Os lances de gol e gol contra guardam `goalkeeper_id` no JSON cifrado, preservando quem sofreu cada gol.
- `src/helpers/championship_goalkeepers.py`: início das atuações, identificação do time que sofreu o gol e contagem por goleiro.
- `POST /clubs/{id}/goalkeeper`: titular padrão, protegido pelo responsável do time.
- `POST /championships/{id}/clubs/{club_id}/goalkeeper`: titular da edição, limitado ao próprio elenco inscrito.
- `POST /championships/{id}/matches/{match_id}/kickoff`: início confirmado pelo organizador.
- O endpoint `/goalkeepers` permite ajuste antes do início e registra substituições depois. Clientes antigos que registram um lance sem chamar `/kickoff` iniciam a partida automaticamente.

**Aplicativo:** seletor em `clubs.tsx`, novo componente `championship-starting-goalkeeper.tsx`, integração na página do time e antes do jogo, confirmação do início, confirmação da substituição, histórico e contratos atualizados. Os grupos podem ser reorganizados antes dos jogos mesmo com titulares preenchidos automaticamente.

**Migração:** foi adicionada **027_starting_goalkeepers.sql**, incluída no bootstrap, no SQL completo exportado e em `scripts/apply_feedback_migrations.py`. Em um banco existente, com a API parada e as chaves privadas configuradas, execute `poetry run python -m scripts.apply_feedback_migrations` antes de iniciar esta versão. As escolhas e os resultados legados são preservados; os titulares novos são definidos pelos responsáveis. O banco real do campeonato não foi modificado.

**Validação:** preenchimento dos confrontos e fases futuras, permissões, manutenção dos jogos em andamento, atribuição de gols e gols contra, remoção de lance, retorno do goleiro, WO, preservação de escolhas específicas e reexecução da migration. A instalação nova e a atualização do schema legado foram verificadas no PostgreSQL temporário. TypeScript, lint sem cache e build da PWA aprovados.
