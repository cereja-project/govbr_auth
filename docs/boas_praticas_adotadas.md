# 🔒 Boas práticas adotadas

Este projeto foi desenvolvido com foco em segurança e clareza para desenvolvedores que desejam integrar o Login Único Gov.br de maneira correta.

## 🎯 Abordagem adotada

### 🔁 Fluxo de autenticação Backend + Frontend
O fluxo de autenticação com o Gov.br utiliza o protocolo OAuth 2.0 com PKCE (Proof Key for Code Exchange) para garantir uma troca segura de tokens entre o cliente e o servidor. Abaixo está uma visão geral do processo:
#### Backend responsável por:
- Gerar `code_verifier` e `code_challenge` (PKCE)
- Criar a URL de autorização (`authorize_url`)
- Decodificar o `state` e realizar a troca de `code` por `token`

#### Frontend responsável por:
- Redirecionar o usuário para a URL do Gov.br
- Capturar o retorno (`code` e `state`) do redirect
- Enviar essas informações ao backend para completar o fluxo
```
        ┌────────────────┐
        │  Frontend App  │
        └────────┬───────┘
                 │
                 │ (1) Solicita URL de login (authorize_endpoint)
                 ▼
    ┌─────────────────────────────┐
    │ GovBrAuthorize (Backend)    │
    │ build_authorize_url()       │
    └────────────┬────────────────┘
                 │
                 │ retorna URL com state + challenge
                 ▼
           (2) Redireciona usuário
           para GOV.BR com PKCE
                 │
                 ▼
    ┌────────────────────────┐
    │   GOV.BR Autenticação  │
    └────────────┬───────────┘
                 │
                 │ redirect para
                 ▼
          REDIRECT_URI (frontend)
                 │
                 │ (3) Frontend envia `code` + `state` (authenticate_endpoint)
                 ▼
    ┌───────────────────────────────┐
    │  GovBrIntegration (Backend)   │
    │  exchange_code_for_token()    │
    └────────────┬──────────────────┘
                 │
                 │ troca por token + decodifica ID
                 ▼
         Dados do usuário autenticado
```
---

## 🧪 Modo Fake para Desenvolvimento

A biblioteca inclui um **modo fake automático** que facilita o desenvolvimento sem necessidade de cadastro no Gov.br:

### Vantagens
- ✅ **Zero configuração**: Detecta automaticamente URLs locais
- ✅ **Endpoints automáticos**: Cria rotas fake sem código adicional
- ✅ **Fluxo completo**: Simula OAuth 2.0 + PKCE corretamente
- ✅ **Testes facilitados**: Usuários pré-configurados
- ✅ **Interface visual**: Página de login estilizada

### Como funciona
O modo fake é ativado automaticamente quando você configura URLs locais:

```python
config = GovBrConfig(
    auth_url="http://localhost:8000/fake-govbr/authorize",  # localhost = fake mode
    token_url="http://localhost:8000/fake-govbr/token"
)
```

### Segurança do modo fake
⚠️ **IMPORTANTE**: O modo fake é apenas para desenvolvimento!

- Usa senhas simplificadas (CPF = senha)
- Não valida CPF real
- JWT secret é conhecido
- Sem limitação de tentativas
- Sessões em memória

**Nunca use o modo fake em produção!** Veja a [documentação completa do modo fake](modo_fake.md) para mais detalhes.

---

## ✅ Por que isso é considerado uma boa prática?

| Item                         | Justificativa                                                                 |
|------------------------------|------------------------------------------------------------------------------|
| `code_verifier` no backend   | Nunca deve ser exposto ao cliente. Protege o fluxo de troca de token.       |
| `state` criptografado       | Evita falsificação e ataques de replay.                                     |
| Tokens só no backend        | Impede exposição de `id_token` ou `access_token` no navegador.              |
| Fracionamento do fluxo      | Garante que o frontend só opere com dados públicos ou temporários.          |
| PKCE com `S256`             | Recomendação atual para proteção adicional mesmo em apps públicos.          |

---

## ⚠️ Dificuldades encontradas na integração com Gov.br

- A documentação oficial (https://acesso.gov.br/roteiro-tecnico/) foi um pouco confusa para mim.
- Muitos exemplos não fazem uso correto do `state` ou do PKCE.
- É necessário cadastrar previamente os domínios de homologação e produção e **apenas órgãos públicos** podem utilizar o Login Gov.br..

---

## 🧠 Referências utilizadas

- [OAuth 2.0 for Browser-Based Apps (IETF)](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-browser-based-apps)
- [OWASP OAuth 2.0 Best Practices](https://owasp.org/www-project-api-security/)

---

Se tiver dúvidas, sugestões ou quiser contribuir com melhorias, fique à vontade para abrir uma issue ou PR! 💙
