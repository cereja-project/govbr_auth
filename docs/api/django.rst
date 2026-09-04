Adaptador Django
================

Instalação::

   pip install "govbr-auth[django]"

Uso no ``urls.py``:

.. code-block:: python

   from govbr_auth.django import GovBrAuth

   auth = GovBrAuth(on_success=authenticated)
   urlpatterns = auth.urlpatterns

O adapter é síncrono e entrega ``(context, request)`` ao callback. Aceita
``GovBrRuntimeSettings`` ou ``GovBrRuntime``; quando omitidos, carrega as
configurações do ambiente. Registre ``auth.urlpatterns`` na raiz do URLconf.
As rotas do FakeGov e a página demo na raiz ``/`` só aparecem quando
``GOVBR_PROVIDER=fake``. O launcher FakeGov é apenas um atalho para essa
composição.

.. py:class:: GovBrAuth(*, on_success, settings=None, runtime=None, on_error=None, expose_tokens=False, prefix="/auth/govbr", clock=utc_now, user_repository=None)
   :no-index:

   Compõe o runtime e expõe ``urlpatterns`` para inclusão explícita.
