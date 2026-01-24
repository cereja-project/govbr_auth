from cereja.utils import get_version_pep440_compliant

try:
    from .core.config import GovBrConfig
    from .core.govbr import GovBrAuthorize, GovBrIntegration, GovBrException, GovBrAuthenticationError
    from .controller import GovBrConnector
    from .utils import generate_cript_verifier_secret
    from .fake_govbr import (
        FakeUserData,
        FakeGovBrService,
        AuthorizationRequest,
        render_fake_login_page,
        process_fake_login,
        create_default_fake_users
    )
except ImportError:
    pass  # noqa: E402

VERSION = "0.1.4.final.0"
__version__ = get_version_pep440_compliant(VERSION)
