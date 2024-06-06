from flask import Flask, request, jsonify
from model import generate_text

app = Flask(__name__)

@app.route('/generate', methods=['POST'])
def handle_generate():
    data = request.json
    if 'prompt' not in data:
        return jsonify({'error': 'No prompt provided'}), 400

    prompt = data['prompt']
    generated_text = generate_text(prompt)

    return jsonify({'generated_text': generated_text})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8501, debug=True)