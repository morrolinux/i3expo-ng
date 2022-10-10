#!/usr/bin/env python
from setuptools import setup, Extension, find_packages

prtscn = Extension(
    'prtscn',
    sources=['prtscn.c'],
    libraries=['X11'],
    language='c',
)

setup(
    name='i3expod',
    version='0.0.0',
    description='Exposè for i3 WM',
    scripts=['i3expod.py'],
    ext_modules=[prtscn],
    license='MIT',
    packages=find_packages(),
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
