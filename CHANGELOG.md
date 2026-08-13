# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

## [1.0.0-rc1] - 2026-08-13

### Added
- Adicionada demonstração local instalável com ``pip install "govbr-auth[demo]"`` e executável por ``python -m govbr_auth.demo``.
- Adicionadas documentação de início rápido e publicação estática no GitHub Pages, com validação HTML e de links no CI.
- Adicionado handler de erro opcional ``on_error`` para consumidores que escolherem tratar falhas de autenticação no adaptador FastAPI.

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

