# Configuration file for the Sphinx documentation builder.

import os
import sys
from datetime import datetime

# Add parent directory to path to import govbr_auth
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Project information
project = 'GovBR Auth'
author = 'Joab Leite'
copyright = f'{datetime.now().year}, {author}'
version = '1.0'  # short version
release = '1.0.0'  # full version

# General configuration
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.intersphinx',
    'myst_parser',
]

# Markdown support
source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}

# MyST parser configuration
myst_enable_extensions = [
    "colon_fence",
    "deflist",
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# Python autodoc options
autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'show-inheritance': True,
}

# HTML output options
html_theme = 'sphinx_rtd_theme'
html_theme_options = {
    'analytics_id': '',
    'canonical_url': 'https://govbr-auth.readthedocs.io/',
    'logo_only': False,
    'display_version': True,
    'prev_next_buttons_location': 'bottom',
    'style_external_links': False,
    'vcs_pageview_mode': '',
    'style_nav_header_background': '#2c3e50',
    'collapse_navigation': True,
    'sticky_navigation': True,
    'navigation_depth': 4,
    'includehidden': True,
    'titles_only': False
}

html_logo = None
html_favicon = None

# Intersphinx mapping
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}

# Highlighting options
pygments_style = 'sphinx'

# HTML output directory
html_static_path = ['_static']

# Napoleon extension settings (for Google style docstrings)
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = False
napoleon_use_param_annotations = False
napoleon_use_rtype_annotations = True

# Add any paths that contain custom static files here
if os.path.exists('_static'):
    html_static_path.append('_static')

