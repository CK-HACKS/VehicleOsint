from flask import Flask, request, jsonify
import subprocess
import json

app = Flask(__name__)

@app.route('/')
def home():
    return {"status": "Vehicle OSINT API Running", "developer": "@CKEXPLOIT"}

@app.route('/lookup', methods=['GET'])
def lookup():
    reg_no = request.args.get('reg')
    chassis = request.args.get('chassis')

    if not reg_no or not chassis:
        return jsonify({"error": "Missing parameters. Use /lookup?reg=XX00YY0000&chassis=12345"}), 400

    try:
        result = subprocess.check_output(
            ["python3", "jsonoutp.py", reg_no, chassis],
            stderr=subprocess.STDOUT,
            timeout=120
        )
        output = result.decode().strip()
        return jsonify(json.loads(output))
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Process timeout. Selenium took too long."}), 504
    except subprocess.CalledProcessError as e:
        return jsonify({"error": e.output.decode()}), 500
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON output from jsonoutp.py"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
