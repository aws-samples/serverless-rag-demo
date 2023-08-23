from sagemaker.jumpstart.model import JumpStartModel
import sys

sagemaker_endpoint_name = str(sys.argv[1])
model_id, model_version = "meta-textgeneration-llama-2-7b-f", "*"

model = JumpStartModel(model_id=model_id)
predictor = model.deploy(endpoint_name=sagemaker_endpoint_name)

