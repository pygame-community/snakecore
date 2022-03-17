from setuptools import setup
import re

requirements = []
with open('requirements.txt') as f:
  requirements = f.read().splitlines()

version = ''
with open('snakecore/__init__.py') as f:
    version = re.search(r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]', f.read(), re.MULTILINE).group(1)

if not version:
    raise RuntimeError('version is not set')

readme = ''
with open('README.md') as f:
    readme = f.read()

packages = [
    'snakecore',
]

setup(name='snakecore',
      author='PygameCommunityDiscord',
      url='https://github.com/PygameCommunityDiscord/snakecore',
      project_urls={
        "Issue tracker": "https://github.com/PygameCommunityDiscord/snakecore/issues",
      },
      version=version,
      packages=packages,
      license='MIT',
      description='A set of core APIs to facilitate the creation of feature-rich Discord bots.',
      long_description=readme,
      long_description_content_type="text/markdown",
      include_package_data=True,
      install_requires=requirements,
      python_requires='>=3.9.0',
      classifiers=[
        "Topic :: Software Development :: ",
        'License :: OSI Approved :: MIT License',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Topic :: Internet',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Utilities',
        'Typing :: Typed',
      ]
)
