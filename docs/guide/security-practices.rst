🔒 Segurança e Boas Práticas
=============================

Este documento detalha as decisões de segurança e arquitetura do GovBR Auth.

Fluxo de Autenticação Backend + Frontend
-----------------------------------------

O fluxo implementado segue OAuth 2.0 com PKCE (Proof Key for Code Exchange):

**Backend responsável por:**

- Gerar `code_verifier` e `code_challenge` (PKCE)
- Criar a URL de autorização
- Decodificar o `state` e realizar a troca de `code` por `token`
- Manter tokens fora do navegador

**Frontend responsável por:**

- Redirecionar o usuário para Gov.br
- Capturar o retorno (`code` e `state`)
- Enviar essas informações ao backend

Proteção de State (CSRF)
------------------------

O parâmetro `state` é **criptografado** usando Fernet (simétrico):

1. **Geração**: Backend gera um `code_verifier` aleatório de 80 bytes
2. **Criptografia**: Encripta com `cript_verifier_secret` (Fernet key)
3. **URL**: State criptografado é incluído na URL OAuth
4. **Recuperação**: Ao receber o callback, o backend descriptografa para recuperar o verifier
5. **Segurança**: Impede falsificação de state e ataques de replay

**Validação**: Se o state for inválido ou corrompido, você recebe::

    ValueError: Invalid or missing code_verifier

Proteção do Code Verifier (PKCE)
--------------------------------

O `code_verifier` é um valor aleatório de 80 bytes que **nunca é exposto ao navegador**:

1. **Gerado**: No backend durante `build_authorize_url()`
2. **Armazenado**: Criptografado no parâmetro `state`
3. **Nunca no frontend**: Não viaja em URLs ou cookies
4. **Proof**: Incluído no POST para troca de token (Gov.br valida)

Isso garante que mesmo se alguém interceptar o `code`, não consegue trocar sem o `verifier`.

Verificação JWT (ID Token)
---------------------------

O `id_token` retornado pelo Gov.br é verificado usando uma hierarquia:

1. **JWKS (Recomendado em produção)**
   - Gov.br publica chaves públicas em JWKS endpoint
   - Usamos RSA público para validar assinatura
   - Valida audiência (`aud`) e expiração (`exp`)

2. **jwt_secret (Local/Staging)**
   - Se JWKS não disponível, usa HS256 com secret configurado
   - Útil em desenvolvimento ou com Gov.br local

3. **Unverified (Apenas desenvolvimento)**
   - Se nenhuma estratégia funcionar, decodifica sem verificar
   - ⚠️ **Perigoso**: Registra WARNING no log
   - Nunca use em produção

**Precedência**::

    Se JWKS disponível:
        ✅ Usa RSA público
    Senão se jwt_secret configurado:
        ⚠️ Usa HS256
    Senão:
        ❌ Unverified (log WARNING)

Criptografia do Verifier Secret
-------------------------------

O `cript_verifier_secret` deve ser:

- **Gerado com segurança**: Use `generate_cript_verifier_secret()`
- **Mantido em segredo**: Nunca commitar no git
- **Consistente**: Idêntico em todos os deployments de um mesmo serviço
- **Armazenado seguro**: Use variáveis de ambiente, secrets managers (AWS Secrets, HashiCorp Vault)

**Se for trocado**:

Todos os estados criptografados anteriormente se tornarão inválidos::

    ValueError: Invalid or missing code_verifier

Tokens Nunca no Navegador
--------------------------

Por design, `id_token` e `access_token` **nunca são expostos ao navegador**:

- Backend recebe e decodifica
- Frontend recebe apenas dados desensibilizados (nome, email, CPF)
- Tokens não trafegam em URLs, cookies ou localStorage não-seguro

Modo Fake (Desenvolvimento Apenas)
----------------------------------

⚠️ **O modo fake é APENAS para desenvolvimento local!**

Segurança do modo fake:

- ❌ Senhas simplificadas (CPF = senha)
- ❌ Não valida CPF real
- ❌ JWT secret é conhecido
- ❌ Sem limitação de tentativas
- ❌ Sessões em memória (perdidas ao reiniciar)

**Nunca use em produção!**

Checklist de Segurança
----------------------

Antes de ir para produção, verifique:

- ☑️ `cript_verifier_secret` gerado com `generate_cript_verifier_secret()`
- ☑️ `cript_verifier_secret` armazenado em variáveis de ambiente
- ☑️ `client_secret` em variáveis de ambiente (nunca no código)
- ☑️ `jwt_secret` em variáveis de ambiente (se usado)
- ☑️ `USE_FAKE_GOVBR=false` em produção
- ☑️ HTTPS em todos os endpoints
- ☑️ `redirect_uri` registrado no Gov.br
- ☑️ CORS configurado corretamente
- ☑️ Rate limiting em endpoints OAuth
- ☑️ Logging de tentativas de autenticação

Referências Técnicas
---------------------

- `OAuth 2.0 for Browser-Based Apps <https://datatracker.ietf.org/doc/html/draft-ietf-oauth-browser-based-apps>`_
- `RFC 7636: PKCE <https://tools.ietf.org/html/rfc7636>`_
- `OWASP OAuth 2.0 Best Practices <https://owasp.org/www-project-api-security/>`_
- `JWT.io <https://jwt.io/>`_

Relatar Vulnerabilidades
------------------------

Se encontrar uma vulnerabilidade de segurança, por favor **não abra uma issue pública**.

Entre em contato com o mantenedor:

- Email: leitejoab@gmail.com
- Assunto: `[SECURITY] GovBR Auth`

Responderemos em até 48 horas.

