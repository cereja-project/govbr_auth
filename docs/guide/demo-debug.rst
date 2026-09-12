Modo debug da demo
==================

O explorador explica a comunicação de uma autenticação **local com FakeGov**.
Ele está disponível na demo de FastAPI, Django e Flask e no launcher
``python -m govbr_auth.fake``. Não é o modo DEBUG do framework e não habilita
stack traces, captura de credenciais reais ou diagnóstico do provedor oficial.

Como usar
---------

#. Inicie a aplicação com ``GOVBR_PROVIDER=fake``. Os demais ajustes continuam
   sendo os do :doc:`fake-mode` ou dos exemplos do :doc:`quick-start`.
#. Abra a demo no mesmo host e porta configurados para o callback. No perfil
   padrão, use ``http://127.0.0.1:8000``; não alterne entre ``localhost`` e
   ``127.0.0.1`` durante o fluxo.
#. Selecione **Ativar modo debug**. O explorador fica em
   ``/govbr-auth-demo/debug``. A captura ainda não foi iniciada.
#. Selecione **Iniciar fluxo** e permita a janela de autenticação. Conclua o
   login usando somente os usuários fictícios configurados no FakeGov.
#. Acompanhe a reprodução, pause, avance uma etapa, altere a velocidade ou
   selecione uma etapa na timeline. Use **Replay** para rever a mesma captura.
#. Selecione **Exportar JSON** para salvar os eventos saneados ou **Limpar
   captura** para apagá-los do servidor. Desativar o modo debug também solicita
   a exclusão antes de retornar à demo normal.

A autenticação continua executando em sua velocidade normal. Somente a
**reprodução visual** é desacelerada: pausar não suspende requisições, não
altera a validade do state e não reexecuta a troca do código. Os tempos em
milissegundos são medidos na fronteira observada, não pelo tempo de animação.

O que a interface mostra
------------------------

A timeline separa preparação, autorização, login fictício no provedor,
recebimento do callback, vínculo com o navegador, troca do código, consulta
JWKS, validação do ID token, UserInfo e resposta final. Senha fictícia incorreta
aparece como uma tentativa recusada; uma nova tentativa na mesma janela pode
prosseguir sem apagar os eventos anteriores.

O mapa distingue navegador, backend da aplicação e FakeGov, com setas de
requisição e resposta. O painel técnico oferece resumo, HTTP, artefatos,
contratos de segurança e eventos. As abas funcionam com teclado; a interface
respeita ``prefers-reduced-motion`` e inicia em reprodução manual quando essa
preferência está ativa.

**Observado** identifica requisições/respostas capturadas nos adapters e no
cliente HTTPX. No FakeGov integrado, o backchannel utiliza transporte HTTPX
em memória: são mensagens HTTP do fluxo local, não chamadas de rede ao gov.br.

**Inferido** identifica uma conclusão limitada pela progressão do fluxo. O
início da troca do código indica que o callback passou pelo vínculo de
navegador e pela leitura do state. O início de UserInfo indica que o ID token
passou pela validação do núcleo. Não existem tempos individuais de assinatura,
nonce, issuer ou audience no trace. O painel não os fabrica nem apresenta a
lista didática como uma auditoria independente.

A resposta final é a resposta HTTP do callback da aplicação. Um status HTTP
bem-sucedido não comprova, isoladamente, criação de sessão ou autorização para
um recurso. A biblioteca entrega a identidade validada quando o fluxo é aceito;
a aplicação consumidora continua definindo sua sessão e seu tratamento de erros.

Privacidade e isolamento
------------------------

A projeção segura acontece **antes de armazenar os eventos**. O observador usa
uma lista restrita de campos e constantes de protocolo; não guarda os corpos
brutos para depois mascará-los. Segredos, tokens, state, nonce, códigos,
verificadores, cookies e dados pessoais são ocultados integralmente, sem
prefixos ou sufixos. O formulário de credenciais do navegador não é capturado.
Claims não são decodificadas pelo observador.

O painel HTTP mostra métodos, caminhos conhecidos, status, campos saneados e
atributos seguros dos cookies. Nomes dinâmicos e valores dos cookies também
são omitidos. A exportação contém exatamente a projeção segura exibida, não
uma segunda versão com detalhes sensíveis. Conteúdo dinâmico é renderizado
como texto; não há CDN, analytics, localStorage ou sessionStorage.

A leitura usa um identificador aleatório em cookie HttpOnly e host-only; esse
identificador não entra no JSON. As mutações exigem a origem configurada e um
header próprio da demo. Outro navegador sem o cookie não consegue ler o trace.
Os endpoints não habilitam CORS e todas as respostas do painel usam no-store.
Com ``GOVBR_PROVIDER=official``, as rotas e os hooks de debug não são instalados.

Limites operacionais
--------------------

Há uma captura ativa por navegador e configuração de cliente/callback.
Iniciar outra substitui a anterior; conclua um fluxo por vez para uma leitura
sem intercalação. Cookies de autenticação e da sessão não são removidos pelo
controle de limpeza do trace.

O armazenamento é local ao processo e limitado a 64 capturas, com até 128
eventos por captura. O acesso expira em 10 minutos; entradas expiradas são
removidas na próxima operação do armazenamento. Reiniciar o processo apaga
todas as capturas. Use **um worker** para esta demonstração: não foi introduzido
armazenamento distribuído apenas para o painel didático.

Fechar a janela, expirar a captura, atingir o limite ou perder o servidor
produz um estado explícito, sem inventar etapas concluídas. Uma captura
truncada deve ser limpa antes de outra execução.

O modo normal não carrega os recursos JavaScript/CSS do explorador nem cria
traces implicitamente. Não foram adicionadas pausas ou telemetria ao núcleo de
autenticação. Cobertura de testes e o painel não substituem revisão de segurança
ou homologação com o provedor oficial.

Verificação da interface
------------------------

Os testes de integração em ``tests/integration/test_demo_debug.py`` exercitam
as requisições reais nos clientes nativos dos três frameworks. A regressão
visual e de controles pode ser executada separadamente, em ambiente de
desenvolvimento com Playwright e Chromium instalados::

    python scripts/check_demo_debug_ui.py --output /tmp/govbr-demo-ui

Use ``--python`` para indicar outro interpretador com os extras de teste da
biblioteca e ``--browser`` para informar o executável Chromium já instalado.
O diretório de saída deve ficar fora do checkout.

Esse script obtém um trace saneado por integração HTTP nativa e renderiza o
HTML real offline. Ele substitui fetch e popup somente no teste visual e
verifica teclado, reprodução, exportação, falhas e layout móvel. Não equivale
a uma autenticação ponta a ponta do navegador contra um servidor e não tenta
contornar políticas que bloqueiem navegação HTTP no ambiente de teste.
