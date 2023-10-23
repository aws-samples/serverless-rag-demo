
### Amazon Bedrock/ Llama2/ Falcon with Serverless RAG on Amazon Opensearch Serverless vector db


# Overview

A new wave of widespread AI adoption is on the way with generative AI,having the potential to reinvent every aspect of customer experiences and applications. Generative AI is powered by very large machine learning models that are pre-trained on vast amounts of data, commonly referred to as foundation models (FMs). Large Language Models are a subset of Foundation Models(FMs) which are trained on trillions of words and they learn the patterns in the language, allowing them to generate human-like responses to any query we give them.  Additionally, foundation models are trained on very general domain corpora, making them less effective for domain-specific tasks. There lies the importance of RAG. You can use Retrieval Augmented Generation (RAG) to retrieve data from outside a foundation model and augment your prompts by adding the relevant retrieved data in context.

Text generation using RAG with LLMs enables you to generate domain-specific text outputs by supplying specific external data as part of the context fed to LLMs. With RAG, the external data used to augment your prompts can come from multiple data sources, such as a document repositories, databases, or APIs. The first step is to convert your documents and any user queries into a compatible format to perform relevancy search. To make the formats compatible, a document collection, or knowledge library, and user-submitted queries are converted to numerical representations using embedding language models. Embedding is the process by which text is given numerical representation in a vector space. RAG model architectures compare the embeddings of user queries within the vector of the knowledge library. The original user prompt is then appended with relevant context from similar documents within the knowledge library. This augmented prompt is then sent to the foundation model. You can update knowledge libraries and their relevant embeddings asynchronously.

[Amazon Opensearch Serverless offers vector engine to store embeddings for faster similarity searches](https://aws.amazon.com/blogs/big-data/introducing-the-vector-engine-for-amazon-opensearch-serverless-now-in-preview/). The vector engine provides a simple, scalable, and high-performing similarity search capability in Amazon OpenSearch Serverless that makes it easy for you to build generative artificial intelligence (AI) applications without having to manage the underlying vector database infrastructure. 

<details>
  <summary><b>Project Updates</b></summary>

 #### (18-Oct-2023):
  * Support French/German for Anthropic Claude with Amazon Bedrock
  * Support for Redaction feature
  * Inbuilt Text Chunking feature with RecursiveTextSplitter from Langchain

 #### (03-Oct-2023): Support for Amazon Bedrock
  * Anthropic Claude V1/V2/Instant support over Amazon Bedrock
  * Support for Streaming ingestion with Anthropic Claude Models
  * Faster Stack Deployments
  * New Functionality (PII/Sentiment/Translations) added on the UI
  <img width="1437" alt="Screenshot 2023-10-03 at 1 37 53 PM" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/d90c0624-7a4b-4091-9ece-25a29f7f869f">


 #### (14-Sept-2023): Support for new LLM's
  * Llama2-7B (Existing G5.2xlarge)
  * Llama2-13B (G5.12xlarge)
  * Llama2-70B (G5.48xlarge)
  * Falcon-7B (G5.2xlarge)
  * Falcon-40B (G5.12xlarge)
  * Falcon-180B (p4de.24xlarge)
 
 #### New UX/UI (13-Sept-2023): Index Sample Data across different domains. Support multiple-assistant behaviours (Normal/Pirate/Jarvis Assistant modes)
  * <img width="500" alt="Sample_Indexes" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/404ed22f-c61a-4c12-9b57-3a7eca871bee">
  * <img width="500" alt="QueryBehaviour" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/647ea08c-0eca-472e-8457-3ef6c4d5d6e6">

</details>

<details>
  <summary><b>Available Features</b></summary>


  #### Multi-lingual Support
  
  <img width="1154" alt="Screenshot 2023-10-18 at 1 23 37 AM" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/ceafb1d6-ba1e-4102-924c-18755c11ee31">

  
  #### Sentiment Analysis
  
  <img width="1149" alt="Screenshot 2023-10-18 at 1 29 54 AM" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/722e6e11-702f-4634-aafd-da5bdff25c61">

  
  #### PII Data Detection
  
  <img width="1154" alt="Screenshot 2023-10-18 at 1 30 48 AM" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/78ec1c00-2238-4d0b-b035-30701a836940">

  
  #### PII Data Redaction
  
  <img width="1154" alt="Screenshot 2023-10-18 at 1 31 52 AM" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/e1e838e0-2ced-4b08-980c-e4e976826f98">

  
</details>


<details open>
 <summary><b>Bedrock RAG Demo</b></summary>

   #### Bedrock RAG Demo Video
   
   https://github.com/aws-samples/serverless-rag-demo/assets/25897220/3549ab88-3957-4b35-b04b-5ba21c41c89b



</details>

<details>
    <summary><b> Llama2 RAG Demo </b></summary>

   #### Llama2 RAG Demo
   
   https://github.com/aws-samples/serverless-rag-demo/assets/25897220/d9162e43-59f5-400c-80d4-3f1545535b66
</details>



This solution demonstrates building a [RAG (Retrieval Augmented Solution)](https://docs.aws.amazon.com/sagemaker/latest/dg/jumpstart-foundation-models-customize-rag.html) with Amazon Opensearch Serverless Vector DB and [Amazon Bedrock](https://aws.amazon.com/bedrock/), [Llama2 LLM](https://ai.meta.com/llama/), [Falcon LLM](https://falconllm.tii.ae/)


<details>
 <summary><b> Prerequisites </b></summary>
   
 #### Prerequsites:
  * [An AWS account](https://aws.amazon.com/console/)
  * [For Amazon Bedrock, you should have access to Anthropic Claude models](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html)
  * Amazon Bedrock is available in 3 regions globally, US East (N. Virginia), US West (Oregon), and Asia Pacific (Tokyo).

  
 #### Familiarity with below Services
  * [AWS IAM](https://docs.aws.amazon.com/iam/index.html). 
  * [AWS Lambda](https://docs.aws.amazon.com/lambda/latest/dg/welcome.html)
  * [Amazon API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/welcome.html)
  * [Amazon opensearch serverless](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-overview.html)

    
 #### For Llama2/Falcon models deployed on Amazon Sagemaker
  * [Amazon Sagemaker](https://docs.aws.amazon.com/sagemaker/index.html)
  * GPU Instance of type ml.g5.2xlarge for endpoint usage
  * _Supported Llama2 regions (us-east-1 , us-east-2 , us-west 2 , eu-west-1 , and ap-southeast-1)_

</details>




### Architecture
![architecture](https://github.com/aws-samples/serverless-rag-demo/assets/25897220/e2b9e3ac-b7b9-479d-b642-e2e1d5ce3837)


### Deploying the Solution to your AWS account with AWS Cloudshell

<details>
 <summary><b> Create an Admin User to deploy this stack </b></summary>

 #### Section1 - Create an IAM user with Administrator permissions (OPTIONAL:  If your already an Admin user/role, you may skip this step) 

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

</details>


<details>
 <summary><b> Deploy the RAG based Solution </b></summary>

#### Section 2 - Deploy this RAG based Solution (The below commands should be executed in the region of deployment)

1. Search for **AWS Cloudshell**. Configure your aws cli environment with the access/secret keys of the new admin user using the below command on AWS Cloudshell
   ```
      aws configure
   ```

<img width="1118" alt="LLMAdminConfigureCloudShell" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/58175b14-259d-4d7d-b3e4-bb75fb48e998">

2. Git Clone the serverless-rag-demo repository from aws-samples
   ```
    git clone https://github.com/aws-samples/serverless-rag-demo.git
   ```

3. Go to the directory where we have the downloaded files.
   ```
     cd serverless-rag-demo
   ```

4. Fire the bash script that creates the RAG based solution. Pass the environment and region for deployment. environment can be dev,qa,sandbox. Region can be any of those supported by Amazon Opensearch Serverless [refer](https://aws.amazon.com/about-aws/whats-new/2023/01/amazon-opensearch-serverless-available)
   ```
     sh creator.sh
   ```
   
5. Select the LLM you want to deploy (sh creator.sh dev us-east-1) . Select Option 1 for Amazon Bedrock.

6. When selecting Amazon Bedrock (Option 1), you should specify an API Key. The key should be atleast 20 characters long.

   <img width="1088" alt="Screenshot 2023-10-23 at 10 48 01 PM" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/dfc7ba5c-48df-4ea6-83ed-31c35e4a1098">

7. Press **Enter** to proceed with deployment of the stack or **ctrl+c** to exit

   <img width="1086" alt="Screenshot 2023-10-23 at 10 49 04 PM" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/b74105bb-b817-4c47-8c41-1b72f7fa27b3">

8. Total deployment takes around 40 minutes. Once the deployment is complete head to API Gateway. Search for API with name
rag-llm-api-{env_name}. Get the invoke URL for the API

   <img width="1407" alt="ApiGw1" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/623344df-adf0-41b0-a90f-16b8cec62f25">

7. Invoke the Api Gateway URL that loads an html page for testing the RAG based solution as api-gateway-url/rag
   * _Do not forget to append_ **"rag"** _at the end of the API-GW url_

   eg: https://xxxxxxx.execute-api.us-east-1.amazonaws.com/dev/rag

   **Add in your API Key used during stack Amazon Bedrock deployment to proceed with the demo**
   
   <img width="1270" alt="Screenshot 2023-10-23 at 10 50 39 PM" src="https://github.com/aws-samples/serverless-rag-demo/assets/25897220/9b1fefa0-d36b-4a4f-bd61-64f563db281e">
 
</details>
