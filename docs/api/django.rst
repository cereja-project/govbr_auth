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
e ``runtime`` são mutuamente exclusivos. Em modo fake, o consumidor continua no
mesmo runtime consumidor; a configuração troca apenas os endpoints do provedor
e o transporte HTTP interno (``FakeGovHttpTransport``). Para composição
avançada, o simulador canônico é ``govbr_auth.fake.FakeGovSimulator``, criado por
``govbr_auth.fake.create_fake_gov_simulator``. As URLs do FakeGov são
adicionadas à lista no prefixo próprio do runtime.

.. py:class:: GovBrAuth(*, on_success, settings=None, runtime=None, on_error=None, expose_tokens=False, prefix="/auth/govbr", clock=utc_now, user_repository=None)
   :no-index:

   Compõe a engine e expõe ``urlpatterns`` para inclusão explícita no projeto.
