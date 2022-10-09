#!/usr/bin/env python

from distutils.core import setup, Extension

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
    license='MIT'
)
