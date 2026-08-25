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
e ``runtime`` são mutuamente exclusivos. Em modo fake, as URLs do FakeGov são
adicionadas à lista no prefixo próprio do runtime.

.. py:class:: GovBrAuth(*, on_success, settings=None, runtime=None, on_error=None, expose_tokens=False, prefix="/auth/govbr", clock=utc_now, user_repository=None)
   :no-index:

   Compõe a engine e expõe ``urlpatterns`` para inclusão explícita no projeto.
