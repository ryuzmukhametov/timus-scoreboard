# -*- coding: utf-8 *-*
from setuptools import setup, find_packages

setup(name='timus.scoreboard',
    version='0.1',
    description='Custom contest support for the Timus contest system',
    long_description=open('README').read(),
    author=u'Adomas Paltanavičius',
    author_email='adomas@shrubberysoft.com',
    #url='http://github.com/shrubberysoft/homophony',
    packages=find_packages(),
    install_requires=['BeautifulSoup==3.0.7a', 'Jinja2'],
    # classifiers=[
    #     'Development Status :: 4 - Beta',
    # ]   
)
