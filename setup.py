# -*- coding: utf-8 *-*
from setuptools import setup, find_packages

setup(name='timus.scoreboard',
    version='0.1',
    description='Custom contest support for the Timus Online Judge',
    long_description=open('README').read(),
    author=u'Adomas Paltanavičius',
    author_email='adomas@shrubberysoft.com',
    #url='http://github.com/admp/timus-scoreboard',
    packages=find_packages(),
    install_requires=['BeautifulSoup==3.0.7a', 'Jinja2', 'configobj'],
    entry_points={
        'console_scripts': [
            "timus-scoreboard = timus.scoreboard:main"
        ]
    }
    # classifiers=[
    #     'Development Status :: 4 - Beta',
    # ]   
)
