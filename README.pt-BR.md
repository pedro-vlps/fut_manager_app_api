# Fut Manager · API

[English](https://github.com/pedro-vlps/fut_manager_app_api?tab=readme-ov-file) | **Português (Brasil)** | [Guia de desenvolvimento](https://github.com/pedro-vlps/fut_manager_app_api?tab=contributing-ov-file)

Fut Manager é um projeto pessoal para organizar o futebol amador: da confirmação de presença na pelada ao título de um campeonato. A API concentra as regras da competição, os resultados e o histórico dos jogadores e times.

O projeto nasceu de uma necessidade prática de organizar jogos e já passou por testes em um campeonato real. Está em evolução rumo ao MVP, com ajustes orientados pelo uso em campo.

## Decisões de engenharia e código para explorar

Desenvolvido por **[Pedro Vieira](https://github.com/pedro-vlps)** como projeto de portfólio de ponta a ponta: modelagem do domínio, contratos da API, persistência, segurança, testes de regressão e deploy. A implementação demonstra desenvolvimento backend a partir de problemas concretos:

| Desafio | Implementação | Código / evidência |
| --- | --- | --- |
| Separar HTTP e persistência | Rotas delegam aos controllers; consultas SQL ficam nos services, com testes que verificam os limites da arquitetura | [Rotas](src/routers), [services](src/services), [testes de arquitetura](tests/test_architecture.py) |
| Manter consistência em escritas concorrentes | Bloqueios de linha no banco serializam alterações de uma edição ou evento dentro da transação | [Services de campeonatos](src/services/championships.py), [proteção de eventos](src/services/event_write_guard.py), [rechecagem de permissões](tests/test_group_roles.py) |
| Evoluir regras complexas de competição | Classificação, calendário, WO, punições e premiações têm helpers de domínio e casos de regressão explícitos | [Helpers de domínio](src/helpers), [testes de campeonatos](tests/test_championships.py), [testes de premiações](tests/test_trophies.py) |
| Proteger dados pessoais e permitir buscas | Criptografia autenticada nos campos pessoais, índice HMAC independente para e-mail e hashes scrypt com salt | [Helpers de privacidade](src/helpers/privacy.py), [autenticação](src/controllers/auth.py), [testes de senhas](tests/test_password_policy.py) |
| Testar persistência real | Testes HTTP assíncronos usam PostgreSQL e rollback; o runner isolado cria o schema e chaves efêmeras | [Testes de autenticação](tests/test_auth.py), [runner isolado](scripts/run_feedback_tests.py) |

A API também utiliza minha biblioteca **[api_crud_generate_libary](https://github.com/pedro-vlps/api_crud_generate_libary)** para infraestrutura compartilhada de CRUD. Permissões específicas e regras de competição ficam neste repositório.

**Limites atuais:** o MVP está em desenvolvimento. As sessões de autenticação ficam em memória no processo; reinícios invalidam sessões e múltiplos workers exigiriam armazenamento compartilhado. Scripts de migração versionados precisam ser executados em ordem explícita; a criação de schema no startup atende instalações novas. São próximos passos concretos para operar em maior escala.

## O que o projeto oferece

- **Grupos de pelada:** convites, pedidos de entrada aprovados por administradores, membros e convidados.
- **Organização dos eventos:** agenda, recorrência semanal, confirmação de presença e lista de espera, com vagas para jogadores e goleiros.
- **Montagem de times:** sorteio com preferências de posição, avaliações e desempenho para equilibrar os elencos.
- **Partidas e súmulas:** gols, assistências, gols contra, cartões, goleiros, substituições e cronômetro.
- **Campeonatos:** liga, grupos com mata-mata, eliminação simples e cascata com chaves de vencedores e perdedores.
- **Regulamento em ação:** sorteio dos grupos, WO de 3 a 0, perda de pontos e desclassificação com continuidade do chaveamento.
- **Rankings e conquistas:** estatísticas, temporadas, premiações individuais e sala de troféus dos times.
- **Acompanhamento:** feed para consultar campeonatos, jogos, resultados e rankings mesmo sem participar da edição, com uma conta autenticada.

## Regras que fazem a diferença

A liga aceita qualquer quantidade de times a partir de dois, inclusive quantidades ímpares. O calendário usa os inscritos no momento do início, em turno único ou ida e volta, com folgas quando necessário.

WO vale 3 a 0 para o time presente. O placar entra na classificação e no saldo de gols, sem gerar gols, assistências ou desempenho artificial para os jogadores. Em fases eliminatórias, o vencedor avança.

As punições ficam registradas por edição. Perda de pontos mantém o time na disputa; a desclassificação retira suas vagas de avanço e transforma seus jogos futuros em WO. Resultados já disputados são preservados.

Os times podem predefinir seu goleiro titular, preenchido automaticamente nos jogos. O organizador registra as substituições durante a partida, e cada gol sofrido permanece com quem estava no gol naquele lance.

Cada premiação individual tem um vencedor. O ranking da categoria define a liderança; a colocação do time resolve os empates, com o campeão à frente do vice. O melhor goleiro segue o ranking de menos gols sofridos entre os jogadores que atuaram no gol.

## Tecnologia e arquitetura

**Python 3.13 · FastAPI · Pydantic · SQLAlchemy assíncrono · PostgreSQL · Poetry · Docker**

```mermaid
flowchart LR
    App[Aplicativo / PWA] --> Routes[Rotas FastAPI]
    Routes --> Controllers[Regras e permissões]
    Controllers --> Helpers[Classificação e chaveamento]
    Controllers --> Services[Persistência assíncrona]
    Services --> DB[(PostgreSQL)]
```

As rotas delegam as operações aos controllers; os services concentram o acesso ao banco. Helpers implementam regras de classificação, calendário e premiação. Schemas tipados definem o contrato com o aplicativo e migrations versionadas permitem evoluir o banco.

As operações de resultados, inscrições e punições bloqueiam a edição durante a transação para manter o campeonato consistente em requisições concorrentes.

## Proteção de dados

Nomes, e-mails, URLs pessoais de avatar, nomes de convidados e cópias de nomes nas súmulas e históricos são cifrados em repouso com criptografia autenticada. Um índice HMAC permite localizar e-mails sem guardar seu texto no índice. Senhas usam scrypt com salt aleatório, com parâmetros fortalecidos para novos hashes e compatibilidade com os anteriores.

Novas senhas exigem pelo menos oito caracteres, uma maiúscula, uma minúscula, um número e um caractere especial.

Chaves ficam no ambiente privado, fora do Git. Códigos de convite são visíveis apenas para administradores e podem ser renovados. A API desativa o CRUD público de perfis; cadastro e consulta da própria conta passam pelas rotas de autenticação.

## Executar localmente

1. Instale Python 3.13+, Poetry e PostgreSQL, ou utilize Docker.
2. Execute `poetry install`.
3. Configure as variáveis de `.env.example` em um `.env` privado, incluindo as chaves de criptografia. A chave Fernet é gerada com `Fernet.generate_key()`; a chave de HMAC deve ser um segredo aleatório independente.
4. Para uma instalação nova, ative `FUT_MANAGER_CREATE_SCHEMA_ON_STARTUP=true`. Para bancos existentes, siga **a ordem de migração em [Feedback.md](Feedback.md)** antes de iniciar esta versão.
5. Execute:

```powershell
poetry run python -m uvicorn src.__main__:app --reload
```

A documentação interativa fica em `/docs` quando `FUT_MANAGER_DOCS_ENABLED=true`. Não configure credenciais ou chaves reais em arquivos versionados.

## Validação

Os testes cobrem autenticação, permissões, confirmação de presença, calendários, classificações, chaveamento e premiações. A suite de feedback acrescenta WO, punições simultâneas, ligas ímpares, renovação de convites e persistência cifrada.

```powershell
poetry run python -m unittest discover -s tests -v
```

Com uma instância isolada de PostgreSQL já disponível na porta 55439, use `poetry run python -m scripts.run_feedback_tests`. Esse comando é destinado exclusivamente ao banco de teste isolado.

## Integração contínua e Railway

Os dois repositórios estão publicados no Railway, com redeploy automático pela `main`. O GitHub Actions executa em **todo push e pull request**, além de permitir execução manual.

O [workflow de testes da API](.github/workflows/tests.yml) instala as dependências do lockfile com Python 3.13 e Poetry 2.3.3, inicia PostgreSQL 17 descartável na porta 55439 e executa toda a suite unittest pelo runner isolado. Não conecta ao banco publicado nem utiliza chaves de produção.

As verificações existentes de configuração privada e segredos no histórico continuam habilitadas.

**Configuração obrigatória no Railway:** os workflows sozinhos não bloqueiam o deploy automático existente. Em **cada serviço**, abra **Settings → Source → Wait for CI** e ative a opção, mantendo `main` como branch de deploy. Depois de publicar o workflow, aceite uma eventual atualização de permissões do Railway GitHub App caso a opção não apareça. É uma configuração do serviço, não uma propriedade do `railway.json`.

Com **Wait for CI ativado**, o Railway aguarda os workflows do commit; se um workflow falhar, aquele deploy é ignorado. Estes workflows não cancelam automaticamente execuções de push. Confira a integração no próximo push da `main`: o deploy deve aguardar o CI, prosseguir após sucesso e ser ignorado quando um workflow falhar. **Até ativar essa opção, o deploy automático não estará protegido por estes testes.** Consulte a [documentação de autodeploy do Railway](https://docs.railway.com/deployments/github-autodeploys).

## Mais sobre o projeto

O aplicativo complementar está no repositório **[fut_manager_app_mobile](https://github.com/pedro-vlps/fut_manager_app_mobile)** e utiliza Expo, React Native e TypeScript, com distribuição web/PWA e suporte a builds nativos.

- [Mudanças após os testes do campeonato](Feedback.md)
- [Documentação técnica anterior](docs/DEVELOPMENT.md)

Desenvolvido por **Pedro Vieira**, como projeto pessoal de portfólio.
