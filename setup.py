#!/usr/bin/env python

from distutils.core import setup
from babel.messages import frontend as babel

setup(name='scum_bot',
      version='1.0',
      description='Discord Bot for Scum Servers',
      author='Thorsten Liepert',
      author_email='thorsten@liepert.dev',
      url='https://localhost',
      packages=['main'],
      cmdclass = {'compile_catalog': babel.compile_catalog,
                'extract_messages': babel.extract_messages,
                'init_catalog': babel.init_catalog,
                'update_catalog': babel.update_catalog}
    )
