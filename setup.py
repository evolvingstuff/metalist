from setuptools import setup, find_packages

setup(
    name="notes-app",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'fastapi>=0.110.0',
        'uvicorn>=0.27.1',
        'mako>=1.3.2',
        'sqlalchemy>=2.0.27',
        'python-multipart>=0.0.9',
        'python-jose[cryptography]>=3.3.0',
        'passlib[bcrypt]>=1.7.4',
        'cryptography>=42.0.5',
    ],
    python_requires='>=3.8',
)