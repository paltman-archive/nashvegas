import os
from setuptools import setup, find_packages


VERSION = __import__("nashvegas").__version__

def read(*path):
    return open(os.path.join(os.path.abspath(os.path.dirname(__file__)), *path)).read()


setup(
    name="nashvegas",
    version=VERSION,
    description="nashvegas is a management command for managing Django database migrations",
    long_description=read("README.rst"),
    author="Patrick Altman",
    author_email="paltman@gmail.com",
    maintainer="Patrick Altman",
    maintainer_email="paltman@gmail.com",
    url="http://github.com/paltman/nashvegas/",
    packages=find_packages(),
    zip_safe=False,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Framework :: Django",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.5",
    ],
)
