# Desenvolvimento e contribuições · Fut Manager API

[Apresentação do projeto](https://github.com/pedro-vlps/fut_manager_app_api?tab=readme-ov-file) · [README em português](README.pt-BR.md)

Este guia descreve como preparar o ambiente, respeitar a arquitetura e validar alterações. O GitHub apresenta este arquivo na aba nativa **Contributing**, ao lado de **README**, na página principal do repositório.

## Preparar o ambiente

1. Instale Python 3.13+, Poetry e PostgreSQL, ou utilize Docker.
2. Execute `poetry install`.
3. Configure as variáveis de `.env.example` em um `.env` privado, incluindo as chaves de criptografia. A chave Fernet é gerada com `Fernet.generate_key()`; a chave de HMAC deve ser um segredo aleatório independente.
4. Para uma instalação nova, ative `FUT_MANAGER_CREATE_SCHEMA_ON_STARTUP=true`. Para bancos existentes, siga **a ordem de migração em [Feedback.md](Feedback.md)** antes de iniciar esta versão.
5. Execute:

```powershell
poetry run python -m uvicorn src.__main__:app --reload
```

A documentação interativa fica em `/docs` quando `FUT_MANAGER_DOCS_ENABLED=true`. Não configure credenciais ou chaves reais em arquivos versionados.

## Limites de responsabilidade

- Rotas em `src/routers` declaram contratos HTTP e delegam aos controllers.
- Controllers coordenam permissões e regras de negócio; consultas SQL ficam em `src/services`.
- Helpers concentram algoritmos de classificação, calendário e premiação.
- Alterações de schema precisam de migrations versionadas, compatíveis com instalações existentes.
- Mudanças em resultados, inscrições e punições devem preservar os bloqueios transacionais utilizados pelos services.
- Mantenha os testes de arquitetura e acrescente regressões para alterações de regras de negócio.

## Validar uma alteração

```powershell
poetry run python -m scripts.run_feedback_tests
python scripts/check_private_config.py
```

Disponibilize antes um PostgreSQL **descartável** na porta 55439, banco e usuário `postgres`, com a senha exclusiva de teste `isolated-test-only`, conforme o runner. O runner ignora o arquivo `.env`, configura as chaves efêmeras e cria o schema; ele não inicia o servidor PostgreSQL. Utilize somente a instância isolada para esta suite.

## Enviar uma contribuição

1. Descreva o problema e o comportamento esperado. Para correções, inclua os passos de reprodução.
2. Implemente a alteração seguindo os limites de responsabilidade descritos acima.
3. Atualize os testes relevantes quando o comportamento mudar e mantenha as versões inglesa e portuguesa da apresentação consistentes.
4. Execute as verificações locais e abra um pull request com a motivação, a mudança de comportamento e os resultados da validação.
5. Preserve credenciais, chaves, arquivos `.env` e dados reais fora dos commits e dos relatórios de teste.

## CI e publicação

O [workflow de validação](.github/workflows/tests.yml) executa em todo push e pull request. A [verificação de informações privadas](.github/workflows/private-config.yml) também continua ativa.

A produção usa deploy automático da branch `main` no Railway. Em cada serviço, **Settings → Source → Wait for CI** deve estar ativado para aguardar os workflows e impedir o deploy de commits cuja validação falhe. Criar o workflow, por si só, não ativa essa opção. Consulte a [documentação do Railway](https://docs.railway.com/deployments/github-autodeploys).
