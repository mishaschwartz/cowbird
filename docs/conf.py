#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# cowbird documentation build configuration file, created by
# sphinx-quickstart on Tue Jul  9 22:26:36 2013.
#
# This file is execfile()d with the current directory set to its
# containing dir.
#
# Note that not all possible configuration values are present in this
# autogenerated file.
#
# All configuration values have a default; values that are commented out
# serve to show the default.

# pylint: disable=C0103,invalid-name

import inspect
import json
import os
import re
import sys

# If extensions (or modules to document with autodoc) are in another
# directory, add these directories to sys.path here. If the directory is
# relative to the documentation root, use os.path.abspath to make it
# absolute, like shown here.
# sys.path.insert(0, os.path.abspath("."))

# Get the project root dir, which is the parent dir of this
DOC_DIR_ROOT = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(DOC_DIR_ROOT)

# Insert the project root dir as the first element in the PYTHONPATH.
# This lets us ensure that the source package is imported, and that its
# version is used.
sys.path.insert(0, PROJECT_ROOT)

# pylint: disable=C0413,wrong-import-position
from cowbird import __meta__  # isort:skip # noqa: E402
# for api generation
from cowbird.api.schemas import generate_api_schema  # isort:skip # noqa: E402
from pyramid.config import Configurator  # isort:skip # noqa: E402

# -- General configuration ---------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
# needs_sphinx = "1.0"

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named "sphinx.ext.*") or your custom
# ones.
sys.path.append(os.path.abspath(os.path.join(DOC_DIR_ROOT, "_ext")))
extensions = [
    "doc_redirect",
    "sphinxcontrib.redoc",
    "sphinx.ext.autodoc",
    "sphinx.ext.todo",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "autoapi.extension",
    "sphinx_autodoc_typehints",
    "sphinx_paramlinks",
    "sphinx_rtd_theme",
]


image_source_dir = "_static"


def autodoc_skip_member(app, what, name, obj, skip, options):  # noqa
    """
    Avoids an error where documentation is having trouble resolving inherited members (methods/properties) from Celery
    Task in 'cowbird.request_task.RequestTask'.
    """

    if skip:
        return skip

    from celery.app.task import Task

    from cowbird.request_task import RequestTask
    if obj is not RequestTask:
        return skip

    request_task_members = set(member[0] for member in inspect.getmembers(RequestTask))
    celery_task_members = set(member[0] for member in inspect.getmembers(Task))
    includes = request_task_members - celery_task_members
    exclude = name not in includes
    return skip or exclude


def doc_redirect_include(file_path):
    if any(re.match(regex, file_path) for regex in doc_redirect_ignores):
        return False
    return any(file_path.endswith(ext) for ext in doc_redirect_extensions)


# note: see custom extension documentation
doc_redirect_ignores = [
    re.compile(r"cowbird\..*"),  # autoapi generated files
    re.compile(r"index.*"),
]
doc_redirect_extensions = [
    ".rst",
]
# references to RST files in 'docs' dir redirect to corresponding HTML
doc_redirect_map = {
    "docs/{}".format(file_name): file_name
    for file_name in os.listdir(DOC_DIR_ROOT)
    if doc_redirect_include(file_name)
}
# references to RST files in repo root (README/CHANGES) redirect to their equivalent HTML in 'docs' dir
doc_redirect_map.update({
    file_name: "docs/{}".format(file_name.lower())
    for file_name in os.listdir(PROJECT_ROOT)
    if doc_redirect_include(file_name)
})

# generate openapi
config = Configurator(settings={"cowbird.build_docs": True, "cowbird.ui_enabled": False})
config.include("cowbird")  # actually need to include cowbird to apply decorators and parse routes
api_spec_file = os.path.join(DOC_DIR_ROOT, "api.json")
api_spec_json = generate_api_schema({"host": "example", "schemes": ["https"]})
with open(api_spec_file, "w") as f:
    json.dump(api_spec_json, f)

redoc = [{
    "name": __meta__.__title__,
    "page": "api",  # rendered under "{root}/api.html"
    "spec": api_spec_file,
    "embed": True,
    "opts": {
        "lazy-rendering": True,
        "hide-hostname": True,
        "path-in-middle-panel": True,
    }
}]

autoapi_dirs = [os.path.join(PROJECT_ROOT, __meta__.__package__)]
autoapi_ignore = [os.path.join(PROJECT_ROOT, "cowbird/alembic/*")]
autoapi_python_class_content = "both"

# cases to ignore during link checking
linkcheck_ignore = [
    # might not exist yet (we are generating it!)
    "https://pavics-cowbird.readthedocs.io/en/latest/api.html",
    # FIXME: tmp disable due to Retry-After header for rate-limiting by Github not respected
    #        (see: https://github.com/sphinx-doc/sphinx/issues/7388)
    "https://github.com/Ouranosinc/cowbird/*",    # limit only Cowbird so others are still checked
    # ignore private links
    "https://github.com/Ouranosinc/PAVICS/*",
    "CHANGES.rst",
    "AUTHORS.rst",
    r"docs/\w+.rst",
]
linkcheck_anchors_ignore = [
    r".*issuecomment.*"   # github issue comment anchors not resolved
]

linkcheck_timeout = 20
linkcheck_retries = 5

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

todo_include_todos = True

# The suffix of source filenames.
source_suffix = ".rst"

# The encoding of source files.
# source_encoding = "utf-8-sig"

# The master toctree document.
master_doc = "index"

# General information about the project.
project = __meta__.__title__
copyright = "2021, {}".format(__meta__.__author__)  # pylint: disable=W0622,redefined-builtin

# The version info for the project you're documenting, acts as replacement
# for |version| and |release|, also used in various other places throughout
# the built documents.
#
# The short X.Y version.
version = __meta__.__version__
# The full version, including alpha/beta/rc tags.
release = __meta__.__version__

# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
language = "en"

# There are two options for replacing |today|: either, you set today to
# some non-false value, then it is used:
# today = ""
# Else, today_fmt is used as the format for a strftime call.
# today_fmt = "%B %d, %Y"

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = []

# The reST default role (used for this markup: `text`) to use for all
# documents.
# default_role = None

# If true, '()' will be appended to :func: etc. cross-reference text.
# add_function_parentheses = True

# If true, the current module name will be prepended to all description
# unit titles (such as .. function::).
# add_module_names = True

# If true, sectionauthor and moduleauthor directives will be shown in the
# output. They are ignored by default.
# show_authors = False

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "sphinx"

# A list of ignored prefixes for module index sorting.
# modindex_common_prefix = []

# If true, keep warnings as "system message" paragraphs in the built
# documents.
# keep_warnings = False


# -- Options for HTML output -------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = "sphinx_rtd_theme"
# html_theme = "nature"

# Theme options are theme-specific and customize the look and feel of a
# theme further.  For a list of options available for each theme, see the
# documentation.
html_theme_options = {
    "navigation_depth": 3,   # TOC, RTD theme
    "body_max_width": 1200,  # really narrow default 850, we are in widescreen era
}

# Add any paths that contain custom themes here, relative to this directory.
# html_theme_path = []

# The name for this set of Sphinx documents.  If None, it defaults to
# "<project> v<release> documentation".
# html_title = None

# A shorter title for the navigation bar.  Default is the same as html_title.
# html_short_title = None

# The name of an image file (relative to this directory) to place at the top
# of the sidebar.
# html_logo = ""

# The name of an image file (within the static path) to use as favicon of the
# docs.  This file should be a Windows icon file (.ico) being 16x16 or 32x32
# pixels large.
# html_favicon = None

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = [image_source_dir]
html_css_files = ["custom.css"]

# Add any extra paths that contain custom files (such as robots.txt or
# .htaccess) here, relative to this directory. These files are copied
# directly to the root of the documentation.
# html_extra_path = []

# If not "", a "Last updated on:" timestamp is inserted at every page bottom,
# using the given strftime format.
html_last_updated_fmt = "%Y-%m-%d"

# If true, SmartyPants will be used to convert quotes and dashes to
# typographically correct entities.
# html_use_smartypants = True

# Custom sidebar templates, maps document names to template names.
html_sidebars = {
    # add full TOC of the doc
    "**": ["globaltoc.html", "relations.html", "sourcelink.html", "searchbox.html"]
}

# Additional templates that should be rendered to pages, maps page names to
# template names.
# html_additional_pages = {}

# If false, no module index is generated.
# html_domain_indices = True

# If false, no index is generated.
# html_use_index = True

# If true, the index is split into individual pages for each letter.
# html_split_index = False

# If true, links to the reST sources are added to the pages.
# html_show_sourcelink = True

# If true, "Created using Sphinx" is shown in the HTML footer. Default is True.
# html_show_sphinx = True

# If true, "(C) Copyright..." is shown in the HTML footer. Default is True.
# html_show_copyright = True

# If true, an OpenSearch description file will be output, and all pages will
# contain a <link> tag referring to it.  The value of this option must be the
# base URL from which the finished HTML is served.
# html_use_opensearch = ""

# This is the file name suffix for HTML files (e.g. ".xhtml").
# html_file_suffix = None

# Output file base name for HTML help builder.
htmlhelp_basename = "cowbirddoc"


# -- Options for LaTeX output ------------------------------------------

latex_elements = {
    # The paper size ("letterpaper" or "a4paper").
    # "papersize": "letterpaper",

    # The font size ("10pt", "11pt" or "12pt").
    # "pointsize": "10pt",

    # Additional stuff for the LaTeX preamble.
    # "preamble": "",
}

doc_title = "{} Documentation".format(__meta__.__title__)

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title,
#  author, documentclass [howto, manual, or own class]).
latex_documents = [
    (master_doc, "{}.tex".format(__meta__.__package__), doc_title, __meta__.__author__, "manual"),
]

# The name of an image file (relative to this directory) to place at
# the top of the title page.
# latex_logo = None

# For "manual" documents, if this is true, then toplevel headings
# are parts, not chapters.
# latex_use_parts = False

# If true, show page references after internal links.
# latex_show_pagerefs = False

# If true, show URL addresses after external links.
# latex_show_urls = False

# Documents to append as an appendix to all manuals.
# latex_appendices = []

# If false, no module index is generated.
# latex_domain_indices = True


# -- Options for manual page output ------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    (master_doc, __meta__.__package__, doc_title, [__meta__.__author__], 1)
]

# If true, show URL addresses after external links.
# man_show_urls = False


# -- Options for Texinfo output ----------------------------------------

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
    (master_doc, __meta__.__package__,
     doc_title,
     __meta__.__author__,
     __meta__.__package__,
     __meta__.__description__,
     "Miscellaneous"),
]

# Documents to append as an appendix to all manuals.
# texinfo_appendices = []

# If false, no module index is generated.
# texinfo_domain_indices = True

# How to display URL addresses: "footnote", "no", or "inline".
# texinfo_show_urls = "footnote"

# If true, do not generate a @detailmenu in the "Top" node"s menu.
# texinfo_no_detailmenu = False

intersphinx_mapping = {
}


def setup(app):
    app.connect("autodoc-skip-member", autodoc_skip_member)
