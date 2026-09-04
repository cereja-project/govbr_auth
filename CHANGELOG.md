# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Added
- Configuração opcional de logout com `GOVBR_LOGOUT_URL` e
  `GOVBR_POST_LOGOUT_REDIRECT_URI`, com rotas nativas para FastAPI, Django e
  Flask.
- Validação do `code_verifier` conforme RFC 7636 no core e no FakeGov.

### Changed
- O callback agora trata erros OAuth, valida o `state` e retorna mensagens
  públicas sem reproduzir `error_description` do provedor.
- A documentação e a demonstração usam o rótulo oficial `Entrar com GOV.BR`.

### Fixed
- O endpoint de logout do FakeGov agora valida destinos registrados e conclui
  o fluxo local sem criar redirecionamento aberto.

### Security
- O destino pós-logout é derivado da configuração e não pode ser escolhido por
  query string na rota do consumidor.
- Respostas de callback inválidas mantêm `Cache-Control: no-store` e não
  expõem parâmetros OAuth recebidos.

### Histórico de compatibilidade
- A configuração incompatível e ainda não publicada
  `GOVBR_FAKE_END_TO_END`/`fake_end_to_end` foi removida em favor do opt-in
  agregado `GOVBR_DEMO_PAGE`.

## [1.0.0] - 2026-09-01

### Changed
- A identidade visual agora inclui símbolos responsivos para fundos claros,
  escuros, reprodução monocromática e favicon, com regras documentadas de
  redução, área de proteção e posicionamento de projeto independente e open source.
- A documentação, os diagramas e a interface local da demo e do FakeGov agora
  usam a identidade govbr-auth em grafite, verde e vermelho, com Inter e
  JetBrains Mono locais, sem CDN e preservando a identificação explícita de
  simulação.
- O `.env.example` agora documenta todas as configurações oficiais e FakeGov;
  os exemplos executáveis delegam a leitura completa ao carregador validado em
  vez de reconstruir apenas provider, host e porta.

### Fixed
- O launcher `python -m govbr_auth.fake` agora carrega o `.env` do
  diretório atual sem sobrescrever variáveis exportadas pelo terminal e valida
  todas as configurações FakeGov antes de iniciar o servidor.
- Variáveis `GOVBR_*` desconhecidas agora falham explicitamente; variáveis
  reconhecidas mas inativas para o provider selecionado emitem warning sem
  revelar seus valores.

## [1.0.0rc1] - 2026-08-26

### Added
- Core OAuth 2.0/OpenID Connect assíncrono e independente de framework.
- Adapters públicos para FastAPI, Django e Flask, instaláveis por extras.
- FakeGov local opt-in com login por credenciais fictícias, launcher end-to-end e carregamento opcional de usuários via `GOVBR_FAKE_USERS_FILE`.
- Transações OAuth stateless protegidas por Fernet, compatíveis com múltiplos workers sem armazenamento compartilhado.
- Contratos públicos `FakeCredentialAuthenticator`, `InMemoryFakeUserRepository` e `JsonFakeUserRepository`.
- Documentação Sphinx, diagramas vetoriais e exemplos executáveis para os três frameworks.

### Changed
- A seleção de provedor agora ocorre por `GOVBR_PROVIDER=official|fake`; o código consumidor e as rotas do adapter permanecem iguais.
- A API pública foi reduzida a módulos explícitos de core, adapter e FakeGov.
- A matriz de CI cobre Python 3.11 a 3.14 em Linux, Windows e macOS.

### Removed
- Fachadas, módulos, exemplos e testes da implementação anterior à v1.
- Formulário de compatibilidade que autenticava no FakeGov pela seleção direta de `subject`; fluxos interativos agora exigem CPF e senha fictícios.

### Security
- Validação de `state`, PKCE, nonce, assinatura RS256/JWKS, issuer, audience e subject.
- TTL autenticado para a transação; replay é rejeitado pelo authorization code de uso único do provedor, não por consumo local do `state`.
- Tokens e segredos permanecem fora das respostas e páginas demonstrativas.
- O launcher local aceita somente hosts de loopback e o provedor oficial é o padrão fail-closed.

## [0.2.2] - 2026-06-19

### Added
- Adicionada integração com Django e um exemplo executável para o framework.

### Changed
- Atualizadas as dependências da cadeia de documentação Sphinx.

### Fixed
- Corrigidos callbacks do Django e rotas do modo fake para respeitar as URLs configuradas de redirecionamento e endpoints.
- Adicionadas validações dos parâmetros obrigatórios das views do Django e troca síncrona de tokens no callback.

## [0.2.1] - 2026-04-14

### Added
- Adicionada documentação com Sphinx e Read the Docs para API, configuração, frameworks, segurança, FAQ e solução de problemas.
- Adicionada cobertura para configuração, tratamento de erros e verificação de JWT.

### Changed
- Falhas de autenticação agora lançam exceções em vez de retornar dicionários de erro.

### Fixed
- Corrigidas a validação de configurações opcionais e o tratamento de erros no controller.

### Security
- Adicionada verificação da assinatura JWT pelo endpoint JWKS do Gov.br.

## [0.2.0] - 2026-02-17

### Adicionado
- 🧪 **Modo Fake Gov.br**: Simulador completo do fluxo OAuth 2.0 para desenvolvimento
  - Ativação explícita via flag `use_fake` ou env `USE_FAKE_GOVBR`
  - Endpoints fake criados automaticamente (`/fake-govbr/authorize`, `/fake-govbr/login`, `/fake-govbr/token`, `/fake-govbr/users`)
  - Página de login HTML estilizada
  - Usuários de teste pré-configurados
  - Geração de JWT (id_token) válido
  - Suporte completo a PKCE
  - Integração automática com FastAPI, Flask e Django
- Função `create_default_fake_users()` para usuários de teste padrão
- Classe `FakeUserData` para definir usuários customizados
- Classe `FakeGovBrService` para gerenciar o serviço fake
- Parâmetro `fake_users` no `GovBrConnector`
- Parâmetro `fake_jwt_secret` no `GovBrConnector`
- Exemplo completo em `examples/example_simple_app.py`
- Documentação detalhada do modo fake em `docs/modo_fake.md`

### Alterado
- `GovBrConnector` agora exige flag/env para ativar modo fake e registra endpoints quando habilitado
- Atualizada documentação principal (README.md) com seção sobre modo fake (opt-in)
- Atualizada documentação de boas práticas com avisos de segurança do modo fake
- Exportações do módulo principal incluem classes e funções do fake_govbr

### Segurança
- ⚠️ Modo fake possui validações simplificadas (apenas para desenvolvimento)
- ⚠️ JWT secret do fake é conhecido (não usar em produção)
- ⚠️ Senhas fake são iguais ao CPF (apenas para testes)

---

## [0.1.3] - 2025-05-14

### Adicionado
- Suporte inicial para FastAPI, Flask e Django
- Implementação de OAuth 2.0 com PKCE
- Geração de `code_verifier` e `code_challenge`
- Criptografia de `state` para segurança
- Funções assíncronas e síncronas
- Configuração via `.env` ou código
- Função `generate_cript_verifier_secret()`
- Callback `on_auth_success` customizável

### Documentação
- README com exemplos de uso
- Documentação de boas práticas
- Diagrama de fluxo de autenticação

---

## [0.1.0] - 2025-04-12

### Adicionado
- Versão inicial do projeto
- Estrutura básica do módulo
- Configuração com Pydantic
- Integração básica com Gov.br

---

## Tipos de Mudanças

- `Adicionado` para novas funcionalidades
- `Alterado` para mudanças em funcionalidades existentes
- `Depreciado` para funcionalidades que serão removidas
- `Removido` para funcionalidades removidas
- `Corrigido` para correção de bugs
- `Segurança` para vulnerabilidades corrigidas ou avisos

---

## Links

- [Repositório GitHub](https://github.com/cereja-project/govbr_auth)
- [Documentação](https://govbr-auth.readthedocs.io/)
- [Issues](https://github.com/cereja-project/govbr_auth/issues)

