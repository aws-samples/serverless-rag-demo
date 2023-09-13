FROM public.ecr.aws/lambda/python:3.10
COPY llama2_rag.py ${LAMBDA_TASK_ROOT}
COPY embed_model ${LAMBDA_TASK_ROOT}
COPY sample_data ${LAMBDA_TASK_ROOT}
# RUN sudo chmod 777 /tmp/embed_model/
CMD [ "llama2_rag.handler" ]
RUN pip3 install llama-index && \
    pip3 install opensearch-py && \
    pip3 install safetensors && \
    pip3 install sentence-transformers && \
    pip3 install requests-aws4auth && \
    pip3 install boto3
WORKDIR /var/task/
