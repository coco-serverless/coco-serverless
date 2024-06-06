# FROM python:3.9-slim

# RUN apt-get update && apt-get install -y --no-install-recommends \
#     gcc \
#     libgomp1 && \
#     rm -rf /var/lib/apt/lists/*

# RUN pip install --no-cache-dir transformers[torch]

# #RUN pip install --no-cache-dir torch transformers flask

# RUN python -c "from transformers import GPT2Tokenizer, GPT2LMHeadModel; \
#     GPT2Tokenizer.from_pretrained('gpt2'); \
#     GPT2LMHeadModel.from_pretrained('gpt2')"

# RUN apt-get clean && \
#     rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# ENV APP_HOME /app
# WORKDIR $APP_HOME
# COPY . ./

# CMD ["python", "app.py"]


FROM tensorflow/serving

RUN mkdir -p /models/distilbert/1

COPY ./model/distilbert/1 /models/distilbert/1

ENV MODEL_NAME=distilbert
ENV MODEL_BASE_PATH=/models

EXPOSE 8501

CMD ["tensorflow_model_server", "--port=8501", "--rest_api_port=8502", "--model_name=distilbert", "--model_base_path=/models/distilbert/1/saved_model"]

