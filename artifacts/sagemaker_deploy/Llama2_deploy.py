from sagemaker.jumpstart.model import JumpStartModel
import sys

sagemaker_endpoint_name = str(sys.argv[1])
model_id, model_version = str(sys.argv[2]), "*"

print(f'Deploying {model_id} with endpoint name {sagemaker_endpoint_name}')
model = JumpStartModel(model_id=model_id)
predictor = model.deploy(endpoint_name=sagemaker_endpoint_name)

