from flask import Flask
from os import environ

app = Flask(__name__)


@app.route('/')
def hello_world():
    target = environ.get('TARGET', 'World')
    return 'Hello {}!\n'.format(target)


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(environ.get('PORT', 8080)))
