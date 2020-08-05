from setuptools import setup, find_packages

setup(
    name="hierarchical-coordination",
    version="1.0",
    packages=find_packages('src', 'tests'),
    description='Hierarchical network and service coordination',
    url='https://github.com/CN-UPB/hierarchical-coordination',
    author='Mirko Juergens',
    author_email='mirkoj@mail.upb.de',
    package_dir={'': 'src'},
    install_requires=[
        "networkx",
        "pydot",
        "geopy",
        "pyyaml",
        "numpy",
  #      "pytest",
        'gurobipy',
        "matplotlib",
        "sklearn",
        "psycopg2-binary"
    ],
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'hvc=hvc.main:main',
        ],
    },
)
