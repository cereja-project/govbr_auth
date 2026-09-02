Adaptador Flask
===============

Instalação::

   pip install "govbr-auth[flask]"

Uso:

.. code-block:: python

   from govbr_auth.flask import GovBrAuth

   auth = GovBrAuth(on_success=authenticated)
   auth.register(app)

``register(app)`` registra o blueprint do consumidor e, em modo fake, o
blueprint do FakeGov separadamente. O callback recebe o contexto autenticado e
o proxy ``request`` nativo do Flask durante o contexto da requisição.
``settings`` recebe ``GovBrApplicationSettings``; quando ``settings`` e
``runtime`` são omitidos, a fachada usa
``GovBrApplicationSettings.from_environment()``. O
consumidor continua no mesmo runtime consumidor; a configuração fake troca
apenas os endpoints do provedor e o transporte HTTP interno
(``FakeGovHttpTransport``). Para composição avançada, o simulador canônico é
``govbr_auth.fake.FakeGovSimulator``, criado por
``govbr_auth.fake.create_fake_gov_simulator``. No provedor oficial, o callback
é registrado no caminho de ``GOVBR_REDIRECT_URI``; ``prefix`` continua
definindo a rota de login. Registre a fachada sem ``url_prefix`` externo, pois
um prefixo adicional também alteraria o caminho do callback.

``GOVBR_DEMO_PAGE=true`` registra ``/govbr-auth-demo``; com
``demo_page=false``, a rota não é injetada. O provedor oficial usa a mesma
página sem simulação. Com runtime explícito, use
``GovBrAuth(runtime=runtime, demo_page=True, on_success=authenticated)``. A
rota é fixa e evitar colisão é responsabilidade do integrador.

.. py:class:: GovBrAuth(*, on_success, settings=None, runtime=None, demo_page=False, on_error=None, expose_tokens=False, prefix="/auth/govbr", clock=utc_now, user_repository=None)
   :no-index:

   Compõe a engine e expõe ``blueprint`` para registro manual ou ``register``
   para registrar também as rotas condicionais do FakeGov.
