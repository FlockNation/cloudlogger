from flask import Flask, send_from_directory, jsonify
import json
import os

app = Flask(__name__)

@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/cloud_log.json")
def cloud_log():
    if os.path.exists("cloud_log.json"):
        with open("cloud_log.json") as f:
            data = json.load(f)
        return jsonify(data)
    return jsonify([])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
