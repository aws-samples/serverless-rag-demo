
### Llama2 with Serverless RAG on Amazon Opensearch Serverless vector db


# Overview
[Amazon Opensearch Serverless offers vector engine to store embeddings for faster similarity searches](https://aws.amazon.com/blogs/big-data/introducing-the-vector-engine-for-amazon-opensearch-serverless-now-in-preview/). The vector engine provides a simple, scalable, and high-performing similarity search capability in Amazon OpenSearch Serverless that makes it easy for you to build generative artificial intelligence (AI) applications without having to manage the underlying vector database infrastructure. This solution demonstrates building a [RAG (Retrieval Augmented Solution)](https://docs.aws.amazon.com/sagemaker/latest/dg/jumpstart-foundation-models-customize-rag.html) with Amazon Opensearch Serverless Vector DB and Llama2 LLM.

With RAG, you retrive data from multiple sources outside the foundational model and augment your prompts by adding relevant data in context.

### Architecture
![architecture](https://github.com/aws-samples/serverless-rag-demo/blob/8d679f3846239d4f41fb93c4545ecdcdf406254b/architecture.png)
