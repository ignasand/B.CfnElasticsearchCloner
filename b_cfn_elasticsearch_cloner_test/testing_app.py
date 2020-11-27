import os
import sys

from aws_cdk.core import App

"""
Import main stack.
"""

ROOT_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_PATH)
from b_cfn_elasticsearch_cloner_test.testing_infrastructure import TestingInfrastructure

"""
Create CDK app.
"""

app = App()
TestingInfrastructure(app)
app.synth()
