import requests
import json
from transformers import GPT2Tokenizer
import time

def send_request(url, payload):
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, data=json.dumps(payload), headers=headers)
    return response.json()

def main():
    tokenizer = GPT2Tokenizer.from_pretrained('gpt2')

    #prompt = input("Please enter your prompt: ")
    
    #encoded_input = tokenizer(prompt, return_tensors='tf', max_length=512, truncation=True)

    text = """Beneath the canopy of the Eldorian forests, hidden from the eyes of modern civilization, lies the forgotten city of Eldar. This ancient metropolis, once bustling with life and advanced beyond its years, was known to house the sacred Crystals of Fate, sources of immense power and enlightenment. Legends say that the city vanished without a trace, enveloped by the forest itself in an attempt to protect its secrets from the greedy hands of invaders.

For centuries, the tales of Eldar were passed down through generations, each adding their own details, making the city a myth more than a reality. Many believed it to be just a story, a cautionary tale about the greed and corruption that led to the city's mysterious disappearance. However, a recently discovered diary from a renowned explorer of the 19th century suggests that the city is real, and he had found clues to its exact location before his untimely disappearance.i"""

    encoded_input = tokenizer(text, return_tensors='tf')

    server_ip = input("enter the server ip: ")
    
    server_url = f"http://{server_ip}:8502/v1/models/gpt2:predict"

    payload = {
        "inputs": {
            "input_ids": encoded_input['input_ids'].numpy().tolist(),
            "attention_mask": encoded_input['attention_mask'].numpy().tolist()
        }
    }
    start_time = time.time()
    response = send_request(server_url, payload)
    end_time = time.time() 

    duration = end_time - start_time
    print(f"Request duration: {duration:.3f} seconds")

    logits = response["outputs"]["logits"][0][0]

    print(any([logit == 0 for logit in logits]))

    #predicted_text = tokenizer.decode(logits, skip_special_tokens=True)
    #print("Predicted text:", predicted_text)

if __name__ == '__main__':
    main()
