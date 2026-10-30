"""Pinned ReportLab 5.1.0 source recipe for Android.

ReportLab 4+ is pure Python for normal PDF generation. This recipe avoids
python-for-android's obsolete Mercurial URL and verifies the PyPI sdist.
"""
from pythonforandroid.recipe import PythonRecipe


class ReportLabRecipe(PythonRecipe):
    version = "5.1.0"
    url = "https://files.pythonhosted.org/packages/89/22/c18474be40b9bbb52fdb7051177d4d25f1ea59fada17eb181026411e93b1/reportlab-5.1.0.tar.gz"
    sha256sum = "6878200464527e87672d19e9f7cfc6bb890e3a6931e74ac6a1a8d1754aa55671"
    depends = ["pillow", "charset-normalizer"]
    hostpython_prerequisites = ["setuptools"]
    site_packages_name = "reportlab"


recipe = ReportLabRecipe()
