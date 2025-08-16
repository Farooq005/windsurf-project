from setuptools import setup, find_packages

setup(
    name="anime_list_sync",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "requests",
        "python-dotenv",
        "fastapi",
        "uvicorn",
        "streamlit",
    ],
)
