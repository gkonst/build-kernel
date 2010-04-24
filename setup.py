# -*- coding: utf-8 -*-
"""
Module used for installing/uninstalling application.
"""
from setuptools import setup

setup(
    name = "build_kernel", 
    version = "0.1",
    author =  "Konstantin Grigoriev",
    author_email = "Konstantin.V.Grigoriev@gmail.com",
    url = "http://github.com/KonstantinGrigoriev/build-kernel",
    license = "GPLv3",
    py_modules = ["build_kernel",],
    entry_points = """
        [console_scripts]
            build_kernel = build_kernel:main
    """
)
