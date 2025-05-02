from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext as build_ext_orig



setup(
    name='feudal_sim',
    version='0.1',
    packages=['feudal_sim'],
    ext_modules=[Extension(
        'renderer',
        sources=['render/renderer.cpp'],
        language='c++',
    )],
    # cmdclass={'build_ext': build_ext},
)
