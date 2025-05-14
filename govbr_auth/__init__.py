from cereja.utils import get_version_pep440_compliant

try:
    from .core.config import GovBrConfig
    from .core.govbr import GovBrAuthorize, GovBrIntegration
    from .controller import GovBrConnector
    from .utils import generate_cript_verifier_secret
except ImportError:
    pass  # noqa: E402

VERSION = "0.1.3.final.0"
__version__ = get_version_pep440_compliant(VERSION)
