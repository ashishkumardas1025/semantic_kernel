import streamlit as st
import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import AzureTextCompletion

# Create the kernel
kernel = sk.Kernel()

# Azure OpenAI settings
OPENAI_ENDPOINT = "*************************************"
OPENAI_DEPLOYMENT_NAME = "gpt-35-turbo"
OPENAI_API_KEY = "***********************"

# Add text completion service
kernel.add_text_completion_service(
    service_id="gpt-35-turbo",
    service=AzureTextCompletion("gpt-35-turbo", OPENAI_ENDPOINT, OPENAI_API_KEY)
)

# Initialize the semantic function
prompt = """
You are a helpful chatbot. Please answer the question based on the given text data.
Do not make up answers or add anything which is not in context.
Rather, politely answer that you do not know the answer.

context:
{{ $context_str }}

user: {{ $question_str }}
"""
qa_chat_bot = kernel.create_semantic_function(
    prompt_template=prompt,
    description="Answer question based on provided context",
    max_tokens=100,
    temperature=0.3,
    top_p=0.5,
)

# Streamlit UI
st.title("Chat With Text Chatbot Using Semantic Kernel")
st.markdown("<h3 style='text-align: center; color: blue;'>Built for Gen AI</h3>", unsafe_allow_html=True)

context_str = st.text_area("Enter the text data:", height=100)
question_str = st.text_input("Enter your question:")

if st.button("Answer", key="answer_button") and context_str and question_str:
    sk_context = kernel.create_new_context()
    sk_context["context_str"] = context_str
    sk_context["question_str"] = question_str

    answer = qa_chat_bot.invoke(context=sk_context)

    st.subheader("Answer:")
    st.write(answer)
elif st.button("Answer", key="warning_button"):
    st.warning("Please enter the text data and question.")
