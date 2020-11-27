from setuptools import find_packages, setup

with open("README.md") as readme_file:
    README = readme_file.read()

with open("HISTORY.md") as history_file:
    HISTORY = history_file.read()

with open("VERSION") as file:
    VERSION = file.read()
    VERSION = "".join(VERSION.split())

setup(
    name="b_cfn_elasticsearch_cloner",
    version=VERSION,
    license="Apache License 2.0",
    packages=find_packages(
        exclude=[
            # Exclude virtual environment.
            "venv",
            # Exclude test source files.
            "b_cfn_elasticsearch_cloner_test",
        ]
    ),
    description=("AWS CDK based custom resource that clones DynamoDB tables into Elasticsearch."),
    long_description=README + "\n\n" + HISTORY,
    long_description_content_type="text/markdown",
    include_package_data=True,
    install_requires=[
        "aws-cdk.core>=1.54.0,<2.0.0",
        "aws-cdk.aws_lambda>=1.54.0,<2.0.0",
        "aws-cdk.aws_elasticsearch>=1.54.0,<2.0.0",
        "aws-cdk.aws_lambda_event_sources>=1.54.0,<2.0.0",
        "aws-cdk.aws_logs>=1.54.0,<2.0.0",
        "aws-cdk.aws_kms>=1.54.0,<2.0.0",
        "aws-cdk.aws_iam>=1.54.0,<2.0.0",
        "b_elasticsearch_layer>=0.0.1,<1.0.0",
        "b_cfn_elasticsearch_index>=0.0.3,<1.0.0",
    ],
    author="Ignas Kiela",
    author_email="ignas.kiela@biomapas.com",
    keywords="AWS CDK Lambda Layer Elasticsearch Cloner",
    url="https://github.com/biomapas/B.CfnElasticsearchCloner.git",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
