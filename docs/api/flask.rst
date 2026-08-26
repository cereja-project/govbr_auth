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
o proxy ``request`` nativo do Flask durante o contexto da requisição. O
consumidor continua no mesmo runtime consumidor; a configuração fake troca
apenas os endpoints do provedor e o transporte HTTP interno. Para composição
avançada, o simulador canônico é ``govbr_auth.fake.FakeGovSimulator``, criado
por ``govbr_auth.fake.create_fake_gov_simulator``.

.. py:class:: GovBrAuth(*, on_success, settings=None, runtime=None, on_error=None, expose_tokens=False, prefix="/auth/govbr", clock=utc_now, user_repository=None)
   :no-index:

   Compõe a engine e expõe ``blueprint`` para registro manual ou ``register``
   para registrar também as rotas condicionais do FakeGov.
