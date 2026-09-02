Adaptador Django
================

Instalação::

   pip install "govbr-auth[django]"

Uso no ``urls.py`` do projeto:

.. code-block:: python

   from govbr_auth.django import GovBrAuth

   auth = GovBrAuth(on_success=authenticated)
   urlpatterns = auth.urlpatterns

O adapter é síncrono e entrega ``(context, request)`` ao callback. ``settings``
recebe ``GovBrApplicationSettings``; quando nenhuma composição é fornecida, o
adapter usa ``GovBrApplicationSettings.from_environment()``. ``settings`` e
``runtime`` são mutuamente exclusivos. Em modo fake, o consumidor continua no
mesmo runtime consumidor; a configuração troca apenas os endpoints do provedor
e o transporte HTTP interno (``FakeGovHttpTransport``). Para composição
avançada, o simulador canônico é ``govbr_auth.fake.FakeGovSimulator``, criado por
``govbr_auth.fake.create_fake_gov_simulator``. As URLs do FakeGov são
adicionadas à lista no prefixo próprio do runtime. No provedor oficial, o
callback é registrado no caminho de ``GOVBR_REDIRECT_URI``; ``prefix``
continua definindo a rota de login. Inclua ``auth.urlpatterns`` na raiz do
URLconf, pois um prefixo externo também alteraria o caminho do callback.

``GOVBR_DEMO_PAGE=true`` registra ``/govbr-auth-demo``; com
``demo_page=false``, a rota não é injetada. O provedor oficial usa a mesma
página sem simulação. Com runtime explícito, passe
``GovBrAuth(runtime=runtime, demo_page=True, on_success=authenticated)``. A
rota é fixa e evitar colisão é responsabilidade do integrador.

.. py:class:: GovBrAuth(*, on_success, settings=None, runtime=None, demo_page=False, on_error=None, expose_tokens=False, prefix="/auth/govbr", clock=utc_now, user_repository=None)
   :no-index:

   Compõe a engine e expõe ``urlpatterns`` para inclusão explícita no projeto.
