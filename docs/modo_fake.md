# 🧪 Modo Fake Gov.br - Documentação Completa

O modo fake é uma funcionalidade integrada que permite desenvolver e testar sua aplicação sem necessidade de cadastro no Gov.br ou conexão com os servidores reais.

## 📋 Índice

- [O que é o Modo Fake?](#o-que-é-o-modo-fake)
- [Como Funciona?](#como-funciona)
- [Quando Usar?](#quando-usar)
- [Configuração](#configuração)
- [Usuários de Teste](#usuários-de-teste)
- [Customização](#customização)
- [Arquitetura Interna](#arquitetura-interna)
- [Limitações](#limitações)

---

## O que é o Modo Fake?

O modo fake é um simulador completo do fluxo OAuth 2.0 com PKCE do Gov.br que roda localmente na sua aplicação. Ele inclui:

- ✅ Página de login estilizada
- ✅ Validação de credenciais (CPF + email)
- ✅ Geração de códigos de autorização
- ✅ Troca de code por tokens
- ✅ Geração de JWT (id_token) válido
- ✅ Sessões temporárias em memória

**Tudo isso sem precisar de conexão externa!**

---

## Como Funciona?

### Detecção Automática

O modo fake é ativado automaticamente quando o `GovBrConnector` detecta que as URLs de autenticação (`auth_url` e `token_url`) apontam para `localhost` ou `127.0.0.1`.

```python
# ✅ Isso ATIVA o modo fake
config = GovBrConfig(
    auth_url="http://localhost:8000/fake-govbr/authorize",
    token_url="http://localhost:8000/fake-govbr/token",
    # ...
)

# ❌ Isso NÃO ativa o modo fake (URLs reais)
config = GovBrConfig(
    auth_url="https://sso.staging.acesso.gov.br/authorize",
    token_url="https://sso.staging.acesso.gov.br/token",
    # ...
)
```

### Fluxo de Autenticação

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. GET /auth/govbr/authorize                                    │
│    → Retorna URL: http://localhost:8000/fake-govbr/authorize   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. GET /fake-govbr/authorize                                    │
│    → Exibe página de login HTML                                │
│    → Cria sessão temporária com state e code_challenge         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. POST /fake-govbr/login (email + CPF)                        │
│    → Valida credenciais contra usuários fake                   │
│    → Gera authorization_code                                   │
│    → Redireciona para redirect_uri com code + state           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. POST /auth/govbr/authenticate (code + state)                │
│    → POST /fake-govbr/token (internamente)                     │
│    → Valida code_verifier (PKCE)                               │
│    → Gera access_token e id_token (JWT)                        │
│    → Retorna dados do usuário                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quando Usar?

### ✅ Use o Modo Fake quando:

- Estiver desenvolvendo localmente
- Quiser testar o fluxo OAuth sem burocracia
- Precisar de usuários de teste predefinidos
- Não tiver acesso aos servidores do Gov.br
- Estiver criando testes automatizados
- Estiver desenvolvendo em ambiente CI/CD

### ❌ NÃO use o Modo Fake quando:

- Estiver em **produção**
- Precisar validar usuários reais
- Estiver em ambiente de homologação conectado ao Gov.br

---

## Configuração

### Configuração Básica (Automática)

```python
from govbr_auth import GovBrConfig, GovBrConnector, create_default_fake_users
from fastapi import FastAPI

# Configuração com URLs locais (ativa o fake automaticamente)
config = GovBrConfig(
    client_id="fake-client-id",
    client_secret="fake-client-secret",
    redirect_uri="http://localhost:8000/auth/govbr/callback",
    cript_verifier_secret="Vvd9H5VC2Aqk-dwFOJX6MvQTuZZARmb37y7un9wkj0c=",
    auth_url="http://localhost:8000/fake-govbr/authorize",
    token_url="http://localhost:8000/fake-govbr/token"
)

app = FastAPI()

# O connector detecta automaticamente e registra endpoints fake
connector = GovBrConnector(
    config=config,
    on_auth_success=handle_success,
    fake_users=create_default_fake_users()  # Opcional
)

connector.init_fastapi(app)
```

### Configuração com Variáveis de Ambiente

```bash
# .env
USE_FAKE_GOVBR=true
GOVBR_CLIENT_ID=fake-client-id
GOVBR_CLIENT_SECRET=fake-client-secret
GOVBR_REDIRECT_URI=http://localhost:8000/auth/govbr/callback
CRIPT_VERIFIER_SECRET=Vvd9H5VC2Aqk-dwFOJX6MvQTuZZARmb37y7un9wkj0c=
GOVBR_AUTH_URL=http://localhost:8000/fake-govbr/authorize
GOVBR_TOKEN_URL=http://localhost:8000/fake-govbr/token
```

```python
import os
from govbr_auth import GovBrConfig

# Carrega automaticamente do .env
config = GovBrConfig.from_env()
```

---

## Usuários de Teste

### Usuários Padrão

A função `create_default_fake_users()` cria 3 usuários de teste:

| CPF | Nome | E-mail | Senha | Picture |
|-----|------|--------|-------|---------|
| 12345678901 | João da Silva | joao.silva@example.com | 12345678901 | URL padrão Gov.br |
| 98765432100 | Maria Oliveira | maria.oliveira@example.com | 98765432100 | URL padrão Gov.br |
| 11122233344 | José Santos | jose.santos@example.com | 11122233344 | URL padrão Gov.br |

### Acessando Usuários via API

```bash
# Listar todos os usuários disponíveis
curl http://localhost:8000/fake-govbr/users
```

Resposta:
```json
{
  "usuarios_de_teste": [
    {
      "cpf": "12345678901",
      "nome": "João da Silva",
      "email": "joao.silva@example.com",
      "senha": "12345678901"
    },
    {
      "cpf": "98765432100",
      "nome": "Maria Oliveira",
      "email": "maria.oliveira@example.com",
      "senha": "98765432100"
    },
    {
      "cpf": "11122233344",
      "nome": "José Santos",
      "email": "jose.santos@example.com",
      "senha": "11122233344"
    }
  ]
}
```

---

## Customização

### Criando Usuários Personalizados

```python
from govbr_auth.fake_govbr import FakeUserData

# Criar usuários customizados
custom_users = {
    "00011122233": FakeUserData(
        cpf="00011122233",
        nome="Admin Teste",
        email="admin@empresa.com.br",
        picture="https://example.com/avatar.jpg"
    ),
    "44455566677": FakeUserData(
        cpf="44455566677",
        nome="Desenvolvedor Teste",
        email="dev@empresa.com.br"
    )
}

connector = GovBrConnector(
    config=config,
    fake_users=custom_users
)
```

### Mesclando com Usuários Padrão

```python
from govbr_auth import create_default_fake_users
from govbr_auth.fake_govbr import FakeUserData

# Começa com os usuários padrão
users = create_default_fake_users()

# Adiciona usuários customizados
users["99988877766"] = FakeUserData(
    cpf="99988877766",
    nome="Usuário Extra",
    email="extra@example.com"
)

connector = GovBrConnector(config=config, fake_users=users)
```

### Customizando JWT Secret

```python
connector = GovBrConnector(
    config=config,
    fake_users=users,
    fake_jwt_secret="minha-chave-secreta-personalizada"
)
```

> ⚠️ **Importante**: O `fake_jwt_secret` é usado apenas para assinar o `id_token` no modo fake. Em produção, o Gov.br usa suas próprias chaves.

---

## Arquitetura Interna

### Classes Principais

#### `FakeGovBrService`

Classe central que gerencia:
- Sessões OAuth temporárias
- Validação de usuários
- Geração de códigos de autorização
- Troca de tokens
- Limpeza de sessões expiradas

```python
class FakeGovBrService:
    def __init__(self, users, session_ttl=600, jwt_secret="...", client_id="..."):
        self.users = users
        self.session_ttl = session_ttl
        self.jwt_secret = jwt_secret
        self._sessions = {}
        self._authorization_codes = {}
```

#### `FakeUserData`

Schema Pydantic para dados de usuário:

```python
class FakeUserData(BaseModel):
    cpf: str
    nome: str
    email: str
    picture: str = "https://www.gov.br/++theme++padrao_govbr/img/govbr-logo-large.png"
```

### Funções Auxiliares

- `create_default_fake_users()` - Cria usuários padrão
- `render_fake_login_page()` - Renderiza HTML da página de login
- `process_fake_login()` - Processa autenticação
- `_is_fake_mode()` - Detecta se deve ativar modo fake

---

## Limitações

### O que o Modo Fake NÃO faz:

1. **Não valida CPF real**: Aceita qualquer CPF de 11 dígitos cadastrado
2. **Não persiste dados**: Tudo fica em memória (reiniciar = perder sessões)
3. **Não simula erros de rede**: Sempre responde instantaneamente
4. **Não valida scopes complexos**: Aceita qualquer scope solicitado
5. **Não implementa refresh_token**: Apenas access_token e id_token
6. **Não simula rate limiting**: Sem limites de requisições
7. **Não é seguro para produção**: Chaves hardcoded, validação simplificada

### Diferenças do Gov.br Real

| Aspecto | Modo Fake | Gov.br Real |
|---------|-----------|-------------|
| Cadastro prévio | ❌ Não necessário | ✅ Obrigatório |
| Validação de CPF | Apenas formato | CPF válido na Receita |
| Certificados SSL | Não validado | Obrigatório |
| Domínios whitelisted | Qualquer | Apenas cadastrados |
| MFA/2FA | Não implementado | Opcional |
| Dados biométricos | Não disponível | Disponível |

---

## Segurança

### ⚠️ Avisos Importantes

1. **NUNCA use o modo fake em produção**
2. A senha fake é sempre igual ao CPF (inseguro!)
3. O JWT secret fake é conhecido (não use para dados reais)
4. Não há limitação de tentativas de login
5. Sessões ficam em memória (podem ser perdidas)

### ✅ Boas Práticas

1. Use variável de ambiente para controlar o modo (ex: `USE_FAKE_GOVBR`)
2. Tenha configurações separadas para dev/staging/prod
3. Documente claramente quando o fake está ativo
4. Teste com o Gov.br real antes de ir para produção
5. Use o fake apenas para desenvolvimento inicial

---

## Exemplos Práticos

### Exemplo 1: FastAPI Completo

Veja [`examples/example_simple_app.py`](../examples/example_simple_app.py) para um exemplo funcional completo com:
- Detecção automática de modo
- Página inicial com instruções
- Health check endpoint
- Listagem de usuários fake

### Exemplo 2: Testes Automatizados

```python
import pytest
from fastapi.testclient import TestClient
from govbr_auth import GovBrConfig, GovBrConnector, create_default_fake_users

@pytest.fixture
def app():
    from fastapi import FastAPI
    
    config = GovBrConfig(
        client_id="test-id",
        client_secret="test-secret",
        redirect_uri="http://localhost:8000/callback",
        cript_verifier_secret="test-secret",
        auth_url="http://localhost:8000/fake-govbr/authorize",
        token_url="http://localhost:8000/fake-govbr/token"
    )
    
    app = FastAPI()
    connector = GovBrConnector(
        config=config,
        fake_users=create_default_fake_users()
    )
    connector.init_fastapi(app)
    
    return app

def test_fake_login(app):
    client = TestClient(app)
    
    # Listar usuários disponíveis
    response = client.get("/fake-govbr/users")
    assert response.status_code == 200
    assert len(response.json()["usuarios_de_teste"]) == 3
```

---

## FAQ

### Como sei se o modo fake está ativo?

Verifique os logs ao iniciar sua aplicação:
```
🧪 Modo FAKE Gov.br ativado - Endpoints fake serão registrados automaticamente
```

Ou acesse o endpoint `/fake-govbr/users` - se retornar 200, está ativo.

### Posso usar o fake em testes CI/CD?

Sim! É uma das melhores aplicações. Configure seu CI para usar URLs locais.

### O fake suporta logout?

Não atualmente. O logout deve ser implementado na sua aplicação (limpeza de sessão/JWT).

### Posso adicionar campos customizados ao id_token?

Sim, modifique a classe `FakeGovBrService` e adicione campos ao `id_token_payload` no método `exchange_code_for_token`.

### O fake funciona com todos os frameworks?

Sim! FastAPI, Flask e Django têm suporte completo e automático.

---

## Contribuindo

Sugestões para melhorar o modo fake são bem-vindas! Abra uma issue ou PR.

Possíveis melhorias futuras:
- [ ] Persistência opcional (SQLite)
- [ ] Simulação de erros comuns
- [ ] Interface de administração web
- [ ] Suporte a refresh_token
- [ ] Simulação de MFA/2FA
- [ ] Métricas e logs detalhados

---

## Referências

- [OAuth 2.0 RFC 6749](https://datatracker.ietf.org/doc/html/rfc6749)
- [PKCE RFC 7636](https://datatracker.ietf.org/doc/html/rfc7636)
- [Gov.br - Roteiro Técnico](https://acesso.gov.br/roteiro-tecnico/)
- [JWT RFC 7519](https://datatracker.ietf.org/doc/html/rfc7519)

