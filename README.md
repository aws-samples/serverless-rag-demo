
### Llama2/Falcon with Serverless RAG on Amazon Opensearch Serverless vector db


# Overview

A new wave of widespread AI adoption is on the way with generative AI,having the potential to reinvent every aspect of customer experiences and applications. Generative AI is powered by very large machine learning models that are pre-trained on vast amounts of data, commonly referred to as foundation models (FMs). Large Language Models are a subset of Foundation Models(FMs) which are trained on trillions of words and they learn the patterns in the language, allowing them to generate human-like responses to any query we give them.  Additionally, foundation models are trained on very general domain corpora, making them less effective for domain-specific tasks. There lies the importance of RAG. You can use Retrieval Augmented Generation (RAG) to retrieve data from outside a foundation model and augment your prompts by adding the relevant retrieved data in context.

Text generation using RAG with LLMs enables you to generate domain-specific text outputs by supplying specific external data as part of the context fed to LLMs. With RAG, the external data used to augment your prompts can come from multiple data sources, such as a document repositories, databases, or APIs. The first step is to convert your documents and any user queries into a compatible format to perform relevancy search. To make the formats compatible, a document collection, or knowledge library, and user-submitted queries are converted to numerical representations using embedding language models. Embedding is the process by which text is given numerical representation in a vector space. RAG model architectures compare the embeddings of user queries within the vector of the knowledge library. The original user prompt is then appended with relevant context from similar documents within the knowledge library. This augmented prompt is then sent to the foundation model. You can update knowledge libraries and their relevant embeddings asynchronously.

[Amazon Opensearch Serverless offers vector engine to store embeddings for faster similarity searches](https://aws.amazon.com/blogs/big-data/introducing-the-vector-engine-for-amazon-opensearch-serverless-now-in-preview/). The vector engine provides a simple, scalable, and high-performing similarity search capability in Amazon OpenSearch Serverless that makes it easy for you to build generative artificial intelligence (AI) applications without having to manage the underlying vector database infrastructure. 

#### (14-Sept-2023): Support for new LLM's
 * Llama2-7B (Existing G5.2xlarge)
 * Llama2-13B (G5.12xlarge)
 * Llama2-70B (G5.48xlarge)
 * Falcon-7B (G5.2xlarge)
 * Falcon-40B (G5.12xlarge)
 * Falcon-180B (p4de.24xlarge)

#### New UX/UI (13-Sept-2023): Index Sample Data across different domains. Support multiple-assistant behaviours (Normal/Pirate/Jarvis Assistant modes)

   <img width="500" alt="Sample_Indexes" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/404ed22f-c61a-4c12-9b57-3a7eca871bee">
   <img width="500" alt="QueryBehaviour" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/647ea08c-0eca-472e-8457-3ef6c4d5d6e6">


#### Video Demo
https://github.com/aws-samples/serverless-rag-demo/assets/25897220/d9162e43-59f5-400c-80d4-3f1545535b66






This solution demonstrates building a [RAG (Retrieval Augmented Solution)](https://docs.aws.amazon.com/sagemaker/latest/dg/jumpstart-foundation-models-customize-rag.html) with Amazon Opensearch Serverless Vector DB and [Llama2 LLM](https://ai.meta.com/llama/), [Falcon LLM](https://falconllm.tii.ae/)

### Prerequisites

For this walkthrough, you should have the following prerequisites:

[An AWS account](https://aws.amazon.com/console/)

Familiarity with below Services.

[AWS IAM](https://docs.aws.amazon.com/iam/index.html). 

[AWS Lambda](https://docs.aws.amazon.com/lambda/latest/dg/welcome.html)

[Amazon API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/welcome.html)
 
[Amazon opensearch serverless](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-overview.html)

[Amazon Sagemaker](https://docs.aws.amazon.com/sagemaker/index.html)

_GPU Instance of type ml.g5.2xlarge for endpoint usage_

_Supported Llama2 regions (us-east-1 , us-east-2 , us-west 2 , eu-west-1 , and ap-southeast-1)_



### Architecture
![Architecture drawio (2)](https://github.com/aws-samples/serverless-rag-demo/assets/25897220/0dd72882-f650-43b2-8479-addf9685067c)


### Deploying the Solution to your account with AWS Cloudshell

#### Section1 - Create an IAM user with Administrator permissions. 

1. Search for the service IAM on the AWS Console and go the IAM Dashboard and click on “Users“ tab under ”Access Management” and Click on “Create User”

![image](https://github.com/aws-samples/serverless-rag-demo/blob/main/media/Screenshot%202023-08-24%20at%204.40.44%20PM.png)

2. Give a name to the IAM user and click “Next“

![image](https://github.com/aws-samples/serverless-rag-demo/blob/main/media/Screenshot%202023-08-24%20at%204.41.48%20PM.png)

3. Now Click on Attach Policies directly and Choose "AdminsitratorAccess" and click "Next" 

![image](https://github.com/aws-samples/serverless-rag-demo/blob/main/media/Screenshot%202023-08-24%20at%204.42.44%20PM.png)

4. Now review the details and click on "Create User"

![image](https://github.com/aws-samples/serverless-rag-demo/blob/main/media/Screenshot%202023-08-24%20at%204.43.24%20PM.png)

5. Now we need to create credentials for this IAM. Go to "Users" tab again and you will see your new user listed over there. Now click on the username.

![image](https://github.com/aws-samples/serverless-rag-demo/blob/main/media/Screenshot%202023-08-24%20at%204.44.14%20PM.png)

6. Go to Security Credentials Tab and under "Access Keys" click on "Create Access key"

<img width="1377" alt="LLMAdminSecurityCredentials2" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/36bdf80f-8b0e-43a4-ad0f-a3233ce753cb">


7. In the window that appears choose the first option "Command line Interface" and click the checkbox at the bottom and click Next

![image](https://github.com/aws-samples/serverless-rag-demo/blob/main/media/Screenshot%202023-08-24%20at%204.45.24%20PM.png)

8.Now the Tag is optional and you can leave this empty and click on Create Access Key

![image](https://github.com/aws-samples/serverless-rag-demo/blob/main/media/Screenshot%202023-08-24%20at%204.45.34%20PM.png)

9. Now click on Download .csv file to download the credentials and click on "Done". Now lets proceed to section 2

![image](https://github.com/aws-samples/serverless-rag-demo/blob/main/media/Screenshot%202023-08-24%20at%204.45.49%20PM.png)


#### Section 2 - Deploy a RAG based Solution (The below commands should be executed in the region of deployment)

1. Search for AWS Cloudshell. Configure your aws cli environment with the access/secret keys of the new admin user using the below command on AWS Cloudshell
   ```
      aws configure
   ```

<img width="1118" alt="LLMAdminConfigureCloudShell" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/58175b14-259d-4d7d-b3e4-bb75fb48e998">


3. Git Clone the serverless-rag-demo repository from aws-samples
   ```
    git clone https://github.com/aws-samples/serverless-rag-demo.git
   ```

5. Go to the directory where we have the downloaded files.
   ```
     cd serverless-rag-demo
   ```

6. Fire the bash script that creates the RAG based solution. Pass the environment and region for deployment. environment can be dev,qa,sandbox. Region can be any of those supported by Amazon Opensearch Serverless [refer](https://aws.amazon.com/about-aws/whats-new/2023/01/amazon-opensearch-serverless-available)
   ```
     sh creator.sh dev us-east-1
   ```
   
7. Select the LLM you want to deploy (sh creator.sh dev us-east-1)

   <img width="1088" alt="Screenshot 2023-09-14 at 8 48 50 PM" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/78492d0a-e9d0-481c-b2cd-09bd63ae61ee">

8. Total deployment takes around 40 minutes. Once the deployment is complete head to API Gateway. Search for API with name
rag-llm-api-{env_name}. Get the invoke URL for the API

  <img width="1407" alt="ApiGw1" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/623344df-adf0-41b0-a90f-16b8cec62f25">


9. Invoke the Api Gateway URL that loads an html page for testing the RAG based solution as api-gateway-url/rag
   * _Do not forget to append_ **"rag"** _at the end of the API-GW url_

   eg: https://xxxxxxx.execute-api.us-east-1.amazonaws.com/dev/rag

   <img width="1238" alt="Screenshot 2023-09-14 at 8 52 09 PM" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/9e5c3e4d-e211-4727-ab57-ecd188565a64">




 







