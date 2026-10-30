"""Use ReportLab's maintained pure-Python source instead of p4a's stale hg recipe.

ReportLab 4+ is pure Python for normal PDF generation. The bundled p4a
recipe points at an obsolete Mercurial changeset URL which now returns 403.
"""
from pythonforandroid.recipe import PythonRecipe


class ReportLabRecipe(PythonRecipe):
    version = "master"
    url = "https://github.com/MrBitBucket/reportlab-mirror/archive/refs/heads/master.zip"
    depends = ["python3", "setuptools", "pillow", "charset-normalizer"]
    site_packages_name = "reportlab"


recipe = ReportLabRecipe()
