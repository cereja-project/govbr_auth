# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [0.1.4] - 2026-02-17

### Adicionado
- 🧪 **Modo Fake Gov.br**: Simulador completo do fluxo OAuth 2.0 para desenvolvimento
  - Detecção automática quando URLs locais são configuradas
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
- `GovBrConnector` agora detecta automaticamente URLs locais e ativa modo fake
- Atualizada documentação principal (README.md) com seção sobre modo fake
- Atualizada documentação de boas práticas com avisos de segurança do modo fake
- Exportações do módulo principal incluem classes e funções do fake_govbr

### Segurança
- ⚠️ Modo fake possui validações simplificadas (apenas para desenvolvimento)
- ⚠️ JWT secret do fake é conhecido (não usar em produção)
- ⚠️ Senhas fake são iguais ao CPF (apenas para testes)

---

## [0.1.3] - 2025-XX-XX

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

## [0.1.0] - 2025-XX-XX

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
- [Documentação](https://github.com/cereja-project/govbr_auth#readme)
- [Issues](https://github.com/cereja-project/govbr_auth/issues)

