from langchain.agents import AgentType
from langchain.memory import ConversationBufferMemory
from langchain.llms.bedrock import Bedrock
from langchain.agents import initialize_agent

memory = ConversationBufferMemory(memory_key="chat_history")

llm = Bedrock(model_id = 'amazon.titan-tg1-large',
              model_kwargs = {'maxTokenCount': 4096,
                            'temperature': 0.9},
              region_name = 'us-west-2',
              endpoint_url = 'https://prod.us-west-2.frontend.bedrock.aws.dev')

agent_chain = initialize_agent([], llm,
                               agent = AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
                               verbose = True,
                               memory = memory,
                               agent_kwargs = {'prefix': '''
Assistant is a large language model trained by Amazon.
Assistant is designed to be able to assist with a wide range of tasks, from answering simple questions to providing in-depth explanations and discussions on a wide range of topics. As a language model, Assistant is able to generate human-like text based on the input it receives, allowing it to engage in natural-sounding conversations and provide responses that are coherent and relevant to the topic at hand.
Assistant is constantly learning and improving, and its capabilities are constantly evolving. It is able to process and understand large amounts of text, and can use this knowledge to provide accurate and informative responses to a wide range of questions. Additionally, Assistant is able to generate its own text based on the input it receives, allowing it to engage in discussions and provide explanations and descriptions on a wide range of topics.
Overall, Assistant is a powerful tool that can help with a wide range of tasks and provide valuable insights and information on a wide range of topics. Whether you need help with a specific question or just want to have a conversation about a particular topic, Assistant is here to assist.
TOOLS:
------
Assistant has access to the following tools:'''})
agent_chain.run(input = "hi, i am Fraser")
agent_chain.run(input = "What's the first letter in my name?")


