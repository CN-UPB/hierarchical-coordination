from setuptools import setup, find_packages

setup(
    name="Hierarchical-vnf-coordination",
    version="0.1dev",
    packages=find_packages('src', 'tests'),
    license='Apache 2.0',
    description='HVC enables hierarchical coordination to VNF placement, scaling and routing',
    # url='https://github.com/CN-UPB/B-JointSP',
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
