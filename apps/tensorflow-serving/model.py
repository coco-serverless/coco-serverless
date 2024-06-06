from transformers import GPT2Tokenizer, GPT2LMHeadModel

tokenizer = GPT2Tokenizer.from_pretrained("gpt2")
model = GPT2LMHeadModel.from_pretrained("gpt2")

def generate_text(prompt):

    encoded_input = tokenizer.encode(prompt, return_tensors='pt')

    output = model.generate(encoded_input, max_length=200, num_return_sequences=1)

    decoded_output = tokenizer.decode(output[0], skip_special_tokens=True)
    return decoded_output