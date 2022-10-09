#!/usr/bin/env python
from distutils.core import setup, Extension

import setuptools

prtscn = Extension(
    'prtscn',
    sources=['prtscn.c'],
    libraries=['X11'],
    language="c",
)

setup(
    name='i3expod',
    version='0.0.0',
    description='',
    scripts=['i3expod.py'],
    ext_modules=[prtscn],
    license='MIT',
    packages=setuptools.find_packages(),
    install_requires=[
        'pygame',
        'i3ipc',
        'pillow',
        'xdg',
        'pyxdg',
    ],
    entry_points={
        'console_scripts': [
            'i3expod=i3expod:main'
        ]
    }
)
